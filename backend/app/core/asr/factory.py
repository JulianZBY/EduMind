"""Transcriber 工厂：按 settings.asr_provider 返回实例。"""

from functools import lru_cache

from app.config import settings
from app.core.asr.base import Transcriber
from app.core.asr.paraformer import ParaformerTranscriber
from app.core.asr.stub import StubTranscriber


@lru_cache
def get_transcriber() -> Transcriber:
    key = settings.asr_provider.lower()
    if key == "stub":
        return StubTranscriber()
    if key == "paraformer":
        if not settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        return ParaformerTranscriber(api_key=settings.dashscope_api_key)
    raise ValueError(f"未实现的 ASR provider: {settings.asr_provider}")
