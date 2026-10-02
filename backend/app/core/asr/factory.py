"""Transcriber 工厂：按 settings.asr_provider 在注册表里选实现（留空 = 自动）。

自动档：有百炼 Key（ASR_API_KEY）走 paraformer，否则抛 `ProviderNotConfigured`
（paraformer 是阿里云百炼的服务，千问 MaaS 不提供且 Key 不通用；没有假转写兜底）。
"""

from collections.abc import Callable
from functools import lru_cache

from app.config import Settings, settings
from app.core.asr.base import Transcriber
from app.core.asr.paraformer import ParaformerTranscriber
from app.core.errors import ProviderNotConfigured
from app.core.registry import build, register

ASR_BUILDERS: dict[str, Callable[[Settings], Transcriber]] = {}

NOT_CONFIGURED_MESSAGE = (
    "语音转写未配置：录音转写需要阿里云百炼的 paraformer（千问 MaaS 不提供）。"
    "到「设置 → 能力实现」把语音转写指到 paraformer 并粘贴百炼 Key，或在 .env 配置 ASR_API_KEY。"
)


def _paraformer(cfg: Settings) -> Transcriber:
    if not cfg.asr_api_key:
        raise ValueError("ASR_API_KEY 未配置（需要阿里云百炼的 Key，千问 MaaS 的 Key 不通用）")
    return ParaformerTranscriber(api_key=cfg.asr_api_key)


def _auto(cfg: Settings) -> Transcriber:
    if cfg.asr_api_key:
        return _paraformer(cfg)
    raise ProviderNotConfigured(NOT_CONFIGURED_MESSAGE)


register(ASR_BUILDERS, "paraformer", _paraformer)
register(ASR_BUILDERS, "auto", _auto)


@lru_cache
def get_transcriber() -> Transcriber:
    provider = settings.asr_provider.strip().lower()
    if not provider:
        return _auto(settings)
    return build(ASR_BUILDERS, provider, settings, "ASR provider")
