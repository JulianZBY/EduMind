"""设置接口（CONTEXT.md「设置」「供应商目录」「任务级模型」「掩码」）。

三件事各一个端点：

- `GET /settings` 读**当前生效**配置：每项都带来源（设置页 / 引导默认），Key 只回掩码；
- `PUT /settings` 写设置：校验 → 落库 → 同步进程内配置 → 清能力工厂缓存，全程在请求内完成，
  **不需要重启**（写穿细节见 `app/core/settings_store.py`）；
- `GET /settings/catalog` 列可选目录：供应商、任务清单、各能力的可选实现（下拉的唯一出处）。

目录与校验口径统一住在 `app/core/catalog.py`；本模块只做装配与 OpenAPI 注解。
"""

from collections.abc import Mapping
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.openapi_examples import VALIDATION_ERROR, internal_error, json_response
from app.core.catalog import (
    CAPABILITIES,
    FIELDS,
    ITEM_FIELDS,
    KEY_FIELDS,
    PROVIDERS,
    TASKS,
    SettingsError,
    probe,
)
from app.core.llm.factory import get_llm
from app.core.llm.provider_instances import (
    default_instance,
    effective_base_url,
    effective_model,
    list_instances,
    models_of_instance,
    probe_instance,
)
from app.core.llm.task_routing import routing_for
from app.core.settings_store import (
    apply_stored_settings,
    ensure_bootstrap_provider_instance,
    mask_key,
    read_stored,
    source_of,
    value_of,
    write_settings,
)
from app.db import get_session
from app.db.models import LLMProviderInstance

router = APIRouter(on_startup=[apply_stored_settings, ensure_bootstrap_provider_instance])
# 启动钩子：应用起来就按设置库把生效值同步进进程内配置；随后把 .env 里的 legacy 供应商
# 配置（如有）迁成一条默认实例（`init_db()` 之后执行，表已就位）。

NOTE = "改动即时生效、不需要重启；Key 只在写入时接收，回读一律掩码，任何响应与表单都不回显明文。"


# ---- 响应模型（前端类型由 OpenAPI 生成，禁止手抄）----


class ProviderInstanceView(BaseModel):
    """一条已添加的供应商实例：设置页「添加供应商」产生的每一家。"""

    id: str  # 实例 id（任务级供应商与默认供应商指针指向它）
    provider: str  # 方言 id（目录家的取值；custom = 自定义 OpenAI 兼容服务）
    label: str  # 面向教师的名称
    base_url: str  # 生效地址（覆盖优先，其次方言预设）
    model: str  # 覆盖默认模型（兼容旧行；新添加不再选模型，全局默认走「全局默认」卡）
    models: list[str]  # 从服务商 /v1/models 拉取的模型清单（统一模型池的来源；失败为空）
    models_error: str  # 上次拉取失败的原因（空 = 拉取成功或尚未拉取）
    is_default: bool  # 是否全局默认供应商
    ready: bool  # 用当前配置能否构造出实现（缺 Key 时为 false，不是错误响应）
    reason: str  # ready=false 时的原因（实现自己抛出的可读错误）
    key_configured: bool  # 是否已粘贴 Key
    key_masked: str  # 掩码（只显示尾部若干位；未配置为空）


class ProviderView(BaseModel):
    """当前对话供应商：id、面向教师的名称、它用哪个字段存 Key，以及「现在能不能用」。"""

    value: str  # 供应商 id（目录里的取值）
    label: str  # 面向教师的名称
    key_field: str  # 该供应商的 Key 存在哪个设置项（空 = 不需要 Key）
    source: str  # 设置页 / 引导默认
    ready: bool  # 用当前配置能否构造出实现（缺 Key 时为 false，不是错误响应）
    reason: str  # ready=false 时的原因（实现自己抛出的可读错误）


class SettingItem(BaseModel):
    """一项可编辑的非 Key 设置：当前值 + 实际生效值（留空时按供应商预设解析）。"""

    name: str  # 设置项名（写入时用它做键）
    label: str  # 面向教师的名称
    value: str  # 当前值（空 = 未覆盖）
    effective: str  # 实际生效值（解析预设、回落引导默认之后）
    source: str  # 设置页 / 引导默认


class KeyItem(BaseModel):
    """一项 Key：只回掩码与是否已配置，明文一个字节都不出现在响应里。"""

    field: str  # 设置项名（写入时用它做键）
    label: str  # 面向教师的名称
    configured: bool  # 是否已配置
    masked: str  # 掩码（只显示尾部若干位；未配置为空）
    source: str  # 设置页 / 引导默认


class TaskModelView(BaseModel):
    """一个任务级模型档位：选了哪家、选了什么、**实际用的是哪家哪个模型**、来源。"""

    task: str  # 任务名：intent / generate / conflict
    label: str  # 面向教师的名称：意图分析 / 生成 / 冲突比对
    field: str  # 存放该任务档位的设置项
    provider_field: str  # 存放该任务供应商实例的设置项
    selected: str  # 任务级选择的模型（空 = 未设置）
    selected_provider: str  # 任务级选择的供应商实例 id（空 = 跟随全局默认）
    provider: str  # 该任务实际用的供应商实例 id（空 = legacy 单供应商口径）
    provider_label: str  # 该任务实际用的供应商名（面向教师）
    model: str  # 该任务实际用的模型
    source: str  # 任务级 / 全局默认


