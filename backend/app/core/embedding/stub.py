"""桩向量化器：无 Key 可跑，返回可预测假向量，供骨架阶段联调与测试。"""

from app.core.embedding.base import Embedder

STUB_DIM = 8


class StubEmbedder(Embedder):
    name = "stub"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 确定性假向量：以文本长度为特征（len * 1.0 转浮点，不引入可抛出转换）
        return [[len(t) * 1.0] * STUB_DIM for t in texts]
