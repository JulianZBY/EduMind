"""检索的公共前半段：意图 → 查询串 → 向量化 → 参考资料加权 KNN，以及来源资料名溯源。

两档检索策略共用这一份实现；调用方（编排器 / 生成端点）不再自己算权重与拼溯源。
"""

import logging

from app.knowledge.retrieval.base import RetrievalHit

logger = logging.getLogger(__name__)


def intent_query(intent) -> str:
    """备课意图 → 检索查询串（主题 + 知识点）。"""
    return " ".join([intent.topic, *intent.knowledge_points]).strip()


async def search_hits(
    query: str, top_k: int, reference_doc_ids: list[str] | None
) -> list[RetrievalHit] | None:
    """向量化查询并做参考资料加权 KNN；检索失败返回 None（调用方降级为空结果）。

    参考资料的加权规则住在向量存储层（命中参考资料的片段距离折扣后参与排名），
    策略只负责把本次备课勾选的参考资料标识传下去。
    """
    try:
        from app.core.embedding.factory import get_embedder
        from app.knowledge.vector_store import VectorStore

        embeddings = await get_embedder().embed([query])
        rows = VectorStore().search(embeddings[0], k=top_k, boost_doc_ids=reference_doc_ids or None)
    except Exception:
        logger.warning("知识检索失败，降级为空上下文", exc_info=True)
        return None
    return [
        RetrievalHit(
            chunk_id=r["chunk_id"],
            distance=r["distance"],
            doc_id=r["doc_id"],
            content=r["content"],
        )
        for r in rows
    ]


def source_names(doc_ids: list[str]) -> list[str]:
    """命中 doc_id 按排名映射为资料名（去重）；资料已删除时回退为 doc_id。"""
    names: dict[str, str] = {}
    try:
        from sqlalchemy import select

        from app.db import SessionLocal
        from app.db.models import Document

        db = SessionLocal()
        try:
            rows = db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
            names = {d.id: d.filename for d in rows}
        finally:
            db.close()
    except Exception:
        logger.warning("来源资料名查询失败，回退为 doc_id", exc_info=True)
    ordered: list[str] = []
    for doc_id in doc_ids:
        name = names.get(doc_id, doc_id)
        if name not in ordered:
            ordered.append(name)
    return ordered
