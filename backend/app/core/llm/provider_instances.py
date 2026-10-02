"""供应商实例（多供应商并存）：设置页「添加供应商」产生的每一条，可同时配置多家。

一条实例 = 方言（目录家或自定义 OpenAI 兼容）+ 自己的 Key + 可选的地址/模型覆盖。
解析按「实例行 → OpenAICompatProvider」：预设来自方言，覆盖来自实例行，两者合成即生效值。
缓存与失效：构造结果按（实例 id + updated_at + 模型覆盖）缓存；任何实例行的改动都会改变
updated_at，下一次解析自然换新实例。`settings_store.invalidate_capabilities()` 也会整体清空
这里的缓存——它是全进程唯一的缓存失效入口。
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.dialects import DIALECTS
from app.core.llm.providers.openai_compat import OpenAICompatProvider
from app.db import SessionLocal
from app.db.models import LLMProviderInstance, ProviderModel


def list_instances(db: Session | None = None) -> list[LLMProviderInstance]:
    """全部供应商实例（按创建时间排，先加的在前——「第一条即默认」的次序依据）。"""
    if db is not None:
        return list(db.query(LLMProviderInstance).order_by(LLMProviderInstance.created_at).all())
    with SessionLocal() as session:
        return list_instances(session)


def get_instance(instance_id: str, db: Session | None = None) -> LLMProviderInstance | None:
    if db is not None:
        return db.get(LLMProviderInstance, instance_id)
    with SessionLocal() as session:
        return get_instance(instance_id, session)


def instance_dialects() -> dict[str, str]:
    """实例 id → 方言 id 的映射（跨字段校验与设置页回读用）。"""
    return {row.id: row.provider for row in list_instances()}


def effective_base_url(instance: LLMProviderInstance) -> str:
    """实例的生效地址：覆盖优先，其次方言预设（自定义服务没有预设，必须填覆盖）。"""
    if instance.base_url:
        return instance.base_url
    return DIALECTS.get(instance.provider).base_url if instance.provider in DIALECTS else ""


def effective_model(instance: LLMProviderInstance) -> str:
    """实例的默认模型：覆盖优先，其次方言预设的对话模型。"""
    if instance.model:
        return instance.model
    dialect = DIALECTS.get(instance.provider)
    return dialect.chat_model if dialect else ""


def _resolve(instance: LLMProviderInstance, model_override: str = "") -> object:
    """把一条实例行构造成对话能力：全部走 OpenAI 兼容实现（目录家与自定义服务同构）。"""
    base_url = effective_base_url(instance)
    if not base_url:
        raise ValueError(f"「{instance.label}」没有可用地址：自定义服务要填服务商地址（base_url）")
    if not instance.api_key:
        raise ValueError(f"「{instance.label}」还没有粘贴 API Key")
    model = model_override or effective_model(instance)
    dialect = DIALECTS.get(instance.provider)
    return OpenAICompatProvider(
        base_url=base_url,
        model=model,
        api_key=instance.api_key,
        vision_model=dialect.vision_model if dialect else "",
    )


def _ts(value: datetime | None) -> str:
    return value.isoformat() if value else ""


@lru_cache(maxsize=64)
def _cached_resolve(
    instance_id: str, updated_at: str, model_override: str
) -> tuple[bool, object, str]:
    """带缓存的解析：ready=false 时把可读原因一并缓存（设置页就绪探针与真实调用同一结果）。"""
    instance = get_instance(instance_id)
    if instance is None:
        return False, None, f"供应商实例不存在：{instance_id}"
    try:
        return True, _resolve(instance, model_override), ""
    except Exception as error:  # noqa: BLE001 - 原因原样转述给教师
        return False, None, str(error)


def provider_of_instance(instance_id: str, model_override: str = "") -> object:
    """按实例 id 取对话能力（缓存）；实例不在了/构造不起来时抛可读错误。"""
    instance = get_instance(instance_id)
    if instance is None:
        raise ValueError(f"供应商实例不存在：{instance_id}")
    ready, provider, reason = _cached_resolve(instance_id, _ts(instance.updated_at), model_override)
    if not ready:
        raise ValueError(reason)
    return provider


def probe_instance(instance_id: str) -> tuple[bool, str]:
    """就绪探针：只判断「现在能不能用」，与 `catalog.probe` 同口径。"""
    instance = get_instance(instance_id)
    if instance is None:
        return False, f"供应商实例不存在：{instance_id}"
    ready, _, reason = _cached_resolve(instance_id, _ts(instance.updated_at), "")
    return ready, reason


def default_instance() -> LLMProviderInstance | None:
    """默认供应商实例行；没设默认（或指向的行没了）时返回 None，调用方回落 legacy 路径。"""
    from app.config import settings  # 局部导入避免环：config 不依赖本模块

    instance_id = (settings.default_provider_instance or "").strip()
    if not instance_id:
        return None
    return get_instance(instance_id)


def default_provider() -> object:
    """默认实例的对话能力：模型用全局默认选择（llm_model，未选则实例/方言预设）；
    没有默认实例时抛 KeyError 由调用方回落 legacy 单供应商路径。"""
    from app.config import settings  # 局部导入避免环：config 不依赖本模块

    instance = default_instance()
    if instance is None:
        raise KeyError("no default provider instance")
    return provider_of_instance(instance.id, model_override=(settings.llm_model or ""))


def clear_instance_cache() -> None:
    _cached_resolve.cache_clear()


# ---- 模型清单（添加/刷新时从服务商 `GET /v1/models` 拉取并缓存）----

FETCH_TIMEOUT_SECONDS = 10.0


def fetch_model_ids(instance: LLMProviderInstance) -> list[str]:
    """调该实例的 `GET {base_url}/models`（OpenAI 兼容）拉取模型 id 清单。

    拉不到（网络问题 / 服务商不提供 / 超时）时抛可读错误，调用方把它回给教师。
    """
    base_url = effective_base_url(instance)
    if not base_url or not instance.api_key:
        raise ValueError("地址或 Key 不全，拉不了模型清单")
    url = base_url.rstrip("/") + "/models"
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {instance.api_key}"},
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise TypeError("服务商返回的模型清单读不懂（没有 data 列表）")
    models = sorted(
        {
            row.get("id")
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
    )
    if not models:
        raise ValueError("服务商返回的模型清单是空的")
    return models


def store_models(db: Session, instance_id: str, model_ids: list[str]) -> None:
    """整表替换该实例的模型清单（幂等：先清后写）。"""
    db.execute(delete(ProviderModel).where(ProviderModel.instance_id == instance_id))
    for model_id in model_ids:
        db.add(ProviderModel(instance_id=instance_id, model_id=model_id))
    db.commit()


def models_of_instance(instance_id: str, db: Session | None = None) -> list[str]:
    """该实例缓存的模型清单（按 id 排序）。"""
    if db is not None:
        rows = db.query(ProviderModel).filter(ProviderModel.instance_id == instance_id).all()
        return sorted(row.model_id for row in rows)
    with SessionLocal() as session:
        return models_of_instance(instance_id, session)


def models_pool(db: Session | None = None) -> list[tuple[str, str, str]]:
    """统一模型池：(实例 id, 实例名, 模型 id)——设置页全局默认与任务级下拉的唯一出处。"""
    instances = {row.id: row.label for row in list_instances(db)}
    if db is not None:
        rows = db.query(ProviderModel).order_by(ProviderModel.model_id).all()
    else:
        with SessionLocal() as session:
            rows = session.query(ProviderModel).order_by(ProviderModel.model_id).all()
    return [
        (row.instance_id, instances.get(row.instance_id, row.instance_id), row.model_id)
        for row in rows
        if row.instance_id in instances
    ]


def refresh_models(instance_id: str, db: Session | None = None) -> tuple[bool, str, int]:
    """拉取并缓存该实例的模型清单。返回 (成功?, 失败原因, 模型数)；失败时保持旧清单不动，
    并把原因写到实例行的 `models_error`（设置页据此提示「拉取失败，可手动填写或刷新」）。"""
    instance = get_instance(instance_id, db)
    if instance is None:
        return False, f"供应商实例不存在：{instance_id}", 0
    try:
        model_ids = fetch_model_ids(instance)
    except Exception as error:  # noqa: BLE001 - 原因原样转述给教师
        if db is not None:
            instance.models_error = str(error)
            db.commit()
        else:
            with SessionLocal() as session:
                row = session.get(LLMProviderInstance, instance_id)
                row.models_error = str(error)
                session.commit()
        return False, str(error), 0
    if db is not None:
        instance.models_error = ""
        db.commit()
        store_models(db, instance_id, model_ids)
    else:
        with SessionLocal() as session:
            row = session.get(LLMProviderInstance, instance_id)
            row.models_error = ""
            session.commit()
            store_models(session, instance_id, model_ids)
    return True, "", len(model_ids)
