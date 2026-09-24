"""Transcriber 工厂：按 settings.asr_provider 在注册表里选实现。"""

from collections.abc import Callable
from functools import lru_cache

from app.config import Settings, settings
from app.core.asr.base import Transcriber
from app.core.asr.paraformer import ParaformerTranscriber
from app.core.asr.stub import StubTranscriber
from app.core.registry import build, register

ASR_BUILDERS: dict[str, Callable[[Settings], Transcriber]] = {}


def _paraformer(cfg: Settings) -> Transcriber:
    if not cfg.dashscope_api_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置")
    return ParaformerTranscriber(api_key=cfg.dashscope_api_key)


register(ASR_BUILDERS, "stub", lambda cfg: StubTranscriber())
register(ASR_BUILDERS, "paraformer", _paraformer)


@lru_cache
def get_transcriber() -> Transcriber:
    return build(ASR_BUILDERS, settings.asr_provider, settings, "ASR provider")
