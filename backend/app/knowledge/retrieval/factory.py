"""Retriever 工厂：按 settings.retrieval_strategy 选实现（默认 = 收编前的向量 + 图谱融合）。"""

from collections.abc import Callable
from functools import lru_cache

from app.config import Settings, settings
from app.core.registry import build, register
from app.knowledge.retrieval.base import Retriever
from app.knowledge.retrieval.vector import VectorRetriever
from app.knowledge.retrieval.vector_graph import VectorGraphRetriever

RETRIEVER_BUILDERS: dict[str, Callable[[Settings], Retriever]] = {}

register(RETRIEVER_BUILDERS, "vector", lambda cfg: VectorRetriever())
register(RETRIEVER_BUILDERS, "vector_graph", lambda cfg: VectorGraphRetriever())

# 默认档：留空或未配置时按它取实现（收编前行为：向量 + 图谱邻接融合）
DEFAULT_RETRIEVER = "vector_graph"


@lru_cache
def get_retriever() -> Retriever:
    name = settings.retrieval_strategy.strip().lower() or DEFAULT_RETRIEVER
    return build(RETRIEVER_BUILDERS, name, settings, "检索策略")
