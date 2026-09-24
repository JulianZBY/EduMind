"""LLM 工厂：按 settings.llm_provider 在方言注册表里选构造器。

新增一家 OpenAI 兼容服务商 = 往 DIALECTS 加一条预设（或直接填 LLM_BASE_URL /
LLM_MODEL / LLM_API_KEY 覆盖），调用方无需改动。
"""
from collections.abc import Callable
from functools import lru_cache, partial

from app.config import Settings, settings
from app.core.dialects import DIALECTS
from app.core.llm.base import LLMProvider
from app.core.llm.providers.openai_compat import OpenAICompatProvider
from app.core.llm.providers.stub import StubProvider
from app.core.registry import build, register

LLM_BUILDERS: dict[str, Callable[[Settings], LLMProvider]] = {}


def _from_dialect(name: str, cfg: Settings) -> LLMProvider:
    dialect = DIALECTS[name]
    api_key = cfg.llm_api_key or getattr(cfg, dialect.api_key_field)
    if not api_key:
        raise ValueError(f"{dialect.api_key_field.upper()} 未配置")
    return OpenAICompatProvider(
        base_url=cfg.llm_base_url or dialect.base_url,
        model=cfg.llm_model or dialect.chat_model,
        api_key=api_key,
        vision_model=cfg.llm_vision_model or dialect.vision_model,
    )


register(LLM_BUILDERS, "stub", lambda cfg: StubProvider())
for _dialect_name in DIALECTS:
    register(LLM_BUILDERS, _dialect_name, partial(_from_dialect, _dialect_name))


@lru_cache
def get_llm() -> LLMProvider:
    return build(LLM_BUILDERS, settings.llm_provider, settings, "LLM provider")
