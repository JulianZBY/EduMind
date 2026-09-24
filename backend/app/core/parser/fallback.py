"""策略组合：主策略失败退到备选策略（默认 mineru 失败退 pypdf）。"""

import logging

from app.core.parser.base import PdfParser

logger = logging.getLogger(__name__)


class FallbackPdfParser(PdfParser):
    name = "fallback"

    def __init__(self, primary: PdfParser, backup: PdfParser) -> None:
        self.primary = primary
        self.backup = backup

    async def parse(self, pdf_path: str) -> str:
        try:
            return await self.primary.parse(pdf_path)
        except Exception:
            logger.warning(
                "PDF 主策略 %s 失败，退到 %s", self.primary.name, self.backup.name, exc_info=True
            )
            return await self.backup.parse(pdf_path)
