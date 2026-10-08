"""解析管道：分发解析 → 分段 → 向量化入库 → 知识提取与冲突检测 → 更新 Document 状态（后台任务入口）。"""

import asyncio
import logging
from datetime import datetime

from app.core.errors import ProviderNotConfigured
from app.db import SessionLocal
from app.db.models import Document
from app.knowledge.literature_note import SOURCE_DOCUMENT, SOURCE_WEB, build_note
from app.knowledge.storage import normalize_stored_path

logger = logging.getLogger(__name__)

# 面向教师的失败原因（资料详情里展示）。不回显内部异常文本：那里可能带本机路径。
REASON_INTERRUPTED = "解析被中断（服务重启），请重新上传这份资料。"
REASON_PARSE_ERROR = (
    "资料解析没有成功：文件可能已损坏、被加密，或内容无法识别。请检查文件后重新上传。"
)


WEB_RETRY_HINT = "请回到备课会话，手动再次点击「联网检索并入库」。"
REASON_WEB_ERROR = f"网页资料处理没有成功。{WEB_RETRY_HINT}"
REASON_WEB_INTERRUPTED = f"网页资料处理被中断（服务重启）。{WEB_RETRY_HINT}"


def failure_reason_for(exc: Exception, *, source: str = SOURCE_DOCUMENT) -> str:
    """把解析异常翻译成给教师看的一句话。

    未配置云端能力时沿用能力工厂给出的引导原文（它本来就是写给教师的）；
    其余异常按来源给出恢复指引，细节只进日志；网页没有可重新上传的原件。
    """
    if isinstance(exc, ProviderNotConfigured):
        return str(exc)
    return REASON_WEB_ERROR if source == SOURCE_WEB else REASON_PARSE_ERROR


def fail_stuck_documents() -> int:
    """启动清扫：把上次进程残留的「处理中」资料标记为「失败」，返回清扫条数。

    后台解析任务随进程消亡——进程重启后被中断的解析再没有任何任务推进它，
    若不清扫会永远停在「处理中」，前端会一直轮询（不会自愈）。这里统一标记为
    「失败」（与解析异常同一终态），教师按来源重新上传或手动联网检索并入库；不自动重排解析：
    坏文件会在每次启动时反复失败、形成启动循环。
    """
    db = SessionLocal()
    try:
        stuck = db.query(Document).filter(Document.status == "处理中").all()
        for doc in stuck:
            doc.status = "失败"
            doc.failure_reason = (
                REASON_WEB_INTERRUPTED if doc.file_type == SOURCE_WEB else REASON_INTERRUPTED
            )
        if stuck:
            db.commit()
            logger.warning("启动清扫：%d 份「处理中」资料标记为失败", len(stuck))
        return len(stuck)
    finally:
        db.close()


async def parse_document(
    doc_id: str, *, text: str | None = None, source: str = SOURCE_DOCUMENT
) -> str:
    """解析文档并入库；网页已取得的文本跳过解析器，其余步骤与上传完全相同。"""
    from app.knowledge.chunking.factory import get_chunker
    from app.knowledge.parsers import get_parser  # 延迟 import 避免循环

    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            raise ValueError(f"文档不存在: {doc_id}")
        try:
            if text is None:
                parser = get_parser(doc.file_type)
                # 读侧路径规范化（票 07）：存量 Windows 分隔符的路径统一为 POSIX 再交给解析器
                result = await parser.parse(normalize_stored_path(doc.file_path))
            else:
                result = text
            chunks = get_chunker().chunk(result)
            if chunks:
                await index_chunks(doc_id, chunks)
            conflict_count = await extract_and_save_knowledge(doc_id, result)
            # 文献笔记（ADR-0007）：知识提取完成后生成摘要卡——概要 + 本资料的知识点索引。
            # 尽力而为：对话模型未配置时只落「未配置」状态，不影响解析主流程。
            await build_note(doc_id, result, source=source)
        except Exception as exc:
            # 后台任务入口：吞掉异常仅记日志——失败经 doc.status=「失败」观测即可，
            # 重抛只会打断 FastAPI 后台任务且无所收益（ticket #11：失败不拖垮其他格式解析）
            doc.status = "失败"
            doc.failure_reason = failure_reason_for(
                exc, source=SOURCE_WEB if doc.file_type == SOURCE_WEB else source
            )
            db.commit()
            if isinstance(exc, ProviderNotConfigured):
                # 能力未配置不是故障：原因已写进 failure_reason 给教师看，日志记一行、不带堆栈
                logger.warning(
                    "文档解析未完成（能力未配置）doc=%s file=%s：%s", doc_id, doc.filename, exc
                )
            else:
                logger.exception("文档解析失败 doc=%s file=%s", doc_id, doc.filename)
            return ""
        doc.status = "有冲突" if conflict_count else "已完成"
        doc.failure_reason = ""
        doc.conflict_count = conflict_count
        doc.parsed_at = datetime.now()  # noqa: DTZ005 - SQLite 存 naive 时间
        db.commit()
        return result
    finally:
        db.close()


async def index_chunks(doc_id: str, chunks: list[str]) -> None:
    """向量化 chunk 并入库。"""
    from app.core.embedding.factory import get_embedder
    from app.knowledge.vector_store import VectorStore

    embeddings = await get_embedder().embed(chunks)
    # sqlite-vec 同步写：放线程池，解析后台任务不阻塞事件循环（M1）
    await asyncio.to_thread(VectorStore().add, doc_id, chunks, embeddings)


async def extract_and_save_knowledge(doc_id: str, text: str) -> int:
    """提取知识图谱 + 冲突检测（尽力而为，失败不阻断主流程），返回待审冲突数。

    冲突节点与同名重复节点不入图谱（ADR-0006：审核前新节点不入知识图谱）；
    其余节点连同标题向量索引直接入库（既有行为）。
    """
    from app.core.embedding.factory import get_embedder
    from app.knowledge.conflict import detect_conflicts
    from app.knowledge.graph import extract_knowledge, save_knowledge

    try:
        nodes, edges = await extract_knowledge(text)
        if not nodes:
            return 0
        pending, duplicates = await detect_conflicts("default", nodes, doc_id)
        held = {id(n) for n in pending} | {id(n) for n in duplicates}
        to_save = [n for n in nodes if id(n) not in held]
        if to_save:
            titles = sorted({(n.get("title") or "").strip() for n in to_save} - {""})
            embedder = get_embedder()
            embeddings = await embedder.embed(titles)
            from app.knowledge.title_vectors import title_vector_space

            await asyncio.to_thread(
                save_knowledge,
                "default",
                to_save,
                edges,
                source_doc_id=doc_id,
                title_embeddings=dict(zip(titles, embeddings)),
                title_spaces={
                    t: title_vector_space(embedder, len(e)) for t, e in zip(titles, embeddings)
                },
            )
        return len(pending)
    except ProviderNotConfigured as exc:
        # 没配对话模型时知识提取跳过、分块照常入库（文档约定的未配置行为）：记一行，不带堆栈
        logger.info("知识图谱提取跳过（能力未配置）doc=%s：%s", doc_id, exc)
        return 0
    except Exception:
        logger.exception("知识图谱提取失败 doc=%s", doc_id)
        return 0
