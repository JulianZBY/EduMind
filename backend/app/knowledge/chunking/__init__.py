"""分块策略：接口（base）+ 按配置选择的工厂（factory）+ 实现。

既有 `chunk_text` 逻辑收编为 `paragraph` 一格实现，调用方改用
`get_chunker()` 后换分块方式只改配置（ADR-0003）；`chunk_text` 仍在此导出，
供既有调用与单元测试直接用纯函数。
"""

from app.knowledge.chunking.base import Chunker
from app.knowledge.chunking.factory import (
    CHUNKER_BUILDERS,
    DEFAULT_CHUNKER,
    get_chunker,
)
from app.knowledge.chunking.paragraph import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    ParagraphChunker,
    chunk_text,
)

__all__ = [
    "CHUNKER_BUILDERS",
    "DEFAULT_CHUNKER",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
    "Chunker",
    "ParagraphChunker",
    "chunk_text",
    "get_chunker",
]
