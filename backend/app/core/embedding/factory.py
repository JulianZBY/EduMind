"""Embedder 工厂：按 settings.embedding_provider 选实现。

留空（默认）时跟随对话方言，保持既有 .env 语义：
- LLM_PROVIDER=stub → stub 向量（无 Key 底线）
- LLM_PROVIDER=dashscope / siliconflow → 同方言的 embedding
- LLM_PROVIDER=deepseek（官方不提供 embedding）→ 有硅基流动 Key 走它，否则本地 hash 兜底
显式 EMBEDDING_PROVIDER 覆盖以上推断（stub / hash / openai / dashscope / siliconflow）。
"""

from collections.abc import Callable
from functools import lru_cache, partial

from app.config import Settings, settings
from app.core.dialects import DIALECTS
from app.core.embedding.base import Embedder
from app.core.embedding.hash import HashEmbedder
from app.core.embedding.openai_compat import OpenAICompatEmbedder
from app.core.embedding.stub import StubEmbedder
from app.core.registry import build, register

EMBEDDING_BUILDERS: dict[str, Callable[[Settings], Embedder]] = {}


def _explicit(cfg: Settings) -> Embedder:
    """显式 openai 口径：换服务商只需填 EMBEDDING_BASE_URL / MODEL / API_KEY。"""
    if not cfg.embedding_base_url or not cfg.embedding_model:
        raise ValueError("EMBEDDING_BASE_URL / EMBEDDING_MODEL 未配置")
    if not cfg.embedding_api_key:
        raise ValueError("EMBEDDING_API_KEY 未配置")
    return OpenAICompatEmbedder(
        base_url=cfg.embedding_base_url,
        model=cfg.embedding_model,
        api_key=cfg.embedding_api_key,
        dimensions=cfg.embedding_dimensions,
    )


def _from_dialect(name: str, cfg: Settings) -> Embedder:
    dialect = DIALECTS[name]
    if not dialect.embed_model:
        raise ValueError(f"{dialect.name} 方言不提供 embedding，请改用 EMBEDDING_* 显式配置")
    api_key = cfg.embedding_api_key or getattr(cfg, dialect.api_key_field)
    if not api_key:
        raise ValueError(f"{dialect.api_key_field.upper()} 未配置")
    return OpenAICompatEmbedder(
        base_url=cfg.embedding_base_url or dialect.base_url,
        model=cfg.embedding_model or dialect.embed_model,
        api_key=api_key,
        dimensions=cfg.embedding_dimensions or dialect.embed_dimensions,
    )


def _auto(cfg: Settings) -> Embedder:
    name = cfg.llm_provider.strip().lower()
    if name in DIALECTS and DIALECTS[name].embed_model:
        return _from_dialect(name, cfg)
    if name == "deepseek":
        if cfg.siliconflow_api_key:
            return _from_dialect("siliconflow", cfg)
        return HashEmbedder()
    return StubEmbedder()


register(EMBEDDING_BUILDERS, "stub", lambda cfg: StubEmbedder())
register(EMBEDDING_BUILDERS, "hash", lambda cfg: HashEmbedder())
register(EMBEDDING_BUILDERS, "openai", _explicit)
register(EMBEDDING_BUILDERS, "auto", _auto)
for _dialect_name, _dialect in DIALECTS.items():
    if _dialect.embed_model:
        register(EMBEDDING_BUILDERS, _dialect_name, partial(_from_dialect, _dialect_name))


@lru_cache
def get_embedder() -> Embedder:
    provider = settings.embedding_provider.strip().lower()
    if not provider:
        return _auto(settings)
    return build(EMBEDDING_BUILDERS, provider, settings, "embedding provider")
