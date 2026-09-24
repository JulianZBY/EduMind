"""Chunker 工厂：按 settings.chunk_strategy 选实现（默认 = 收编前的段落边界分块）。"""

from collections.abc import Callable
from functools import lru_cache

from app.config import Settings, settings
from app.core.registry import build, register
from app.knowledge.chunking.base import Chunker
from app.knowledge.chunking.paragraph import ParagraphChunker

CHUNKER_BUILDERS: dict[str, Callable[[Settings], Chunker]] = {}

register(CHUNKER_BUILDERS, "paragraph", lambda cfg: ParagraphChunker())

# 默认档：留空或未配置时按它取实现（收编前行为）
DEFAULT_CHUNKER = "paragraph"


@lru_cache
def get_chunker() -> Chunker:
    name = settings.chunk_strategy.strip().lower() or DEFAULT_CHUNKER
    return build(CHUNKER_BUILDERS, name, settings, "分块策略")
