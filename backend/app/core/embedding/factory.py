"""Embedder 工厂：按 settings.embedding_provider 选实现。

留空（默认）时跟随对话口径：
- LLM_PROVIDER 指到有 embedding 的方言（千问 / 智谱 / 硅基流动）→ 同方言 embedding；
- LLM_PROVIDER=deepseek（官方不提供 embedding）→ 有硅基流动 Key 走它，否则本地 hash 兜底；
- 未配置对话供应商 → 本地 hash 兜底（真实算法，非假数据；语义检索质量降级）。
显式 EMBEDDING_PROVIDER 覆盖以上推断（hash / openai / qwen / siliconflow）。
"""

from collections.abc import Callable
from functools import lru_cache, partial

from app.config import Settings, settings
from app.core import provider_config
from app.core.dialects import DIALECTS
from app.core.embedding.base import Embedder
from app.core.embedding.hash import HashEmbedder
from app.core.embedding.openai_compat import OpenAICompatEmbedder
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
    field_key = getattr(cfg, dialect.api_key_field) if dialect.api_key_field else ""
    api_key = cfg.embedding_api_key or field_key or provider_config.env_api_key(dialect)
    if not api_key:
        hint = dialect.api_key_field.upper() if dialect.api_key_field else (dialect.api_key_env or "API Key")
        raise ValueError(f"{hint} 未配置")
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
    if name == "deepseek" and cfg.siliconflow_api_key:
        return _from_dialect("siliconflow", cfg)
    # 未配置对话供应商 / 方言不提供 embedding：本地 hash 兜底（真实算法，检索质量降级）
    return HashEmbedder()


register(EMBEDDING_BUILDERS, "hash", lambda cfg: HashEmbedder())
register(EMBEDDING_BUILDERS, "openai", _explicit)
register(EMBEDDING_BUILDERS, "auto", _auto)
provider_config.ensure_merged()  # 配置声明的家先进方言表，再据表注册
for _dialect_name, _dialect in DIALECTS.items():
    if _dialect.embed_model:
        register(EMBEDDING_BUILDERS, _dialect_name, partial(_from_dialect, _dialect_name))


def _register_if_configured(provider: str) -> None:
    """配置声明的家可能在本次 import 之后才并进方言表：用到时补注册一次（幂等）。"""
    dialect = DIALECTS.get(provider)
    if provider in EMBEDDING_BUILDERS or dialect is None or not dialect.embed_model:
        return
    register(EMBEDDING_BUILDERS, provider, partial(_from_dialect, provider))


@lru_cache
def get_embedder() -> Embedder:
    provider = settings.embedding_provider.strip().lower()
    if not provider:
        return _auto(settings)
    _register_if_configured(provider)
    return build(EMBEDDING_BUILDERS, provider, settings, "embedding provider")
