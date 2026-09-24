"""本地确定性兜底向量：字符 1/2-gram 的 crc32 哈希袋 + L2 归一化。

云端 embedding 不可用（未配 Key）时的底线实现：可跑通、维度稳定，但语义检索
与近名冲突预筛质量降级。必须跨进程稳定（内置 hash() 带 PYTHONHASHSEED 随机
种子，不可用）。
"""

import zlib

from app.core.embedding.base import Embedder

DEFAULT_DIM = 64


class HashEmbedder(Embedder):
    name = "hash"

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        grams = {text[i : i + 2] for i in range(max(len(text) - 1, 0))} | set(text)
        for g in grams:
            vec[zlib.crc32(g.encode("utf-8")) % self.dim] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0:  # 空文本：给一个固定非零向量，避免归一化除零
            vec[0] = 1.0
            return vec
        return [v / norm for v in vec]
