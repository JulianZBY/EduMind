"""LLM 工厂：默认供应商实例（多供应商）优先，其次 legacy 单供应商（llm_provider 方言注册表）。

未配置任何供应商时抛 `ProviderNotConfigured`（产品里没有假数据兜底）：调用方 /
全局异常处理器把它转成「去设置页配置」的引导，而不是返回占位内容。
模型档位由任务路由（task_routing）按「实例 + 模型」注入。
"""

from collections.abc import Callable
from functools import lru_cache, partial

from app.config import Settings, settings
from app.core import provider_config
from app.core.dialects import DIALECTS
from app.core.errors import ProviderNotConfigured
from app.core.llm import provider_instances
from app.core.llm.base import LLMProvider
from app.core.llm.model_capabilities import capability_map, require_capability, vision_model_for
from app.core.llm.providers.openai_compat import OpenAICompatProvider
from app.core.registry import build, register

NOT_CONFIGURED_MESSAGE = (
    "还没有配置模型供应商：到「设置 → 添加供应商」选一家并粘贴 Key 后即可使用。"
)

LLM_BUILDERS: dict[str, Callable[[Settings], LLMProvider]] = {}


def _from_dialect(name: str, cfg: Settings) -> LLMProvider:
    dialect = DIALECTS[name]
    field_key = getattr(cfg, dialect.api_key_field) if dialect.api_key_field else ""
    api_key = cfg.llm_api_key or field_key or provider_config.env_api_key(dialect)
    if not api_key:
        hint = (
            dialect.api_key_field.upper()
            if dialect.api_key_field
            else (dialect.api_key_env or "API Key")
        )
        raise ProviderNotConfigured(f"{hint} 未配置：请到设置页配置模型供应商。")
    model = cfg.llm_model or dialect.chat_model
    caps = capability_map(name)
    require_capability(model, "text", caps.get(model, ()))
    return OpenAICompatProvider(
        base_url=cfg.llm_base_url or dialect.base_url,
        model=model,
        api_key=api_key,
        vision_model=vision_model_for(
            name, model, selected=bool(cfg.llm_model), override=cfg.llm_vision_model
        ),
        model_capabilities=caps,
    )


def _custom(cfg: Settings) -> LLMProvider:
    """自定义 OpenAI 兼容服务（供应商目录之外）：base_url + 模型 ID + Key 三件齐全才成立。

    与方言预设的区别：没有预设地址、没有默认模型——填什么就是什么，模型 ID 不限目录。
    """
    if not cfg.llm_base_url:
        raise ProviderNotConfigured("LLM_BASE_URL 未配置：请到设置页填写服务商地址。")
    if not cfg.llm_model:
        raise ProviderNotConfigured("LLM_MODEL 未配置：请到设置页填写模型。")
    if not cfg.llm_api_key:
        raise ProviderNotConfigured("LLM_API_KEY 未配置：请到设置页配置 Key。")
    return OpenAICompatProvider(
        base_url=cfg.llm_base_url,
        model=cfg.llm_model,
        api_key=cfg.llm_api_key,
        vision_model=cfg.llm_vision_model,
    )


provider_config.ensure_merged()  # 配置声明的家先进方言表，再据表注册
for _dialect_name in DIALECTS:
    register(LLM_BUILDERS, _dialect_name, partial(_from_dialect, _dialect_name))
register(LLM_BUILDERS, "custom", _custom)


def _register_if_configured(provider: str) -> None:
    """配置声明的家可能在本次 import 之后才并进方言表：用到时补注册一次（幂等）。"""
    if provider in LLM_BUILDERS or provider not in DIALECTS:
        return
    register(LLM_BUILDERS, provider, partial(_from_dialect, provider))


@lru_cache
def get_llm() -> LLMProvider:
    # 多供应商：设了默认实例就走实例解析（地址 / Key / 默认模型都在实例行上）。
    try:
        return provider_instances.default_provider()  # type: ignore[return-value]
    except KeyError:
        pass
    # legacy 单供应商：没配（空）就是「未配置」，不再回落任何假实现。
    provider = (settings.llm_provider or "").strip().lower()
    if not provider:
        raise ProviderNotConfigured(NOT_CONFIGURED_MESSAGE)
    _register_if_configured(provider)
    return build(LLM_BUILDERS, provider, settings, "LLM provider")
