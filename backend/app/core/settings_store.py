"""设置库（CONTEXT.md「设置」「引导默认」「掩码」）：配置库优先于 .env，写穿即时生效。

- **落库**：`app_settings` 表（key = Settings 字段名，value = 字符串化的值，见 `app/db/models.py`）。
  没写过（或被写空清除）的项一律回落**引导默认**——进程启动时 `.env` 的取值快照。
- **生效**：`write_settings()` 落库后立刻 `apply_stored_settings()`，把生效值同步进进程内 `settings`
  对象（既有调用点一行未改），再经 `invalidate_capabilities()` 清掉能力工厂缓存。全过程在请求内完成，
  **不需要重启**。
- **回读**：`mask_key()` 只给尾部若干位；任何响应都不含明文 Key（设置页表单也拿不到明文）。

校验（未知供应商 / 未知模型 / 格式不对的地址 / 未实现的实现）在 `write_settings()` 里先做，
不通过就抛 `SettingsError`，库内一行不动。
"""

import logging
from collections.abc import Mapping

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.core.asr.factory import get_transcriber
from app.core.catalog import (
    MANAGED_FIELDS,
    SOURCE_BOOTSTRAP,
    SOURCE_STORED,
    SettingsError,
    normalize,
    validate_patch,
)
from app.core.embedding.factory import get_embedder
from app.core.llm.factory import get_llm
from app.core.parser.factory import get_pdf_parser
from app.core.search.factory import get_search
from app.db import SessionLocal
from app.db.models import AppSetting
from app.knowledge.chunking.factory import get_chunker
from app.knowledge.retrieval.factory import get_retriever

logger = logging.getLogger(__name__)

# 引导默认：进程启动时 .env 的取值快照。设置库是覆盖层而不是唯一事实源，
# 所以「恢复引导默认」永远是删掉那一行，而不是把某个值写回去。
_BOOTSTRAP: dict[str, str] = {name: str(getattr(settings, name)) for name in MANAGED_FIELDS}


def bootstrap_value(name: str) -> str:
    """该设置项的 `.env` 引导值（进程启动时的快照）。"""
    return _BOOTSTRAP[name]


def value_of(name: str) -> str:
    """该设置项的当前生效值（写穿后即为设置库里的值，未写过则等于引导默认）。"""
    return str(getattr(settings, name) or "")


def current_values() -> dict[str, str]:
    """全部可改项的当前生效值（跨字段校验要用，例如模型落到哪个供应商的目录里）。"""
    return {name: value_of(name) for name in MANAGED_FIELDS}


def read_stored(db: Session) -> dict[str, str]:
    """设置库里已写入的项：没写过的项不在结果里，正是「回落引导默认」的判据。"""
    return {row.key: row.value for row in db.query(AppSetting).all()}


def read_stored_fresh() -> dict[str, str]:
    """同上，但自己开一个会话（启动同步与写穿后重放时用）。"""
    with SessionLocal() as db:
        return read_stored(db)


def source_of(name: str, stored: Mapping[str, str]) -> str:
    """该项当前的值从哪来：设置页写过 = 设置页，否则是引导默认。"""
    return SOURCE_STORED if name in stored else SOURCE_BOOTSTRAP


def mask_key(value: str) -> str:
    """掩码：只显示尾部若干位；太短的 Key 整串隐去，一个字都不回显。"""
    value = (value or "").strip()
    if not value:
        return ""
    return "••••" + (value[-4:] if len(value) > 8 else "")


def invalidate_capabilities() -> None:
    """**全进程唯一的缓存失效入口**：清掉全部能力工厂的 lru_cache。

    能力工厂按配置构造实现并缓存（票 02/03 的遗产），所以「写穿」= 写库 + 走这里清缓存。
    调用点各自的 `cache_clear()` 一律撤掉——漏清一处就会表现为「改了设置但不生效」。
    供应商实例的解析缓存也在这里清：实例行的任何改动（增删改 Key / 地址 / 模型）都经它生效。
    """
    from app.core.llm.provider_instances import clear_instance_cache

    for cached in (
        get_llm,
        get_embedder,
        get_transcriber,
        get_pdf_parser,
        get_search,
        get_retriever,
        get_chunker,
    ):
        cached.cache_clear()
    clear_instance_cache()

