"""检索的公共前半段：意图 → 查询串 → 向量化 → 相关度阈值过滤 + 参考资料加权 KNN，以及来源资料名溯源。

两档检索策略共用这一份实现；调用方（编排器 / 生成端点）不再自己算权重与拼溯源。
"""

import logging

from app.config import settings
from app.knowledge.retrieval.base import RetrievalHit

logger = logging.getLogger(__name__)


def intent_query(intent) -> str:
    """备课意图 → 检索查询串（主题 + 知识点）。"""
    return " ".join([intent.topic, *intent.knowledge_points]).strip()


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """余弦距离（1 − 余弦相似度）：检索命中阈值的度量口径。

    向量库存的 distance 是 L2 欧氏距离（sqlite-vec 默认度量），大小受向量模长影响，
    不能直接与余弦阈值比较；这里用原始向量现算余弦距离，库内存量向量照常可用，无需迁移。
    阈值口径与冲突检测的 conflict_distance_threshold 一致（余弦距离），但两条水位各自独立。
    """
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 1.0  # 零向量没有方向：按「无相似信息」（正交）处理
    similarity = max(-1.0, min(1.0, dot / ((na**0.5) * (nb**0.5))))
    return 1.0 - similarity


async def search_hits(
    query: str, top_k: int, reference_doc_ids: list[str] | None
) -> list[RetrievalHit] | None:
    """向量化查询并做参考资料加权 KNN，再按余弦距离阈值过滤：超阈值的命中一律丢弃（不是降权）。

    阈值取自配置 `retrieval_distance_threshold`（默认保守取宽，避免误杀真实内容），
    与冲突检测的 `conflict_distance_threshold` 各管各的水位，不共用。
    检索失败返回 None（调用方降级为空结果）。

    参考资料的加权规则住在向量存储层（命中参考资料的片段距离折扣后参与排名），
    策略只负责把本次备课勾选的参考资料标识传下去。
    """
    try:
        from app.core.embedding.factory import get_embedder
        from app.knowledge.vector_store import VectorStore

        embeddings = await get_embedder().embed([query])
        query_embedding = embeddings[0]
        rows = VectorStore().search(
            query_embedding, k=top_k, boost_doc_ids=reference_doc_ids or None, with_embeddings=True
        )
    except Exception:
        logger.warning("知识检索失败，降级为空上下文", exc_info=True)
        return None
    threshold = settings.retrieval_distance_threshold
    return [
        RetrievalHit(
            chunk_id=r["chunk_id"],
            distance=r["distance"],
            doc_id=r["doc_id"],
            content=r["content"],
        )
        for r in rows
        if _cosine_distance(query_embedding, r["embedding"]) <= threshold
    ]


def library_is_empty() -> bool:
    """向量库里是否一个分块都没有：区分「知识库为空」与「未命中相关内容」（票 01）。

    探测失败按非空处理：说不了「为空」，宁可让回复落「未命中相关内容」口径。
    """
    try:
        from app.knowledge.vector_store import VectorStore

        return VectorStore().chunk_count() == 0
    except Exception:
        logger.warning("向量库规模查询失败，按非空处理", exc_info=True)
        return False


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