class CapabilityView(BaseModel):
    """一项可切换能力：当前实现 + 就绪状态。"""

    key: str  # 设置项名
    label: str  # 面向教师的能力名
    value: str  # 当前实现 id（留空时给出「自动」档的 id）
    value_label: str  # 当前实现的说明
    source: str  # 设置页 / 引导默认
    ready: bool  # 用当前配置能否构造出实现
    reason: str  # ready=false 时的原因


class SettingsView(BaseModel):
    """当前生效设置：读取与写入共用同一份形状（写完直接用它刷新界面）。"""

    provider: ProviderView
    provider_instances: list[ProviderInstanceView]  # 已添加的供应商（多供应商并存）
    items: list[SettingItem]
    keys: list[KeyItem]
    tasks: list[TaskModelView]
    capabilities: list[CapabilityView]
    note: str


class CatalogOption(BaseModel):
    """一项可选实现。"""

    id: str  # 配置取值
    label: str  # 面向教师的说明


class CatalogProvider(BaseModel):
    """供应商目录里的一家。"""

    id: str
    label: str
    base_url: str  # 预设地址（自定义档为空：由教师填）
    key_field: str  # 该供应商用哪个设置项存 Key（空 = 不需要）
    chat_models: list[str]  # 目录内的对话模型（任务级模型档位从这里选）
    vision_models: list[str]  # 目录内的多模态模型
    embed_models: list[str]  # 目录内的向量化模型
    accepts_any_model: bool  # 自定义服务：任意模型 ID 都放行
    note: str


class CatalogCapability(BaseModel):
    """一项可切换能力与它的全部可选实现。"""

    key: str
    label: str
    options: list[CatalogOption]
    note: str


class CatalogTask(BaseModel):
    """一个任务级模型档位的定义。"""

    id: str
    label: str
    field: str


class SettingsCatalog(BaseModel):
    """可选目录：供应商 + 能力实现 + 任务清单（设置页下拉的唯一出处）。"""

    providers: list[CatalogProvider]
    capabilities: list[CatalogCapability]
    tasks: list[CatalogTask]
    note: str


