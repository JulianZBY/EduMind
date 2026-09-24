"""PDF 解析抽象：云端精确解析与本地文本层抽取共用一个出口。"""

from abc import ABC, abstractmethod


class PdfParser(ABC):
    """PDF → Markdown / 纯文本。"""

    name: str = "base"

    @abstractmethod
    async def parse(self, pdf_path: str) -> str:
        """解析 PDF，返回文本（策略失败时抛异常，由调用方或组合策略处理）。"""
