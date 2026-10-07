"""策略组合：主策略失败退到备选策略（默认 mineru 失败退 pypdf）。"""

import logging

from app.core.parser.base import PdfParser, PdfStrategyNotConfigured

logger = logging.getLogger(__name__)


class FallbackPdfParser(PdfParser):
    name = "fallback"

    def __init__(self, primary: PdfParser, backup: PdfParser) -> None:
        self.primary = primary
        self.backup = backup

    async def parse(self, pdf_path: str) -> str:
        try:
            return await self.primary.parse(pdf_path)
        except PdfStrategyNotConfigured as exc:
            # 主策略没配置（默认档下没填 MinerU token 就是这条路）：这是预期内的回退，
            # 记一行即可。带堆栈的话每解析一份 PDF 就刷一屏，真正的异常会被淹没。
            logger.info(
                "PDF 主策略 %s 未配置（%s），改用 %s", self.primary.name, exc, self.backup.name
            )
        except Exception:
            logger.warning(
                "PDF 主策略 %s 失败，退到 %s", self.primary.name, self.backup.name, exc_info=True
            )
        # 备选策略在 except 块之外调用：它自己失败时，异常不会挂上主策略的异常链。
        # 否则一份坏 PDF 的报错里会先出现一段无关的「主策略未配置」堆栈，把人引向错误的方向。
        return await self.backup.parse(pdf_path)
