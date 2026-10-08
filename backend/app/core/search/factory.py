"""搜索工厂：settings.search_provider（留空 = 有 BOCHA_API_KEY 用 bocha，否则未配置）。

无 Key 时抛 `ProviderNotConfigured`（不再返回占位假结果）：题库的「网络」来源
会得到明确的「去配置博查 Key」引导。
"""

from collections.abc import Callable
from functools import lru_cache

from app.config import Settings, settings
from app.core.errors import ProviderNotConfigured
from app.core.registry import build, register
from app.core.search.base import WebSearch
from app.core.search.bocha import BochaSearch

SEARCH_BUILDERS: dict[str, Callable[[Settings], WebSearch]] = {}

NOT_CONFIGURED_MESSAGE = "网络搜索未配置：到「设置 → 能力实现」把网络搜索指到博查，或在 .env 配置 BOCHA_API_KEY。"


def _bocha(cfg: Settings) -> WebSearch:
    if not cfg.bocha_api_key:
        raise ProviderNotConfigured(NOT_CONFIGURED_MESSAGE)
    return BochaSearch(key=cfg.bocha_api_key)


def _auto(cfg: Settings) -> WebSearch:
    if cfg.bocha_api_key:
        return _bocha(cfg)
    raise ProviderNotConfigured(NOT_CONFIGURED_MESSAGE)


register(SEARCH_BUILDERS, "bocha", _bocha)
register(SEARCH_BUILDERS, "auto", _auto)


@lru_cache
def get_search() -> WebSearch:
    provider = settings.search_provider.strip().lower()
    if not provider:
        return _auto(settings)
    return build(SEARCH_BUILDERS, provider, settings, "网络搜索 provider")
