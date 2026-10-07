"""PDF 解析抽象：云端精确解析与本地文本层抽取共用一个出口。"""

from abc import ABC, abstractmethod


class PdfParser(ABC):
    """PDF → Markdown / 纯文本。"""

    name: str = "base"

    @abstractmethod
    async def parse(self, pdf_path: str) -> str:
        """解析 PDF，返回文本（策略失败时抛异常，由调用方或组合策略处理）。"""


class PdfStrategyNotConfigured(ValueError):
    """某个 PDF 解析策略缺少必需的配置（例如 MinerU 没填 token）。

    继承 ValueError 以保持原有的异常口径；单独成类是为了让组合策略把
    「没配置所以回退」和「配置了但调用失败」区分开：前者是预期内的路径，不该带堆栈告警。
    """
