"""PDF 解析工厂：按 settings.pdf_strategy 三选一。

mineru（仅云端）/ pypdf（仅本地）/ mineru_then_pypdf（默认，云端失败退本地）。
换策略只改配置；调用方（知识库解析层）只认 PdfParser 接口。
"""

from collections.abc import Callable
from functools import lru_cache

from app.config import Settings, settings
from app.core.parser.base import PdfParser
from app.core.parser.fallback import FallbackPdfParser
from app.core.parser.mineru import MinerUParser
from app.core.parser.pypdf import PypdfParser
from app.core.registry import build, register

PDF_BUILDERS: dict[str, Callable[[Settings], PdfParser]] = {}


def _mineru_only(cfg: Settings) -> PdfParser:
    if not cfg.mineru_token:
        raise ValueError("MINERU_TOKEN 未配置，且 PDF_STRATEGY=mineru 无兜底策略")
    return MinerUParser(token=cfg.mineru_token)


register(PDF_BUILDERS, "mineru", _mineru_only)
register(PDF_BUILDERS, "pypdf", lambda cfg: PypdfParser())
# 缺 token 时不在这里拦：让 MinerUParser.parse 抛错，组合策略才好退到 pypdf
register(
    PDF_BUILDERS,
    "mineru_then_pypdf",
    lambda cfg: FallbackPdfParser(MinerUParser(token=cfg.mineru_token), PypdfParser()),
)


@lru_cache
def get_pdf_parser() -> PdfParser:
    return build(PDF_BUILDERS, settings.pdf_strategy, settings, "PDF 解析策略")
