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
from app.core.llm.task_routing import model_for
from app.core.settings_store import (
    apply_stored_settings,
    mask_key,
    read_stored,
    source_of,
    value_of,
    write_settings,
)
from app.db import get_session

router = APIRouter(on_startup=[apply_stored_settings])
# 启动钩子：应用起来就按设置库把生效值同步进进程内配置（`init_db()` 之后执行，表已就位）。

NOTE = "改动即时生效、不需要重启；Key 只在写入时接收，回读一律掩码，任何响应与表单都不回显明文。"


# ---- 响应模型（前端类型由 OpenAPI 生成，禁止手抄）----


class ProviderView(BaseModel):
    """当前对话供应商：id、面向教师的名称、它用哪个字段存 Key，以及「现在能不能用」。"""

    value: str  # 供应商 id（目录里的取值）
    label: str  # 面向教师的名称
    key_field: str  # 该供应商的 Key 存在哪个设置项（stub 为空 = 不需要 Key）
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
    """一个任务级模型档位：选了什么、**实际用的是什么**、来源是任务级还是全局默认。"""

    task: str  # 任务名：intent / generate / conflict
    label: str  # 面向教师的名称：意图分析 / 生成 / 冲突比对
    field: str  # 存放该任务档位的设置项
    selected: str  # 任务级选择的模型（空 = 未设置）
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
        description="供应商目录里的 id（stub / dashscope / deepseek / siliconflow / custom）",
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
    dashscope_api_key: str | None = Field(default=None, description="阿里云百炼 API Key")
    deepseek_api_key: str | None = Field(default=None, description="DeepSeek API Key")
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
    asr_provider: str | None = Field(default=None, description="语音转写实现：stub / paraformer")
    pdf_strategy: str | None = Field(
        default=None, description="PDF 解析策略：mineru_then_pypdf / pypdf / mineru"
    )
    search_provider: str | None = Field(
        default=None, description="网络搜索实现：auto / stub / bocha"
    )
    retrieval_strategy: str | None = Field(
        default=None, description="检索策略：vector_graph / vector"
    )
    chunk_strategy: str | None = Field(default=None, description="分块策略：paragraph")
    # ---- 任务级模型（留空回落全局默认）----
    task_model_intent: str | None = Field(default=None, description="意图分析用的模型档位")
    task_model_generate: str | None = Field(default=None, description="生成用的模型档位")
    task_model_conflict: str | None = Field(default=None, description="冲突比对用的模型档位")


# ---- 生效值装配 ----


def _effective(name: str, value: str) -> str:
    """实际生效值：留空时按当前供应商的预设解析（设置页要显示「实际用的是什么」）。"""
    if value:
        return value
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
        model, source = model_for(spec.id)
        rows.append(
            TaskModelView(
                task=spec.id,
                label=spec.label,
                field=spec.field,
                selected=value_of(spec.field),
                model=model,
                source=source,
            )
        )
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
    """装配当前生效设置：`stored` 是「哪些项在设置页改过」的判据，决定每项的 `source`。"""
    stored = read_stored(db)
    provider_id = value_of("llm_provider").strip().lower() or "stub"
    spec = PROVIDERS.get(provider_id)
    ready, reason = probe(get_llm)
    return SettingsView(
        provider=ProviderView(
            value=provider_id,
            label=spec.label if spec else provider_id,
            key_field=spec.key_field if spec else "",
            source=source_of("llm_provider", stored),
            ready=ready,
            reason=reason,
        ),
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
            "field": "dashscope_api_key",
            "label": "阿里云百炼 API Key",
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
            "selected": "deepseek-chat",
            "model": "deepseek-chat",
            "source": "任务级",
        },
        {
            "task": "generate",
            "label": "生成",
            "field": "task_model_generate",
            "selected": "",
            "model": "deepseek-chat",
            "source": "全局默认",
        },
        {
            "task": "conflict",
            "label": "冲突比对",
            "field": "task_model_conflict",
            "selected": "",
            "model": "deepseek-chat",
            "source": "全局默认",
        },
    ],
    "capabilities": [
        {
            "key": "asr_provider",
            "label": "语音转写",
            "value": "stub",
            "value_label": "stub 模式（无 Key 可跑）",
            "source": "引导默认",
            "ready": True,
            "reason": "",
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
            "value_label": "自动（有 Key 走博查，否则 stub 模式）",
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
            "id": "stub",
            "label": "stub 模式",
            "base_url": "",
            "key_field": "",
            "chat_models": ["stub"],
            "vision_models": [],
            "embed_models": [],
            "accepts_any_model": False,
            "note": "没有任何云端 Key 时的兜底实现：全链路可跑，结果用于试用与联调，不追求真实质量。",
        },
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
                {"id": "stub", "label": "stub 模式（无 Key 可跑）"},
                {"id": "paraformer", "label": "paraformer（阿里云百炼，复用 DASHSCOPE_API_KEY）"},
            ],
            "note": "录音资料走哪条转写路径；paraformer 复用阿里云百炼的 Key。",
        },
        {
            "key": "search_provider",
            "label": "网络搜索",
            "options": [
                {"id": "auto", "label": "自动（有 Key 走博查，否则 stub 模式）"},
                {"id": "stub", "label": "stub 模式"},
                {"id": "bocha", "label": "博查（Bocha）"},
            ],
            "note": "题库的「网络」来源用它取题；无 Key 时走 stub 模式占位结果。",
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
        "装配：改供应商与模型时建议一次带上该家的 Key（`dashscope_api_key` / `deepseek_api_key` / "
        "`siliconflow_api_key` / 自定义服务的 `llm_api_key`），一次写入即从 stub 模式切到真实服务。"
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
