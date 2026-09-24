"""向量 + 图谱融合检索（默认档）：命中分块经来源资料定位知识点，沿图谱边拉邻接子图。"""

import logging

from app.knowledge.retrieval.base import RetrievalResult, Retriever
from app.knowledge.retrieval.context import assemble_context, chunks_only_context
from app.knowledge.retrieval.search import intent_query, search_hits, source_names

logger = logging.getLogger(__name__)


def _fused_nodes(doc_ids: list[str]) -> list[dict]:
    """命中分块的来源资料 → 知识点 → 图谱邻接子图（按知识递进顺序）。"""
    from app.knowledge.graph import neighborhood, nodes_for_docs

    return neighborhood([n["id"] for n in nodes_for_docs(doc_ids)])


class VectorGraphRetriever(Retriever):
    """融合档：片段优先，附上沿图谱邻接拉到的知识点；图谱拉取失败降级为仅片段。"""

    name = "vector_graph"

    async def retrieve(self, intent, top_k: int = 5, reference_doc_ids=None) -> RetrievalResult:
        query = intent_query(intent)
        if not query:
            return RetrievalResult.empty()
        hits = await search_hits(query, top_k, reference_doc_ids)
        if hits is None:
            return RetrievalResult.empty()
        chunks = [h.content for h in hits if h.content]
        nodes: list[dict] = []
        try:
            nodes = _fused_nodes([h.doc_id for h in hits])
            context = assemble_context(chunks, nodes)
        except Exception:
            logger.warning("图谱邻接子图拉取失败，降级为仅片段上下文", exc_info=True)
            return RetrievalResult(
                context=chunks_only_context(chunks),
                sources=source_names([h.doc_id for h in hits]),
                hits=hits,
            )
        return RetrievalResult(
            context=context,
            sources=source_names([h.doc_id for h in hits]),
            hits=hits,
            graph_nodes=nodes,
        )
