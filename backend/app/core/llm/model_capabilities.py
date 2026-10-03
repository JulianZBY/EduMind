"""模型级能力口径：目录声明 + 实例手动标注；未知模型保持未知，不猜测模型名称。"""

from typing import Literal

from app.core.errors import ProviderNotConfigured

ModelCapability = Literal["text", "vision", "embedding"]
CAPABILITY_ORDER = ("text", "vision", "embedding")


def require_capability(model: str, capability: str, known: tuple[str, ...]) -> None:
    if known and capability not in known:
        raise ProviderNotConfigured(
            f"模型「{model}」未标注 {capability} 能力：请到设置页选择或标注合适模型。"
        )


def vision_model_for(
    provider: str,
    model: str,
    *,
    selected: bool = False,
    override: str = "",
    overrides: dict | None = None,
) -> str:
    from app.core.dialects import DIALECTS

    if override:
        return override
    if selected and "vision" in capability_map(provider, overrides).get(model, ()):
        return model
    dialect = DIALECTS.get(provider)
    return dialect.vision_model if dialect else ""


def capability_map(provider: str, overrides: dict | None = None) -> dict[str, tuple[str, ...]]:
    # catalog 导入工厂，因此在使用时读取目录，避免 import 环。
    from app.core.catalog import PROVIDERS

    spec = PROVIDERS.get(provider)
    models: dict[str, set[str]] = {}
    if spec is not None:
        for ids, caps in (
            (spec.chat_models, ("text",)),
            (spec.vision_models, ("text", "vision")),
            (spec.embed_models, ("embedding",)),
        ):
            for model in ids:
                models.setdefault(model, set()).update(caps)
    for model, caps in (overrides or {}).items():
        models[model] = set(caps)
    return {
        model: tuple(cap for cap in CAPABILITY_ORDER if cap in caps)
        for model, caps in models.items()
    }


def model_info(provider: str, model: str, overrides: dict | None = None) -> dict:
    caps = capability_map(provider, overrides).get(model, ())
    source = "manual" if model in (overrides or {}) else ("catalog" if caps else "unknown")
    return {"model_id": model, "capabilities": list(caps), "source": source}
