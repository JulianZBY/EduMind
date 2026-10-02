"""供应商目录与可选能力实现（CONTEXT.md「供应商目录」「自定义 OpenAI 兼容服务」「任务级模型」）。

同一份口径服务三件事：

- 设置页「能选什么」：`GET /api/v1/settings/catalog` 的下拉项只来自这里，前端不另立清单；
- 写设置时「填的值在不在目录里」：未知供应商 / 未知模型 / 未实现的实现都给出稳定错误码；
- 「目录之外」的唯一出口是**自定义 OpenAI 兼容服务**（base_url + 模型 ID + Key），单独一档。

目录不另立清单：供应商来自 `app.core.dialects.DIALECTS` 的方言预设，可选能力实现**直接取自各能力
注册表**（ADR-0003）——注册表加一行，设置页就多一个可选项。本模块只有数据与判定，不读写库。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.core import provider_config
from app.core.asr.factory import ASR_BUILDERS, get_transcriber
from app.core.dialects import DIALECTS, Dialect
from app.core.embedding.factory import EMBEDDING_BUILDERS, get_embedder
from app.core.parser.factory import PDF_BUILDERS, get_pdf_parser
from app.core.search.factory import SEARCH_BUILDERS, get_search
from app.knowledge.chunking.factory import CHUNKER_BUILDERS, get_chunker
from app.knowledge.retrieval.factory import RETRIEVER_BUILDERS, get_retriever

# 值来源口径（写入源头）：只有这四个词出现在设置页文案里，前后端抄同一份。
SOURCE_STORED = "设置页"
SOURCE_BOOTSTRAP = "引导默认"
SOURCE_TASK = "任务级"
SOURCE_DEFAULT = "全局默认"


class SettingsError(Exception):
    """设置值不在目录里：带稳定错误码 + 面向教师的信息（HTTP 层转 400，不落库、不抛栈）。"""

    def __init__(self, code: str, field: str, message: str) -> None:
        super().__init__(message)
        self.code = code  # 稳定机器码：unknown_provider / unknown_model / ...
        self.field = field  # 出错的设置项（app_settings.key，也是 Settings 字段名）
        self.message = message  # 面向教师的一句话（界面直接显示）


@dataclass(frozen=True)
class ProviderSpec:
    """供应商目录里的一家（或「自定义 OpenAI 兼容服务」这一档）。"""

    id: str  # 供应商名（也是 LLM_PROVIDER 的取值）
    label: str  # 面向教师的名称
    base_url: str  # 方言预设地址；自定义为空（由教师填）
    key_field: str  # 该供应商用哪个 Settings 字段存 Key；空 = 不需要 Key
    chat_models: tuple[str, ...]  # 目录内的对话模型（任务级模型档位也从这里选）
    vision_models: tuple[str, ...]  # 目录内的多模态模型（空 = 该供应商不提供）
    embed_models: tuple[str, ...]  # 目录内的向量化模型（空 = 该供应商不提供）
    accepts_any_model: bool = False  # 自定义服务：任意模型 ID 都放行
    note: str = ""


# 目录内补充的常用对话模型（预设里只带一个默认档位，这里给出可选的更便宜/更强的档位）
_EXTRA_CHAT_MODELS: dict[str, tuple[str, ...]] = {
    "qwen": ("qwen-turbo", "qwen-max"),
    "deepseek": ("deepseek-v4-pro",),
    "moonshot": ("kimi-k2-turbo-preview", "kimi-k2-0905-preview"),
    "zhipu": ("glm-4.5-air", "glm-4.5v", "glm-4-flash"),
    "minimax": ("MiniMax-M1", "abab6.5s-chat"),
    "ark": ("doubao-seed-1-6-flash-250715", "doubao-pro-32k"),
    "siliconflow": ("deepseek-ai/DeepSeek-V3",),
}

_PROVIDER_LABELS = {
    "qwen": "千问（Qwen）",
    "deepseek": "DeepSeek",
    "moonshot": "Kimi（月之暗面）",
    "zhipu": "智谱 GLM",
    "minimax": "MiniMax",
    "ark": "豆包（字节火山方舟）",
    "siliconflow": "硅基流动（SiliconFlow）",
}

_PROVIDER_NOTES = {
    "qwen": "千问官方 MaaS 平台：对话 + 多模态 + 向量化。",
    "deepseek": "对话 + 多模态（deepseek-flash / deepseek-v4-pro 均支持视觉）；向量化不提供。",
    "moonshot": "只提供对话；多模态与向量化不在此目录内。",
    "zhipu": "对话 + 多模态（glm-4.5v）+ 向量化（embedding-3）。",
    "minimax": "只提供对话；多模态与向量化不在此目录内。",
    "ark": "对话为主；模型 ID 也接受 ep- 接入点（目录外 ID 放行）。",
    "siliconflow": "对话 + 多模态 + 向量化。",
    "custom": "目录之外的接入方式：填 base_url + 模型 ID + Key 即可用。",
}

# 目录内补充的常用多模态模型（方言预设只带一个默认档位）
_EXTRA_VISION_MODELS: dict[str, tuple[str, ...]] = {
    "deepseek": ("deepseek-flash",),
}

# 目录之外模型 ID 放行的方言：豆包的 ep- 接入点与自定义服务一样不受目录限制
_ANY_MODEL_PROVIDERS = {"ark"}


def _dedupe(names: tuple[str, ...]) -> tuple[str, ...]:
    """去掉重复模型名但保持声明顺序（默认档与清单里的第一个常常是同一个）。"""
    seen: dict[str, None] = {}
    for name in names:
        if name:
            seen.setdefault(name, None)
    return tuple(seen)


def build_spec_from_dialect(dialect: Dialect) -> ProviderSpec:
    """方言 → 目录里的供应商行。内置方言用预设 label/note；配置声明的家自带名称与说明。"""
    return ProviderSpec(
        id=dialect.name,
        label=dialect.label or _PROVIDER_LABELS.get(dialect.name, dialect.name),
        base_url=dialect.base_url,
        key_field=dialect.api_key_field,
        chat_models=_dedupe(
            (dialect.chat_model, *_EXTRA_CHAT_MODELS.get(dialect.name, ()), *dialect.extra_chat_models)
        ),
        vision_models=(
            _dedupe((dialect.vision_model, *_EXTRA_VISION_MODELS.get(dialect.name, ()), *dialect.extra_vision_models))
            if dialect.vision_model
            else ()
        ),
        embed_models=(dialect.embed_model,) if dialect.embed_model else (),
        accepts_any_model=dialect.name in _ANY_MODEL_PROVIDERS,
        note=dialect.note or _PROVIDER_NOTES.get(dialect.name, "由 providers.json 声明的服务商。"),
    )
def _build_providers() -> dict[str, ProviderSpec]:
    providers: dict[str, ProviderSpec] = {
        name: build_spec_from_dialect(dialect) for name, dialect in DIALECTS.items()
    }
    providers["custom"] = ProviderSpec(
        id="custom",
        label="自定义 OpenAI 兼容服务",
        base_url="",
        key_field="llm_api_key",
        chat_models=(),
        vision_models=(),
        embed_models=(),
        accepts_any_model=True,
        note=_PROVIDER_NOTES["custom"],
    )
    return providers


# 声明式扩展：`providers.json` 里声明的家先并进方言表，再据方言表建目录——
# 顺序有意如此，保证「配置文件写了什么，设置页就列什么」，且不依赖模块 import 的先后。
provider_config.ensure_merged()
PROVIDERS: dict[str, ProviderSpec] = _build_providers()


@dataclass(frozen=True)
class TaskSpec:
    """一个任务级模型的档位（CONTEXT.md「任务级模型」）。"""

    id: str  # 调用方用的任务名
    label: str  # 面向教师的名称
    field: str  # 存放该任务模型档位的 Settings 字段（空 = 用供应商实例的默认模型）
    provider_field: str  # 存放该任务供应商实例 id 的 Settings 字段（空 = 跟随全局默认供应商）


TASKS: tuple[TaskSpec, ...] = (
    TaskSpec("intent", "意图分析", "task_model_intent", "task_provider_intent"),
    TaskSpec("generate", "生成", "task_model_generate", "task_provider_generate"),
    TaskSpec("conflict", "冲突比对", "task_model_conflict", "task_provider_conflict"),
)

TASKS_BY_ID: dict[str, TaskSpec] = {spec.id: spec for spec in TASKS}


@dataclass(frozen=True)
class OptionSpec:
    """能力的一个可选实现（下拉里的一行）。"""

    id: str  # 注册表里的实现名（也是配置取值）
    label: str  # 面向教师的说明


@dataclass(frozen=True)
class CapabilitySpec:
    """一项可切换的云端能力：可选实现来自能力注册表，就绪探针用工厂当场构造一次。"""

    key: str  # Settings 字段名（也是 app_settings.key）
    label: str  # 面向教师的能力名
    registry: Mapping[str, Any]  # 该能力的实现注册表（可选实现 = 注册表的键）
    order: tuple[str, ...]  # 下拉展示顺序（不在注册表里的忽略）
    probe: Callable[[], object]  # 就绪探针：无 Key 时抛可读错误
    auto_id: str = ""  # 「留空 = 自动」时对应的实现名（空 = 该能力没有自动档）
    note: str = ""

    @property
    def options(self) -> tuple[OptionSpec, ...]:
        """可选实现 = 注册表里有什么就列什么，按声明顺序排，未列到的补在后面。"""
        names = [name for name in self.order if name in self.registry]
        names += [name for name in self.registry if name not in names]
        labels = _OPTION_LABELS.get(self.key, {})
        return tuple(OptionSpec(name, labels.get(name, name)) for name in names)

    def option_label(self, value: str) -> str:
        for option in self.options:
            if option.id == value:
                return option.label
        return value


_OPTION_LABELS: dict[str, dict[str, str]] = {
    "asr_provider": {
        "auto": "自动（有百炼 Key 走 paraformer，否则未配置）",
        "paraformer": "paraformer（阿里云百炼录音转写：需要百炼 Key，千问 MaaS 不提供）",
    },
    "pdf_strategy": {
        "mineru_then_pypdf": "mineru → pypdf 兜底（默认）",
        "pypdf": "pypdf（纯本地，不联网）",
        "mineru": "mineru（仅云端，失败即失败）",
    },
    "search_provider": {
        "auto": "自动（有 Key 走博查，未配置则提示去配置）",
        "bocha": "博查（Bocha）",
    },
    "embedding_provider": {
        "auto": "自动（跟随对话供应商，未配置时本地 hash）",
        "hash": "hash（本地确定性兜底向量）",
        "openai": "自定义 OpenAI 兼容 /embeddings",
        "qwen": "千问 text-embedding-v3",
        "siliconflow": "硅基流动 BAAI/bge-large-zh-v1.5",
    },
    "retrieval_strategy": {
        "vector_graph": "向量 + 图谱融合（默认）",
        "vector": "纯向量",
    },
    "chunk_strategy": {"paragraph": "按段落与标题边界（默认）"},
}

CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        key="asr_provider",
        label="语音转写",
        registry=ASR_BUILDERS,
        order=("paraformer",),
        probe=get_transcriber,
        note="录音资料走哪条转写路径；paraformer 是阿里云百炼的服务（千问 MaaS 不提供，需要专门的百炼 Key）。",
    ),
    CapabilitySpec(
        key="pdf_strategy",
        label="PDF 解析",
        registry=PDF_BUILDERS,
        order=("mineru_then_pypdf", "pypdf", "mineru"),
        probe=get_pdf_parser,
        note="云端解析失败是否退本地 pypdf；pypdf 档完全不联网。",
    ),
    CapabilitySpec(
        key="search_provider",
        label="网络搜索",
        registry=SEARCH_BUILDERS,
        order=("auto", "bocha"),
        probe=get_search,
        auto_id="auto",
        note="题库的「网络」来源用它取题；未配置博查 Key 时给出「去配置」提示，不返回占位结果。",
    ),
    CapabilitySpec(
        key="embedding_provider",
        label="向量化",
        registry=EMBEDDING_BUILDERS,
        order=("auto", "hash", "openai", "qwen", "siliconflow"),
        probe=get_embedder,
        auto_id="auto",
        note="独立于对话供应商；未配置时用本地 hash（真实算法，检索质量降级）；换口径后向量库需重建。",
    ),
    CapabilitySpec(
        key="retrieval_strategy",
        label="检索策略",
        registry=RETRIEVER_BUILDERS,
        order=("vector_graph", "vector"),
        probe=get_retriever,
        note="是否把知识图谱邻接融合进检索上下文。",
    ),
    CapabilitySpec(
        key="chunk_strategy",
        label="分块策略",
        registry=CHUNKER_BUILDERS,
        order=("paragraph",),
        probe=get_chunker,
        note="资料切分成可检索小段的切法。",
    ),
)

CAPABILITIES_BY_KEY: dict[str, CapabilitySpec] = {spec.key: spec for spec in CAPABILITIES}


@dataclass(frozen=True)
class FieldSpec:
    """一个可在设置页改的项。kind 决定怎么校验（见 validate_patch）。"""

    name: str  # Settings 字段名（也是 app_settings.key）
    label: str  # 面向教师的名称
    kind: str  # provider / key / url / chat_model / vision_model / embed_model / capability / task_model


# 全部可在设置页改的项：设置库只接受这里登记过的键（未登记 = 未知设置项）。
# 这里是本票的字段单一出处：写入校验、回读装配、请求体字段都对它。
FIELDS: dict[str, FieldSpec] = {
    spec.name: spec
    for spec in (
        FieldSpec("llm_provider", "供应商", "provider"),
        FieldSpec("llm_base_url", "服务商地址（base_url）", "url"),
        FieldSpec("llm_model", "对话模型", "chat_model"),
        FieldSpec("llm_vision_model", "多模态模型", "vision_model"),
        FieldSpec("embedding_base_url", "向量化服务地址（base_url）", "url"),
        FieldSpec("embedding_model", "向量化模型", "embed_model"),
        FieldSpec("llm_api_key", "自定义服务的 API Key", "key"),
        FieldSpec("qwen_api_key", "千问 API Key", "key"),
        FieldSpec("deepseek_api_key", "DeepSeek API Key", "key"),
        FieldSpec("moonshot_api_key", "Kimi API Key", "key"),
        FieldSpec("zhipu_api_key", "智谱 API Key", "key"),
        FieldSpec("minimax_api_key", "MiniMax API Key", "key"),
        FieldSpec("ark_api_key", "豆包 API Key", "key"),
        FieldSpec("siliconflow_api_key", "硅基流动 API Key", "key"),
        FieldSpec("embedding_api_key", "向量化 API Key", "key"),
        FieldSpec("mineru_token", "MinerU Token", "key"),
        FieldSpec("asr_api_key", "百炼语音转写 Key", "key"),
        FieldSpec("bocha_api_key", "博查搜索 Key", "key"),
        # 多供应商：默认实例与任务级实例指针（存在性由 API 层对着实例表校验）
        FieldSpec("default_provider_instance", "默认供应商", "provider_instance"),
        *(FieldSpec(spec.provider_field, spec.label, "provider_instance") for spec in TASKS),
        *(FieldSpec(spec.key, spec.label, "capability") for spec in CAPABILITIES),
        *(FieldSpec(spec.field, spec.label, "task_model") for spec in TASKS),
    )
}

MANAGED_FIELDS: tuple[str, ...] = tuple(FIELDS)

# Key 项与可编辑项（非 Key）两份视图：设置页分卡片展示、回读时分两种形状（Key 只给掩码）。
KEY_FIELDS: tuple[FieldSpec, ...] = tuple(spec for spec in FIELDS.values() if spec.kind == "key")
ITEM_FIELDS: tuple[FieldSpec, ...] = tuple(
    spec
    for spec in FIELDS.values()
    if spec.kind in ("url", "chat_model", "vision_model", "embed_model")
)


def provider_of(values: Mapping[str, str]) -> str:
    """取值集合里的供应商名（小写去空白）；认不出来时为空。"""
    return (values.get("llm_provider") or "").strip().lower()


def normalize(name: str, value: str) -> str:
    """写库前的规范化：一律去空白，供应商与能力实现名落小写（注册表按小写名选择）。"""
    value = (value or "").strip()
    spec = FIELDS.get(name)
    if spec is not None and spec.kind in ("provider", "capability"):
        return value.lower()
    return value

def validate_patch(
    values: Mapping[str, str],
    current: Mapping[str, str],
    instance_dialects: Mapping[str, str] | None = None,
) -> None:
    """目录口径校验：不在目录里的值一律抛 SettingsError（调用方据此返回明确错误码）。

    `current` 是当前生效值，用于跨字段判断；`instance_dialects` 是供应商实例 id → 方言 id
    的映射（多供应商）：任务级模型落在哪个方言的目录里，取决于该任务指向的实例
    （`task_provider_*`，没指则默认实例）；没有实例映射时回落 legacy 单供应商（`llm_provider`）。
    """
    instances = instance_dialects or {}
    provider_id = provider_of(values) or provider_of(current)
    if ("llm_provider" in values or "llm_provider" in current) and provider_id:
        # 空 = 未配置，合法状态（产品没有假数据兜底）
        _check_provider(provider_id)

    for name, raw in values.items():
        spec = FIELDS.get(name)
        if spec is None:
            raise SettingsError("unknown_setting", name, f"未知设置项：{name}")
        value = normalize(name, raw)
        if not value:
            continue  # 空 = 清除该项设置（回落 .env 引导默认），无值可校验
        if spec.kind == "provider":
            _check_provider(value)
        elif spec.kind == "url":
            _check_url(spec, value)
        elif spec.kind in ("chat_model", "vision_model"):
            # 实例路径（多供应商）：模型池由 /v1/models 动态拉取 + 手动填写，不做硬编码目录校验
            dialect = _dialect_for_global(values, current, instances)
            if dialect:
                _check_model(spec, value, dialect)
        elif spec.kind == "task_model":
            dialect = _dialect_for_task(name, values, current, instances)
            if dialect:
                _check_model(spec, value, dialect)
        elif spec.kind == "capability":
            _check_capability(name, value)
        # embed_model：向量化是独立轴（EMBEDDING_PROVIDER=openai 时就是任意模型 ID），不做目录校验
        # provider_instance：目录校验无从谈起，存在性由 API 层对着实例表校验（unknown_provider_instance）

TASKS_BY_FIELD: dict[str, TaskSpec] = {spec.field: spec for spec in TASKS}


def _dialect_for_global(
    values: Mapping[str, str],
    current: Mapping[str, str],
    instances: Mapping[str, str],
) -> str:
    """全局模型项（llm_model / llm_vision_model）落在哪个目录里校验。

    指到供应商实例时返回空字符串：模型池动态拉取 + 手动填写，不按硬编码目录校验；
    未指实例（legacy 单供应商路径）时返回方言 id，照旧按目录校验。
    """
    default_id = (
        values.get("default_provider_instance") or current.get("default_provider_instance") or ""
    ).strip()
    if default_id in instances:
        return ""  # 实例路径：跳过目录校验（动态模型池）
    return provider_of(values) or provider_of(current)


def _dialect_for_task(
    name: str,
    values: Mapping[str, str],
    current: Mapping[str, str],
    instances: Mapping[str, str],
) -> str:
    """任务级模型落在哪个目录里校验：指了实例（动态模型池）返回空，否则走全局口径。"""
    task = TASKS_BY_FIELD.get(name)
    if task is not None:
        instance_id = (
            values.get(task.provider_field) or current.get(task.provider_field) or ""
        ).strip()
        if instance_id in instances:
            return ""  # 实例路径：跳过目录校验（动态模型池）
    return _dialect_for_global(values, current, instances)

def _check_provider(value: str) -> str:
    if value in PROVIDERS:
        return value
    raise SettingsError(
        "unknown_provider",
        "llm_provider",
        f"未知供应商：{value or '（空）'}（可选：{'、'.join(PROVIDERS)}；"
        "目录之外的服务商请用「自定义 OpenAI 兼容服务」）",
    )


def _check_url(spec: FieldSpec, value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return
    raise SettingsError(
        "invalid_base_url",
        spec.name,
        f"{spec.label}必须是 http(s) 开头的完整地址，例如 https://example.com/v1；当前值：{value}",
    )


def _check_model(spec: FieldSpec, value: str, provider_id: str) -> None:
    provider = PROVIDERS.get(provider_id)
    if provider is None or provider.accepts_any_model:
        return  # 自定义服务接受任意模型 ID（目录之外的接入方式）
    allowed = provider.vision_models if spec.kind == "vision_model" else provider.chat_models
    if value in allowed:
        return
    raise SettingsError(
        "unknown_model",
        spec.name,
        f"未知模型：{value}（「{provider.label}」的{spec.label}可选："
        f"{'、'.join(allowed) if allowed else '无'}；目录之外的模型请用「自定义 OpenAI 兼容服务」）",
    )


def _check_capability(name: str, value: str) -> None:
    spec = CAPABILITIES_BY_KEY[name]
    if value in spec.registry:
        return
    raise SettingsError(
        "unknown_capability_impl",
        spec.key,
        f"未实现的{spec.label}：{value}（可选：{'、'.join(option.id for option in spec.options)}）",
    )


def probe(factory: Callable[[], object]) -> tuple[bool, str]:
    """就绪探针：用工厂当场构造一次实现。

    构造是离线的（不联网、不发请求），缺 Key 时实现自己抛可读错误——直接把它当原因回给教师，
    比让页面显示「已配置」再用起来报错更早暴露问题。
    """
    try:
        factory()
    # 探针只负责「现在能不能用」，各实现抛什么不重要，原因原样转述给教师
    except Exception as error:  # noqa: BLE001
        return False, str(error)
    return True, ""
