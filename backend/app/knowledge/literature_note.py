"""文献笔记管道（CONTEXT.md「文献笔记」，ADR-0007）：解析完成后自动生成摘要卡。

一份教学资料入库时生成一张文献笔记：资料概要（对话模型生成）+ 由该资料提取的
知识点索引（已入图谱的节点）。与教学资料 1:1，资料的管理入口落在它上面。

对话模型未配置时：分块与解析照常入库（那是 `pipeline.parse_document` 的事），
文献笔记不生成、只落「未配置」状态——资料详情端给「去设置页」引导，
不返回任何假摘要（AGENTS.md 铁律：产品里没有假数据兜底）。
「联网检索并入库」的网页结果后续复用本管道（票 10），来源记「网页」。
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ProviderNotConfigured
from app.db import SessionLocal
from app.db.models import Document, KnowledgeNode, LiteratureNote

logger = logging.getLogger(__name__)

# 来源取值（CONTEXT.md 第 4 节）：上传入库的是教学资料；网页入库走同一管道
SOURCE_DOCUMENT = "教学资料"
SOURCE_WEB = "网页"

# 生成状态取值：已生成 / 未配置（列上还有默认值「未生成」，只在行缺席时由详情端给出）
STATUS_GENERATED = "已生成"
STATUS_UNCONFIGURED = "未配置"
STATUS_PENDING = "未生成"

# 概要提示词。开头「资料概要编写助手」同时是替身（tests/support/fakes.py）识别作答口径的标记。
_SUMMARY_PROMPT = """你是教学资料的资料概要编写助手。为下面的资料写一段资料概要，作为它的文献笔记的「资料概要」。

要求：
- 两三句话：这份资料讲了什么、覆盖哪些内容、适合什么样的备课场景。
- 只输出概要正文：不要标题、不要列表、不要客套话。

资料内容：
__TEXT__
"""


async def generate_summary(text: str) -> str:
    """对话模型生成资料概要（纯文本）；未配置对话模型时抛 ProviderNotConfigured。"""
    from app.core.llm.base import ChatMessage
    from app.core.llm.factory import get_llm

    prompt = _SUMMARY_PROMPT.replace("__TEXT__", text[:8000])
    result = await get_llm().chat([ChatMessage(role="user", content=prompt)])
    return result.content.strip()


def knowledge_index_for_doc(db: Session, doc_id: str) -> list[dict]:
    """由这份资料提取出的知识点索引（已入图谱的节点；待审冲突节点还没有可点的 id）。"""
    rows = (
        db.execute(select(KnowledgeNode).where(KnowledgeNode.source_docs.isnot(None)))
        .scalars()
        .all()
    )
    return [
        {"id": node.id, "title": node.title} for node in rows if doc_id in (node.source_docs or [])
    ]


def upsert_note(
    db: Session,
    doc: Document,
    *,
    status: str,
    summary: str,
    knowledge_index: list[dict],
    source: str = SOURCE_DOCUMENT,
) -> LiteratureNote:
    """写入（或更新）这份资料的文献笔记行：1:1，重复解析不产生第二张卡。"""
    note = (
        db.execute(select(LiteratureNote).where(LiteratureNote.doc_id == doc.id))
        .scalars()
        .one_or_none()
    )
    if note is None:
        note = LiteratureNote(user_id=doc.user_id, doc_id=doc.id)
        db.add(note)
    note.source = source
    note.status = status
    note.summary = summary
    note.knowledge_index = knowledge_index
    return note


async def build_note(doc_id: str, text: str, source: str = SOURCE_DOCUMENT) -> None:
    """解析完成后生成并落库文献笔记：资料概要 + 知识点索引（尽力而为，不阻断解析）。

    - 对话模型未配置：落「未配置」行（概要与索引为空），教师看到的是去设置页的引导；
    - 其余异常：记日志、不落行（详情端如实报「未生成」）——资料本身已入库可用，
      概要生成失败不该把一份能检索的资料打成「失败」；落库环节同理，写库失败
      也不得穿透回解析主流程把整单标成「失败」。
    """
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if doc is None:
            return
        try:
            summary = await generate_summary(text)
        except ProviderNotConfigured as exc:
            upsert_note(
                db, doc, status=STATUS_UNCONFIGURED, summary="", knowledge_index=[], source=source
            )
            db.commit()
            logger.info("文献笔记未生成（能力未配置）doc=%s file=%s：%s", doc_id, doc.filename, exc)
            return
        except Exception:
            logger.exception("文献笔记概要生成失败 doc=%s file=%s", doc_id, doc.filename)
            return
        try:
            upsert_note(
                db,
                doc,
                status=STATUS_GENERATED,
                summary=summary,
                knowledge_index=knowledge_index_for_doc(db, doc_id),
                source=source,
            )
            db.commit()
        except Exception:
            # 写库失败同样“尽力而为”：分块已入库的资料不能因笔记落库失败被打成解析失败
            logger.exception("文献笔记落库失败 doc=%s file=%s", doc_id, doc.filename)
    finally:
        db.close()
