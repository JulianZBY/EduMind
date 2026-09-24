"""段落边界分块：收编前的分块逻辑（按语义边界切分，保留上下文重叠）。"""

import re

from app.knowledge.chunking.base import Chunker

# 中文教学文档的合理切分粒度
DEFAULT_CHUNK_SIZE = 500  # 字符
DEFAULT_OVERLAP = 100  # 字符


def _split_paragraphs(text: str) -> list[str]:
    """按空行/标题边界切分为段落块。"""
    parts = re.split(r"\n\s*\n|\n(?=#{1,6}\s)", text)
    return [p.strip() for p in parts if p.strip()]


def _hard_split(paragraph: str, chunk_size: int) -> list[str]:
    """超长段落按字符硬切。"""
    return [paragraph[i : i + chunk_size] for i in range(0, len(paragraph), chunk_size)]


def chunk_text(
    text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    """切分为带重叠的 chunk。

    - 优先按段落边界合并，避免切断语义；
    - 超出 chunk_size 的单段按字符硬切；
    - 相邻 chunk 保留 overlap 字符重叠，避免上下文断裂。
    """
    if not text.strip():
        return []
    chunks: list[str] = []
    current = ""
    for para in _split_paragraphs(text):
        for piece in _hard_split(para, chunk_size) if len(para) > chunk_size else [para]:
            if current and len(current) + len(piece) > chunk_size:
                chunks.append(current)
                current = current[-overlap:] if overlap > 0 else ""
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


class ParagraphChunker(Chunker):
    """按段落/标题边界分块（其中一格实现）：切法与切分粒度即收编前的行为。"""

    name = "paragraph"

    def __init__(
        self, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP
    ) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        return chunk_text(text, chunk_size=self.chunk_size, overlap=self.overlap)
