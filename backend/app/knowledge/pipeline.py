"""解析管道：分发解析 → 分段 → 向量化入库 → 知识提取与冲突检测 → 更新 Document 状态（后台任务入口）。"""

import logging
from datetime import datetime

from app.db import SessionLocal
from app.db.models import Document

logger = logging.getLogger(__name__)


async def parse_document(doc_id: str) -> str:
    """解析文档并向量化入库，返回解析文本/Markdown。"""
    from app.knowledge.chunking.factory import get_chunker
    from app.knowledge.parsers import get_parser  # 延迟 import 避免循环

    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            raise ValueError(f"文档不存在: {doc_id}")
        try:
            parser = get_parser(doc.file_type)
            result = await parser.parse(doc.file_path)
            chunks = get_chunker().chunk(result)
            if chunks:
                await index_chunks(doc_id, chunks)
            conflict_count = await extract_and_save_knowledge(doc_id, result)
        except Exception:
            # 后台任务入口：吞掉异常仅记日志——失败经 doc.status=「失败」观测即可，
            # 重抛只会打断 FastAPI 后台任务且无所收益（ticket #11：失败不拖垮其他格式解析）
            doc.status = "失败"
            db.commit()
            logger.exception("文档解析失败 doc=%s file=%s", doc_id, doc.filename)
            return ""
        doc.status = "有冲突" if conflict_count else "已完成"
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
    VectorStore().add(doc_id, chunks, embeddings)


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
            embeddings = await get_embedder().embed(titles)
            save_knowledge(
                "default",
                to_save,
                edges,
                source_doc_id=doc_id,
                title_embeddings=dict(zip(titles, embeddings)),
            )
        return len(pending)
    except Exception:
        logger.exception("知识图谱提取失败 doc=%s", doc_id)
        return 0