class SettingsUpdate(BaseModel):
    """写入设置：**只传要改的项**（界面一次只做一件事）。

    约定：字段缺省或传 `null` = 该项不动；传空字符串 = **清除该项**（回落 `.env` 引导默认）。
    取值必须落在 `GET /settings/catalog` 给出的目录里，否则 400（带稳定 `code` 与可读 `message`）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "llm_provider": "deepseek",
                "deepseek_api_key": "sk-在这里粘贴你自己的 Key",
                "task_model_generate": "deepseek-reasoner",
            }
        }
    )

    # ---- 供应商与全局默认模型 ----
    llm_provider: str | None = Field(
        default=None,
        description="供应商目录里的 id（内置方言 + providers.json 声明的家；取值见 GET /settings/catalog）",
    )
    llm_base_url: str | None = Field(
        default=None, description="服务商地址（base_url）；留空用方言预设，自定义服务必须填"
    )
    llm_model: str | None = Field(
        default=None, description="全局默认对话模型；未设置的任务回落到它"
    )
    llm_vision_model: str | None = Field(default=None, description="多模态模型（图片/视频理解用）")
    # ---- 各家的 Key（写入接收，回读只回掩码）----
    llm_api_key: str | None = Field(default=None, description="自定义服务的 API Key")
    qwen_api_key: str | None = Field(default=None, description="千问 API Key")
    deepseek_api_key: str | None = Field(default=None, description="DeepSeek API Key")
    moonshot_api_key: str | None = Field(default=None, description="Kimi API Key")
    zhipu_api_key: str | None = Field(default=None, description="智谱 API Key")
    minimax_api_key: str | None = Field(default=None, description="MiniMax API Key")
    ark_api_key: str | None = Field(default=None, description="豆包 API Key")
    siliconflow_api_key: str | None = Field(default=None, description="硅基流动 API Key")
    # ---- 向量化（独立于对话供应商）----
    embedding_provider: str | None = Field(
        default=None, description="向量化实现；留空 = 跟随对话供应商"
    )
    embedding_base_url: str | None = Field(default=None, description="向量化服务地址（base_url）")
    embedding_model: str | None = Field(default=None, description="向量化模型 ID")
    embedding_api_key: str | None = Field(default=None, description="向量化 API Key")
    # ---- 其它云端能力 ----
    mineru_token: str | None = Field(default=None, description="MinerU 云端 PDF 解析 Token")
    bocha_api_key: str | None = Field(default=None, description="博查网络搜索 Key")
    asr_api_key: str | None = Field(default=None, description="百炼语音转写 Key（paraformer 专用，千问 MaaS 的 Key 不通用）")
    asr_provider: str | None = Field(default=None, description="语音转写实现：auto / paraformer")
    pdf_strategy: str | None = Field(
        default=None, description="PDF 解析策略：mineru_then_pypdf / pypdf / mineru"
    )
    search_provider: str | None = Field(
        default=None, description="网络搜索实现：auto / bocha"
    )
    retrieval_strategy: str | None = Field(
        default=None, description="检索策略：vector_graph / vector"
    )
    chunk_strategy: str | None = Field(default=None, description="分块策略：paragraph")
    # ---- 任务级模型（留空回落全局默认）----
    task_provider_intent: str | None = Field(default=None, description="意图分析用的供应商实例 id")
    task_provider_generate: str | None = Field(default=None, description="生成用的供应商实例 id")
    task_provider_conflict: str | None = Field(default=None, description="冲突比对用的供应商实例 id")
    task_model_intent: str | None = Field(default=None, description="意图分析用的模型档位")
    task_model_generate: str | None = Field(default=None, description="生成用的模型档位")
    task_model_conflict: str | None = Field(default=None, description="冲突比对用的模型档位")
    # ---- 多供应商：默认实例指针（实例本身的增删改走 /settings/providers 端点）----
    default_provider_instance: str | None = Field(
        default=None, description="全局默认供应商实例 id（留空 = legacy 单供应商路径）"
    )


# ---- 生效值装配 ----


def _effective(name: str, value: str) -> str:
    """实际生效值：留空时按当前供应商的预设解析（设置页要显示「实际用的是什么」）。

    默认实例（多供应商）优先：解析它方言的预设；没有实例再走 legacy `llm_provider`。
    """
    if value:
        return value
    instance = default_instance()
    if instance is not None:
        provider = PROVIDERS.get(instance.provider)
        if provider is None:
            return ""
        if name == "llm_base_url":
            return instance.base_url or provider.base_url
        if name == "llm_model":
            # 全局默认模型由「全局默认」卡显式选（llm_model）；实例行不再承担默认模型
            return provider.chat_models[0] if provider.chat_models else ""
        if name == "llm_vision_model":
            return provider.vision_models[0] if provider.vision_models else ""
    provider = PROVIDERS.get(value_of("llm_provider").strip().lower())
    if provider is None:
        return ""
    if name == "llm_base_url":
        return provider.base_url
    if name == "llm_model":
        return provider.chat_models[0] if provider.chat_models else ""
    if name == "llm_vision_model":
        return provider.vision_models[0] if provider.vision_models else ""
    return ""


def _items(stored: Mapping[str, str]) -> list[SettingItem]:
    return [
        SettingItem(
            name=spec.name,
            label=spec.label,
            value=value_of(spec.name),
            effective=_effective(spec.name, value_of(spec.name)),
            source=source_of(spec.name, stored),
        )
        for spec in ITEM_FIELDS
    ]


def _keys(stored: Mapping[str, str]) -> list[KeyItem]:
    return [
        KeyItem(
            field=spec.name,
            label=spec.label,
            configured=bool(value_of(spec.name)),
            masked=mask_key(value_of(spec.name)),
            source=source_of(spec.name, stored),
        )
        for spec in KEY_FIELDS
    ]


def _tasks() -> list[TaskModelView]:
    rows = []
    for spec in TASKS:
        instance_id, instance_label, model, source = routing_for(spec.id)
        rows.append(
            TaskModelView(
                task=spec.id,
                label=spec.label,
                field=spec.field,
                provider_field=spec.provider_field,
                selected=value_of(spec.field),
                selected_provider=value_of(spec.provider_field),
                provider=instance_id,
                provider_label=instance_label,
                model=model,
                source=source,
            )
        )
    return rows


def _provider_instance_views() -> list[ProviderInstanceView]:
    default_id = (value_of("default_provider_instance") or "").strip()
    rows = []
    for instance in list_instances():
        rows.append(_instance_view(instance, default_id=instance.id == default_id))
    return rows


def _capabilities(stored: Mapping[str, str]) -> list[CapabilityView]:
    rows = []
    for spec in CAPABILITIES:
        ready, reason = probe(spec.probe)
        value = value_of(spec.key) or spec.auto_id
        rows.append(
            CapabilityView(
                key=spec.key,
                label=spec.label,
                value=value,
                value_label=spec.option_label(value),
                source=source_of(spec.key, stored),
                ready=ready,
                reason=reason,
            )
        )
    return rows


def _view(db: Session) -> SettingsView:
    """装配当前生效设置：`stored` 是「哪些项在设置页改过」的判据，决定每项的 `source`。

    `provider`（legacy 单供应商视图）在有默认实例时由实例派生——设置页新形态以
    `provider_instances` 为准，`provider` 只为兼容旧读取方保留。
    """
    stored = read_stored(db)
    ready, reason = probe(get_llm)
    instance = default_instance()
    if instance is not None:
        spec = PROVIDERS.get(instance.provider)
        provider_view = ProviderView(
            value=instance.provider,
            label=instance.label,
            key_field=spec.key_field if spec else "",
            source=source_of("default_provider_instance", stored),
            ready=ready,
            reason=reason,
        )
    else:
        provider_id = value_of("llm_provider").strip().lower()
        spec = PROVIDERS.get(provider_id)
        provider_view = ProviderView(
            value=provider_id,
            label=spec.label if spec else ("未配置" if not provider_id else provider_id),
            key_field=spec.key_field if spec else "",
            source=source_of("llm_provider", stored),
            ready=ready,
            reason=reason,
        )
    return SettingsView(
        provider=provider_view,
        provider_instances=_provider_instance_views(),
        items=_items(stored),
        keys=_keys(stored),
        tasks=_tasks(),
        capabilities=_capabilities(stored),
        note=NOTE,
    )
def _patch_of(req: SettingsUpdate) -> dict[str, str]:
    """请求体 → 设置项补丁：只收显式传了值的字段（缺省 / null = 不动）。"""
    return {name: value for name in FIELDS if (value := getattr(req, name)) is not None}


_ERROR_EXAMPLE = {
    "detail": {
        "code": "unknown_model",
        "field": "task_model_generate",
        "message": (
            "未知模型：gpt-4o（「DeepSeek」的生成可选：deepseek-chat、deepseek-reasoner；"
            "目录之外的模型请用「自定义 OpenAI 兼容服务」）"
        ),
    }
}

SETTINGS_INVALID = json_response(
    "配置值不在目录里：`code` 是稳定机器码"
    "（unknown_provider / unknown_model / unknown_capability_impl / invalid_base_url），"
    "`field` 指向出错的设置项，`message` 可直接显示给教师；本次写入未落库",
    _ERROR_EXAMPLE,
)

_VIEW_EXAMPLE: dict[str, Any] = {
    "provider": {
        "value": "deepseek",
        "label": "DeepSeek",
        "key_field": "deepseek_api_key",
        "source": "设置页",
        "ready": True,
        "reason": "",
    },
    "provider_instances": [
        {
            "id": "3f2c8e6a-1111-4c3e-9d2a-6c0f1e2d3b4a",
            "provider": "deepseek",
            "label": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "is_default": True,
            "ready": True,
            "reason": "",
            "key_configured": True,
            "key_masked": "••••9f8a",
        },
        {
            "id": "8a1d5b7c-2222-4e6f-8c3b-1d4a5e6f7a8b",
            "provider": "custom",
            "label": "我的中转服务",
            "base_url": "https://example.com/v1",
            "model": "my-model",
            "is_default": False,
            "ready": False,
            "reason": "「我的中转服务」还没有粘贴 API Key",
            "key_configured": False,
            "key_masked": "",
        },
    ],
    "items": [
        {
            "name": "llm_base_url",
            "label": "服务商地址（base_url）",
            "value": "",
            "effective": "https://api.deepseek.com",
            "source": "引导默认",
        },
        {
            "name": "llm_model",
            "label": "对话模型",
            "value": "",
            "effective": "deepseek-chat",
            "source": "引导默认",
        },
        {
            "name": "llm_vision_model",
            "label": "多模态模型",
            "value": "",
            "effective": "",
            "source": "引导默认",
        },
        {
            "name": "embedding_base_url",
            "label": "向量化服务地址（base_url）",
            "value": "",
            "effective": "",
            "source": "引导默认",
        },
        {
            "name": "embedding_model",
            "label": "向量化模型",
            "value": "",
            "effective": "",
            "source": "引导默认",
        },
    ],
    "keys": [
        {
            "field": "llm_api_key",
            "label": "自定义服务的 API Key",
            "configured": False,
            "masked": "",
            "source": "引导默认",
        },
        {
            "field": "qwen_api_key",
            "label": "千问 API Key",
            "configured": False,
            "masked": "",
            "source": "引导默认",
        },
        {
            "field": "asr_api_key",
            "label": "百炼语音转写 Key",
            "configured": False,
            "masked": "",
            "source": "引导默认",
        },

        {
            "field": "deepseek_api_key",
            "label": "DeepSeek API Key",
            "configured": True,
            "masked": "••••9f8a",
            "source": "设置页",
        },
        {
            "field": "siliconflow_api_key",
            "label": "硅基流动 API Key",
            "configured": False,
            "masked": "",
            "source": "引导默认",
        },
        {
            "field": "embedding_api_key",
            "label": "向量化 API Key",
            "configured": False,
            "masked": "",
            "source": "引导默认",
        },
        {
            "field": "mineru_token",
            "label": "MinerU Token",
            "configured": False,
            "masked": "",
            "source": "引导默认",
        },
        {
            "field": "bocha_api_key",
            "label": "博查搜索 Key",
            "configured": False,
            "masked": "",
            "source": "引导默认",
        },
    ],
    "tasks": [
        {
            "task": "intent",
            "label": "意图分析",
            "field": "task_model_intent",
            "provider_field": "task_provider_intent",
            "selected": "deepseek-chat",
            "selected_provider": "3f2c8e6a-1111-4c3e-9d2a-6c0f1e2d3b4a",
            "provider": "3f2c8e6a-1111-4c3e-9d2a-6c0f1e2d3b4a",
            "provider_label": "DeepSeek",
            "model": "deepseek-chat",
            "source": "任务级",
        },
        {
            "task": "generate",
            "label": "生成",
            "field": "task_model_generate",
            "provider_field": "task_provider_generate",
            "selected": "",
            "selected_provider": "",
            "provider": "3f2c8e6a-1111-4c3e-9d2a-6c0f1e2d3b4a",
            "provider_label": "DeepSeek",
            "model": "deepseek-chat",
            "source": "全局默认",
        },
        {
            "task": "conflict",
            "label": "冲突比对",
            "field": "task_model_conflict",
            "provider_field": "task_provider_conflict",
            "selected": "",
            "selected_provider": "",
            "provider": "3f2c8e6a-1111-4c3e-9d2a-6c0f1e2d3b4a",
            "provider_label": "DeepSeek",
            "model": "deepseek-chat",
            "source": "全局默认",
        },
    ],
    "capabilities": [
        {
            "key": "asr_provider",
            "label": "语音转写",
            "value": "",
            "value_label": "未配置（需要百炼 paraformer Key）",
            "source": "引导默认",
            "ready": False,
            "reason": "语音转写未配置：到「设置 → 能力实现」把语音转写指到 paraformer 并粘贴百炼 Key，或在 .env 配置 ASR_API_KEY（千问 MaaS 的 Key 不通用）。",
        },
        {
            "key": "pdf_strategy",
            "label": "PDF 解析",
            "value": "mineru_then_pypdf",
            "value_label": "mineru → pypdf 兜底（默认）",
            "source": "引导默认",
            "ready": True,
            "reason": "",
        },
        {
            "key": "search_provider",
            "label": "网络搜索",
            "value": "auto",
            "value_label": "自动（有 Key 走博查，否则未配置）",
            "source": "引导默认",
            "ready": True,
            "reason": "",
        },
        {
            "key": "embedding_provider",
            "label": "向量化",
            "value": "auto",
            "value_label": "自动（跟随对话供应商）",
            "source": "引导默认",
            "ready": True,
            "reason": "",
        },
        {
            "key": "retrieval_strategy",
            "label": "检索策略",
            "value": "vector_graph",
            "value_label": "向量 + 图谱融合（默认）",
            "source": "引导默认",
            "ready": True,
            "reason": "",
        },
        {
            "key": "chunk_strategy",
            "label": "分块策略",
            "value": "paragraph",
            "value_label": "按段落与标题边界（默认）",
            "source": "引导默认",
            "ready": True,
            "reason": "",
        },
    ],
    "note": NOTE,
}

_CATALOG_EXAMPLE: dict[str, Any] = {
    "providers": [

        {
            "id": "deepseek",
            "label": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "key_field": "deepseek_api_key",
            "chat_models": ["deepseek-chat", "deepseek-reasoner"],
            "vision_models": [],
            "embed_models": [],
            "accepts_any_model": False,
            "note": "只提供对话；多模态与向量化不在此目录内。",
        },
        {
            "id": "custom",
            "label": "自定义 OpenAI 兼容服务",
            "base_url": "",
            "key_field": "llm_api_key",
            "chat_models": [],
            "vision_models": [],
            "embed_models": [],
            "accepts_any_model": True,
            "note": "目录之外的接入方式：填 base_url + 模型 ID + Key 即可用。",
        },
    ],
    "capabilities": [
        {
            "key": "asr_provider",
            "label": "语音转写",
            "options": [
                {"id": "auto", "label": "自动（有百炼 Key 走 paraformer，否则未配置）"},
                {"id": "paraformer", "label": "paraformer（阿里云百炼录音转写：需要百炼 Key，千问 MaaS 不提供）"},
            ],
            "note": "录音资料走哪条转写路径；paraformer 是阿里云百炼的服务（千问 MaaS 不提供，需要百炼 Key）。",
        },
        {
            "key": "search_provider",
            "label": "网络搜索",
            "options": [
                {"id": "auto", "label": "自动（有 Key 走博查，未配置则提示去配置）"},
                {"id": "bocha", "label": "博查（Bocha）"},
            ],
            "note": "题库的「网络」来源用它取题；未配置博查 Key 时给出「去配置」提示，不返回占位结果。",
        },
    ],
    "tasks": [
        {"id": "intent", "label": "意图分析", "field": "task_model_intent"},
        {"id": "generate", "label": "生成", "field": "task_model_generate"},
        {"id": "conflict", "label": "冲突比对", "field": "task_model_conflict"},
    ],
    "note": "供应商目录与可选能力实现来自能力注册表：这里列出什么，就能切成什么。",
}


@router.get(
    "/settings",
    response_model=SettingsView,
    tags=["设置"],
    summary="读取当前生效设置",
    description=(
        "回读**当前生效**的云端能力与模型档位：每项都带 `source`（`设置页` = 在设置页改过，"
        "`引导默认` = 仍按 `.env`）。\n\n"
        "- **Key 一律掩码**：只回 `masked`（尾部若干位）与 `configured`，任何响应与表单都不回显明文；\n"
        "  「表单也不回显明文」= 设置页拿不到明文，只能由教师重新粘贴；\n"
        "- `items` 给「当前值」与「实际生效值」：模型 / 地址留空时按供应商预设解析（如 DeepSeek 的 "
        "`deepseek-chat`），这样界面能显示「实际用的是什么」；\n"
        "- `tasks` 逐任务给出**该任务实际用的模型**与来源（`任务级` / `全局默认`）；\n"
        "- `ready` 用当前配置当场构造一次实现（离线、不联网）来判断「现在能不能用」：缺 Key 时为 "
        "`false` 且 `reason` 直接说明缺什么，而不是把错误拖到真正调用时才爆。"
    ),
    responses={
        200: json_response("当前生效设置（Key 只有掩码）", _VIEW_EXAMPLE),
        500: internal_error(),
    },
)
def read_settings(db: Annotated[Session, Depends(get_session)]):
    return _view(db)


@router.put(
    "/settings",
    response_model=SettingsView,
    tags=["设置"],
    summary="写入设置（即时生效，不需要重启）",
    description=(
        "**只传要改的项**（界面一次只做一件事）；字段缺省或传 `null` = 该项不动，传空字符串 = "
        "**清除该项**（回落 `.env` 引导默认）。\n\n"
        "写穿链路：目录校验 → 落库（`app_settings`）→ 把生效值同步进进程内配置 → 清掉能力工厂缓存。"
        "全过程在本次请求内完成，**改完下一次调用就用新配置**：例如把 `retrieval_strategy` 从 "
        "`vector_graph` 改成 `vector` 后，紧接着的 `POST /api/v1/knowledge/retrieve` 就返回 "
        "`strategy: vector`。\n\n"
        "取值必须落在 `GET /api/v1/settings/catalog` 给出的目录里：未知供应商 / 未知模型 / 未实现的"
        "能力 / 格式不对的 `base_url` 一律 400（带稳定 `code`），**库内一行不动**；"
        "供应商目录之外的模型走「自定义 OpenAI 兼容服务」（`llm_provider=custom` + "
        "`llm_base_url` + `llm_model`）。\n\n"
        "装配：改供应商与模型时建议一次带上该家的 Key（`qwen_api_key` / `deepseek_api_key` / "
        "`siliconflow_api_key` / 自定义服务的 `llm_api_key`），一次写入即切到真实服务。"
    ),
    responses={
        200: json_response("写入后的当前生效设置（Key 只有掩码）", _VIEW_EXAMPLE),
        400: SETTINGS_INVALID,
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
def update_settings(
    req: SettingsUpdate,
    db: Annotated[Session, Depends(get_session)],
):
    try:
        write_settings(db, _patch_of(req))
    except SettingsError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": error.code, "field": error.field, "message": error.message},
        ) from error
    return _view(db)


@router.get(
    "/settings/catalog",
    response_model=SettingsCatalog,
    tags=["设置"],
    summary="可选目录（供应商 / 能力实现 / 任务）",
    description=(
        "设置页下拉的**唯一出处**：供应商目录（含自定义服务）、各能力的可选实现、任务级模型的任务清单。\n\n"
        "口径来自能力注册表（ADR-0003）与方言预设：注册表加一行，这里就多一个可选项。"
        "写设置时认的取值就是这里的 `id`——目录里没有的值会被 400 挡下（自定义服务那档除外，"
        "它 `accepts_any_model=true`，模型 ID 由教师填）。"
    ),
    responses={
        200: json_response("可选目录", _CATALOG_EXAMPLE),
        500: internal_error(),
    },
)
def read_catalog():
    return SettingsCatalog(
        providers=[
            CatalogProvider(
                id=spec.id,
                label=spec.label,
                base_url=spec.base_url,
                key_field=spec.key_field,
                chat_models=list(spec.chat_models),
                vision_models=list(spec.vision_models),
                embed_models=list(spec.embed_models),
                accepts_any_model=spec.accepts_any_model,
                note=spec.note,
            )
            for spec in PROVIDERS.values()
        ],
        capabilities=[
            CatalogCapability(
                key=spec.key,
                label=spec.label,
                options=[
                    CatalogOption(id=option.id, label=option.label) for option in spec.options
                ],
                note=spec.note,
            )
            for spec in CAPABILITIES
        ],
        tasks=[CatalogTask(id=spec.id, label=spec.label, field=spec.field) for spec in TASKS],
        note="供应商目录与可选能力实现来自能力注册表：这里列出什么，就能切成什么。",
    )


# ---- 供应商实例（多供应商并存：添加 / 改 / 删）----


class ProviderInstanceCreate(BaseModel):
    """添加一家供应商：目录家只填 provider + Key；自定义服务另填名称 / 地址 / 模型。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider": "deepseek",
                "api_key": "sk-在这里粘贴你自己的 Key",
            }
        }
    )

    provider: str = Field(description="供应商目录里的 id（内置方言 + providers.json 声明的家；取值见 GET /settings/catalog）")
    label: str = Field(default="", description="面向教师的名称；留空用目录名（自定义服务建议填写）")
    base_url: str = Field(default="", description="服务商地址覆盖；目录家用预设，自定义服务必填")
    model: str = Field(default="", description="默认模型覆盖；目录家用预设，自定义服务必填")
    api_key: str = Field(default="", description="该供应商的 API Key")
    make_default: bool = Field(default=False, description="添加后设为全局默认；第一家自动成为默认")


