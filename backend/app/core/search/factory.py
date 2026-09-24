"""搜索工厂：settings.search_provider（留空 = 有 BOCHA_API_KEY 用 bocha，否则 stub）。"""

from collections.abc import Callable
from functools import lru_cache

from app.config import Settings, settings
from app.core.registry import build, register
from app.core.search.base import WebSearch
from app.core.search.bocha import BochaSearch
from app.core.search.stub import StubSearch

SEARCH_BUILDERS: dict[str, Callable[[Settings], WebSearch]] = {}


def _bocha(cfg: Settings) -> WebSearch:
    if not cfg.bocha_api_key:
        raise ValueError("BOCHA_API_KEY 未配置")
    return BochaSearch(key=cfg.bocha_api_key)


def _auto(cfg: Settings) -> WebSearch:
    return _bocha(cfg) if cfg.bocha_api_key else StubSearch()


register(SEARCH_BUILDERS, "stub", lambda cfg: StubSearch())
register(SEARCH_BUILDERS, "bocha", _bocha)
register(SEARCH_BUILDERS, "auto", _auto)


@lru_cache
def get_search() -> WebSearch:
    provider = settings.search_provider.strip().lower()
    if not provider:
        return _auto(settings)
    return build(SEARCH_BUILDERS, provider, settings, "网络搜索 provider")
