"""网络搜索能力：接口 + 按配置选择的工厂。未配置博查 Key 时抛 ProviderNotConfigured（无占位假结果）。"""

from abc import ABC, abstractmethod


class WebSearch(ABC):
    """联网检索：返回 [{title, url, snippet}]。"""

    name: str = "base"

    @abstractmethod
    async def search(self, query: str, count: int = 5, summary: bool = False) -> list[dict]:
        """检索 query，返回至多 count 条结果。"""