class ProviderInstanceUpdate(BaseModel):
    """改一家已添加的供应商：只传要改的字段；api_key 缺省 = 不动（回读也拿不到明文）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"label": "DeepSeek（公司账号）", "make_default": True}
        }
    )

    label: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = Field(default=None, description="传空字符串 = 清除 Key；缺省 / null = 不动")
    make_default: bool = False


_INSTANCE_EXAMPLE: dict[str, Any] = {
    "id": "3f2c8e6a-1111-4c3e-9d2a-6c0f1e2d3b4a",
    "provider": "deepseek",
    "label": "DeepSeek",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "models": ["deepseek-chat", "deepseek-reasoner"],
    "models_error": "",
    "is_default": True,
    "ready": True,
    "reason": "",
    "key_configured": True,
    "key_masked": "••••9f8a",
}

_INSTANCE_INVALID = json_response(
    "供应商实例不成立：`code` 是稳定机器码（unknown_provider / missing_key / missing_base_url / "
    "missing_model / invalid_base_url / unknown_model），`message` 可直接显示给教师；本次未落库",
    {
        "detail": {
            "code": "unknown_model",
            "field": "model",
            "message": "未知模型：gpt-4o（「DeepSeek」可选：deepseek-chat、deepseek-reasoner；目录之外的模型请用「自定义 OpenAI 兼容服务」）",
        }
    },
)


def _instance_view(instance: LLMProviderInstance, default_id: bool | None = None) -> ProviderInstanceView:
    ready, reason = probe_instance(instance.id)
    if default_id is None:
        default_id = instance.id == value_of("default_provider_instance").strip()
    return ProviderInstanceView(
        id=instance.id,
        provider=instance.provider,
        label=instance.label,
        base_url=effective_base_url(instance),
        model=effective_model(instance),
        models=models_of_instance(instance.id),
        models_error=instance.models_error,
        is_default=default_id,
        ready=ready,
        reason=reason,
        key_configured=bool(instance.api_key),
        key_masked=mask_key(instance.api_key),
    )


def _validate_instance_fields(
    provider: str, base_url: str, model: str, api_key: str
) -> tuple[str, str, str, str]:
    """实例字段的目录校验：供应商在目录里、地址合法、模型在该方言目录内（放行档除外）。

    新口径：添加供应商不选模型——模型清单由 `/v1/models` 拉取或「手动填写」，`model`
    只是兼容旧行的可选覆盖，不再必填。
    """
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise SettingsError(
            "unknown_provider",
            "provider",
            f"未知供应商：{provider or '（空）'}（可选：{'、'.join(PROVIDERS)}）",
        )
    if provider == "custom" and not base_url:
        raise SettingsError(
            "missing_base_url", "base_url", "自定义服务要填服务商地址（base_url），例如 https://example.com/v1"
        )
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise SettingsError(
                "invalid_base_url",
                "base_url",
                f"服务商地址必须是 http(s) 开头的完整地址，例如 https://example.com/v1；当前值：{base_url}",
            )
    if model and not spec.accepts_any_model:
        allowed = spec.chat_models
        if model not in allowed:
            raise SettingsError(
                "unknown_model",
                "model",
                f"未知模型：{model}（「{spec.label}」可选：{'、'.join(allowed)}；"
                "目录之外的模型请用「自定义 OpenAI 兼容服务」）",
            )
    if not api_key:
        raise SettingsError(
            "missing_key", "api_key", f"「{spec.label}」要粘贴 API Key 才能用。"
        )
    return provider, base_url, model, api_key


@router.post(
    "/settings/providers",
    response_model=ProviderInstanceView,
    tags=["设置"],
    summary="添加供应商（多供应商并存）",
    description=(
        "添加一家供应商实例：目录家（千问 / DeepSeek / Kimi / 智谱 GLM / MiniMax / 豆包 / 硅基流动）"
        "只填 `provider` + `api_key`（地址与默认模型用预设）；「自定义 OpenAI 兼容服务」"
        "（`provider=custom`）另填 `label` / `base_url` / `model`。\n\n"
        "第一家添加后**自动成为全局默认**；`make_default=true` 可直接设为默认。"
        "任务级模型（`PUT /settings` 的 `task_provider_*`）指向这里返回的 `id`。\n\n"
        "Key 只在写入时接收；回读一律掩码。校验不通过 400（稳定 `code`），不落库。"
    ),
    responses={
        200: json_response("添加成功的供应商实例（Key 只有掩码）", _INSTANCE_EXAMPLE),
        400: _INSTANCE_INVALID,
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
def create_provider_instance(
    req: ProviderInstanceCreate,
    db: Annotated[Session, Depends(get_session)],
):
    provider = req.provider.strip().lower()
    spec = PROVIDERS.get(provider)
    try:
        provider, base_url, model, api_key = _validate_instance_fields(
            provider, req.base_url.strip(), req.model.strip(), req.api_key.strip()
        )
    except SettingsError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": error.code, "field": error.field, "message": error.message},
        ) from error
    # 名称：教师填了用教师的；没填用目录名（校验已保证目录里有这家）
    label = req.label.strip() or (spec.label if spec else provider)
    instance = LLMProviderInstance(
        provider=provider,
        label=label,
        base_url=base_url,
        model=model,
        api_key=api_key,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    # 添加后同步拉取该家的模型清单（存 provider_models 表）；失败不挡添加，原因写进实例行
    from app.core.llm.provider_instances import refresh_models

    refresh_models(instance.id, db)
    first = len(list_instances(db)) == 1 and list_instances(db)[0].id == instance.id
    if (first and not value_of("default_provider_instance")) or req.make_default:
        try:
            write_settings(db, {"default_provider_instance": instance.id})
        except SettingsError:
            pass  # 指针写不进去不影响实例本身；界面可再手动设默认
    db.refresh(instance)
    return _instance_view(instance)


@router.patch(
    "/settings/providers/{instance_id}",
    response_model=ProviderInstanceView,
    tags=["设置"],
    summary="改供应商（名称 / 地址 / 模型 / Key / 设为默认）",
    description=(
        "改一条已添加的供应商实例：只传要改的字段；`api_key` 缺省或 `null` = 不动"
        "（回读拿不到明文），传空字符串 = 清除 Key。`make_default=true` 把它设为全局默认。\n\n"
        "改动即时生效并清掉能力缓存；正在使用它的任务下一次调用就用新配置。"
    ),
    responses={
        200: json_response("改后的供应商实例（Key 只有掩码）", _INSTANCE_EXAMPLE),
        400: _INSTANCE_INVALID,
        404: json_response("这条供应商实例不存在（可能刚被删除）", {"detail": "provider instance not found"}),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
def update_provider_instance(
    instance_id: str,
    req: ProviderInstanceUpdate,
    db: Annotated[Session, Depends(get_session)],
):
    instance = db.get(LLMProviderInstance, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="provider instance not found")
    base_url = req.base_url.strip() if req.base_url is not None else instance.base_url
    model = req.model.strip() if req.model is not None else instance.model
    api_key = req.api_key.strip() if req.api_key is not None else instance.api_key
    label = req.label.strip() if req.label is not None else instance.label
    try:
        _validate_instance_fields(instance.provider, base_url, model, api_key)
    except SettingsError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": error.code, "field": error.field, "message": error.message},
        ) from error
    instance.label = label
    instance.base_url = base_url
    instance.model = model
    instance.api_key = api_key
    db.commit()
    db.refresh(instance)
    if req.make_default:
        try:
            write_settings(db, {"default_provider_instance": instance.id})
        except SettingsError:
            pass
    from app.core.llm.provider_instances import clear_instance_cache

    clear_instance_cache()
    return _instance_view(instance)


@router.delete(
    "/settings/providers/{instance_id}",
    response_model=SettingsView,
    tags=["设置"],
    summary="删除供应商（并清掉指向它的指针）",
    description=(
        "删除一条供应商实例，同时清掉指向它的全部指针（全局默认与任务级 `task_provider_*`，"
        "相应任务回落全局默认；默认被删则回落剩余第一家，没有了就回落 `.env` 引导默认）。\n\n"
        "Key 随实例行一起删除；`.env` 里的原值不动（那是引导默认，不是实例）。"
    ),
    responses={
        200: json_response("删除后的当前生效设置", _VIEW_EXAMPLE),
        404: json_response("这条供应商实例不存在（可能刚被删除）", {"detail": "provider instance not found"}),
        500: internal_error(),
    },
)
def delete_provider_instance(
    instance_id: str,
    db: Annotated[Session, Depends(get_session)],
):
    instance = db.get(LLMProviderInstance, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="provider instance not found")
    db.delete(instance)
    db.commit()
    # 清指针：默认与任务级指向这家的一并清空，回落全局默认 / 剩余第一家
    pointers = {"default_provider_instance"} | {spec.provider_field for spec in TASKS}
    patch = {name: "" for name in pointers if value_of(name).strip() == instance_id}
    if patch:
        try:
            write_settings(db, patch)
        except SettingsError:
            pass
    # 默认没了但还有别的实例：把第一家顶上（全局默认不能悬空）
    if not value_of("default_provider_instance").strip():
        remaining = list_instances(db)
        if remaining:
            try:
                write_settings(db, {"default_provider_instance": remaining[0].id})
            except SettingsError:
                pass
    from app.core.llm.provider_instances import clear_instance_cache

    clear_instance_cache()
    return _view(db)


@router.post(
    "/settings/providers/{instance_id}/refresh-models",
    response_model=ProviderInstanceView,
    tags=["设置"],
    summary="刷新这家供应商的模型清单（重新拉取 /v1/models）",
    description=(
        "重新调该实例的 `GET {base_url}/models` 拉取模型清单并整表替换缓存：服务商上新模型后、"
        "或上次拉取失败修正 Key / 网络后点这里。\n\n"
        "拉取失败不落半行、保持旧清单，并把原因写到实例的 `models_error`——"
        "统一模型池里这家的模型可以先「手动填写」。"
    ),
    responses={
        200: json_response("刷新后的供应商实例（Key 只有掩码）", _INSTANCE_EXAMPLE),
        404: json_response("这条供应商实例不存在（可能刚被删除）", {"detail": "provider instance not found"}),
        500: internal_error(),
    },
)
def refresh_provider_models(
    instance_id: str,
    db: Annotated[Session, Depends(get_session)],
):
    instance = db.get(LLMProviderInstance, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="provider instance not found")
    from app.core.llm.provider_instances import refresh_models

    refresh_models(instance_id, db)
    db.refresh(instance)
    return _instance_view(instance)