def apply_stored_settings() -> None:
    """把设置库的生效值同步进进程内 `settings`，并清掉能力工厂缓存。

    启动（`app/api/v1/settings.py` 注册的 startup 钩子）与写穿各调一次：
    没写过的项回落引导默认；存量值已不在目录里（例如目录换过）时回落引导默认并留一条告警——
    设置项不该成为应用起不来的原因。任务级模型的目录校验带实例映射（`task_provider_*`
    指向哪家，模型就落哪家的目录）。
    """
    from app.core.llm.provider_instances import instance_dialects

    stored = read_stored_fresh()
    dialects = instance_dialects()
    for name in MANAGED_FIELDS:
        raw = stored.get(name)
        if raw is None:
            setattr(settings, name, _BOOTSTRAP[name])
            continue
        try:
            validate_patch({name: raw}, current_values(), dialects)
        except SettingsError as error:
            logger.warning(
                "设置项 %s 的存量值不在目录里（%s），已回落引导默认", name, error.message
            )
            setattr(settings, name, _BOOTSTRAP[name])
            continue
        setattr(settings, name, normalize(name, raw))
    _prune_stale_instance_pointers(stored)
    invalidate_capabilities()


def _prune_stale_instance_pointers(stored: Mapping[str, str]) -> None:
    """删掉指向已不存在实例的指针（实例被删时 API 会同步清理，这里是启动兜底）。"""
    from app.core.catalog import FIELDS
    from app.core.llm.provider_instances import instance_dialects

    dialects = instance_dialects()
    stale = [
        name
        for name, value in stored.items()
        if FIELDS.get(name) is not None
        and FIELDS[name].kind == "provider_instance"
        and value.strip()
        and value.strip() not in dialects
    ]
    if not stale:
        return
    with SessionLocal() as db:
        for name in stale:
            row = db.get(AppSetting, name)
            if row is not None:
                db.delete(row)
                setattr(settings, name, _BOOTSTRAP[name])
        db.commit()
    logger.warning("清理了指向已删供应商实例的设置项：%s", "、".join(stale))


def ensure_bootstrap_provider_instance() -> None:
    """legacy 配置迁到实例表：表空且 `.env` 已配某方言的 Key 时，自动建一条并设为默认。

    只在「实例表一条都没有」时做（不覆盖教师后来在设置页加的）；custom 不迁——
    它本来就要填三件套。迁移后 `.env` 原值不动，删掉这条实例即回落 legacy 路径。
    """
    from app.core.catalog import PROVIDERS
    from app.core.llm.provider_instances import list_instances

    if list_instances():
        return
    provider = (settings.llm_provider or "").strip().lower()
    spec = PROVIDERS.get(provider)
    if spec is None or provider == "custom" or not spec.key_field:
        return
    api_key = value_of(spec.key_field).strip()
    if not api_key:
        return
    from app.db.models import LLMProviderInstance

    with SessionLocal() as db:
        instance = LLMProviderInstance(
            provider=provider,
            label=spec.label,
            api_key=api_key,
        )
        db.add(instance)
        db.commit()
        db.refresh(instance)
        instance_id = instance.id
        write_settings(db, {"default_provider_instance": instance_id})
    logger.info("已把 .env 的 %s 配置迁为供应商实例 %s（默认）", provider, instance_id)


def write_settings(db: Session, patch: Mapping[str, str]) -> None:
    """写穿：校验 → 落库 → 同步进程内 settings → 清能力工厂缓存（无需重启）。

    传入的键可以是任意子集（界面一次只改一件事）。空字符串 = 清除该项设置（回落引导默认）。
    校验不通过时抛 `SettingsError`（带稳定错误码与面向教师的信息），库内一行不动。
    任务级模型与全局模型的目录校验都带实例映射（多供应商口径）。
    """
    from app.core.llm.provider_instances import instance_dialects

    values = {name: normalize(name, value) for name, value in patch.items()}
    _check_instance_pointers(values)
    validate_patch(values, current_values(), instance_dialects())
    for name, value in values.items():
        row = db.get(AppSetting, name)
        if not value:
            if row is not None:
                db.delete(row)
            continue
        if row is None:
            db.add(AppSetting(key=name, value=value))
        else:
            row.value = value
    db.commit()
    apply_stored_settings()


def _check_instance_pointers(values: Mapping[str, str]) -> None:
    """实例指针的存在性校验：指向不存在的供应商实例 id 一律 400（stable code）。"""
    from app.core.catalog import FIELDS
    from app.core.llm.provider_instances import instance_dialects

    dialects = instance_dialects()
    for name, value in values.items():
        spec = FIELDS.get(name)
        if spec is None or spec.kind != "provider_instance":
            continue
        if value and value not in dialects:
            raise SettingsError(
                "unknown_provider_instance",
                name,
                f"未添加这个供应商：{value or '（空）'}（先在「添加供应商」里加上，再指给任务）",
            )


def clear_stored_settings() -> None:
    """清空设置库并回落引导默认（「恢复引导默认」语义；测试隔离也走它）。"""
    with SessionLocal() as db:
        db.execute(delete(AppSetting))  # 全表清空：设置库只有「有覆盖项」的语义
        db.commit()
    apply_stored_settings()
