"""向量化抽象：与对话 provider 解耦（两者常来自不同服务商、不同 Key）。"""

from abc import ABC, abstractmethod


class Embedder(ABC):
    """文本向量化。"""

    name: str = "base"

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """把一批文本转成向量：与输入同序、同长度，维度由实现决定。"""
