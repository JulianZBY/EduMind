"""分块策略接口：把一份资料的解析文本切成可检索的分块（CONTEXT「分块」）。"""

from abc import ABC, abstractmethod


class Chunker(ABC):
    """分块策略：一个实现一种切法，按配置名选择（ADR-0003）。"""

    name: str = ""

    @abstractmethod
    def chunk(self, text: str) -> list[str]:
        """切分为可检索分块，返回顺序即入库顺序；空文本返回空列表。"""
