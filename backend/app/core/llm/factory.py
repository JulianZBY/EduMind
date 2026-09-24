"""Provider 工厂：按 settings.llm_provider 返回实例。"""

from functools import lru_cache

from app.config import settings
from app.core.llm.base import LLMProvider
from app.core.llm.providers.dashscope import DashScopeProvider
from app.core.llm.providers.deepseek import DeepSeekProvider
from app.core.llm.providers.stub import StubProvider


@lru_cache
def get_llm() -> LLMProvider:
    key = settings.llm_provider.lower()
    if key == "stub":
        return StubProvider()
    if key == "dashscope":
        if not settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        return DashScopeProvider(api_key=settings.dashscope_api_key)
    if key == "deepseek":
        if not settings.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY 未配置")
        return DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            embed_api_key=settings.siliconflow_api_key,
        )
    raise ValueError(f"未实现的 LLM provider: {settings.llm_provider}")
