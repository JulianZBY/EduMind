"""纯向量检索：只按语义相似度（参考资料加权）取命中分块，不融合知识图谱。"""

from app.knowledge.retrieval.base import RetrievalResult, Retriever
from app.knowledge.retrieval.context import chunks_only_context
from app.knowledge.retrieval.search import intent_query, search_hits, source_names


class VectorRetriever(Retriever):
    """向量档：生成上下文只有命中分块，图谱不参与。"""

    name = "vector"

    async def retrieve(self, intent, top_k: int = 5, reference_doc_ids=None) -> RetrievalResult:
        query = intent_query(intent)
        if not query:
            return RetrievalResult.empty()
        hits = await search_hits(query, top_k, reference_doc_ids)
        if hits is None:
            return RetrievalResult.empty()
        chunks = [h.content for h in hits if h.content]
        return RetrievalResult(
            context=chunks_only_context(chunks),
            sources=source_names([h.doc_id for h in hits]),
            hits=hits,
        )
