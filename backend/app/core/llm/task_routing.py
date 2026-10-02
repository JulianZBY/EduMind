"""任务级模型（CONTEXT.md「任务级模型」）：意图分析 / 生成 / 冲突比对各选「供应商实例 + 模型」。

三个任务各有两个设置项：`task_provider_*`（供应商实例 id，设置页「添加供应商」产生）与
`task_model_*`（该实例方言目录里的模型）。留空回落：模型留空 = 实例的默认模型；实例留空 =
全局默认（默认实例，没有实例则 legacy 单供应商）。调用方只换工厂入口
（`get_llm()` → `get_llm_for("generate")`），其余一行不用改。

「该任务实际用的是哪家哪个模型」由 `routing_for()` 给出，设置页的查询接口据此回读。
"""

from app.config import settings
from app.core.catalog import SOURCE_DEFAULT, SOURCE_TASK, TASKS, TASKS_BY_ID, TaskSpec
from app.core.dialects import DIALECTS
from app.core.llm import factory as llm_factory
from app.core.llm import provider_instances
from app.core.llm.base import ChatMessage, ChatResult, LLMProvider


def task_spec(task: str) -> TaskSpec:
    """按任务名取档位定义；陌生任务名给出可选项（调用方写错时当场可见，而不是静默走默认）。"""
    spec = TASKS_BY_ID.get(task)
    if spec is None:
        raise ValueError(f"未知任务：{task}（可选：{'、'.join(spec.id for spec in TASKS)}）")
    return spec


def instance_for_task(spec: TaskSpec):
    """该任务指向的供应商实例行；没指（或指向的行没了）返回 None，调用方回落全局默认。"""
    instance_id = (getattr(settings, spec.provider_field) or "").strip()
    if not instance_id:
        return None
    return provider_instances.get_instance(instance_id)


def global_default_model() -> str:
    """全局默认对话模型：默认实例的默认模型优先，否则 legacy 口径
    （显式 `LLM_MODEL`，或当前方言预设的对话模型）。"""
    instance = provider_instances.default_instance()
    if instance is not None:
        return (settings.llm_model or provider_instances.effective_model(instance)).strip()
    provider = (settings.llm_provider or "").strip().lower()
    preset = DIALECTS.get(provider)
    return (settings.llm_model or (preset.chat_model if preset else "")).strip()


def model_for(task: str) -> tuple[str, str]:
    """该任务实际用的模型与它的来源（任务级 / 全局默认）。"""
    spec = task_spec(task)
    chosen = (getattr(settings, spec.field) or "").strip()
    if chosen:
        return chosen, SOURCE_TASK
    instance = instance_for_task(spec)
    if instance is not None:
        # 指了实例但没选模型：用实例的默认模型（仍是任务级口径，来源标任务级）
        model = provider_instances.effective_model(instance)
        if model:
            return model, SOURCE_TASK
    return global_default_model(), SOURCE_DEFAULT


def routing_for(task: str) -> tuple[str, str, str, str]:
    """该任务的路由回读：实例 id、实例名、模型、来源（设置页 TaskModelView 据此装配）。"""
    spec = task_spec(task)
    instance = instance_for_task(spec)
    model, source = model_for(task)
    if instance is not None:
        return instance.id, instance.label, model, source
    default = provider_instances.default_instance()
    if default is not None:
        return default.id, default.label, model, source
    provider = (settings.llm_provider or "").strip().lower()
    preset = DIALECTS.get(provider)
    return "", preset.name if preset else provider, model, source


class TaskModelProvider(LLMProvider):
    """把任务级模型档位注入每次对话的代理：`chat` 带上 `model`，`vision` 原样转发。"""

    def __init__(self, inner: LLMProvider, model: str) -> None:
        self.inner = inner
        self.model = model
        self.name = inner.name

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        kwargs.setdefault("model", self.model)
        return await self.inner.chat(messages, **kwargs)

    async def vision(self, image_path: str, prompt: str) -> str:
        return await self.inner.vision(image_path, prompt)


def get_llm_for(task: str) -> LLMProvider:
    """按任务取对话能力：指了实例就连供应商带模型一起用实例的；否则用全局默认。"""
    spec = task_spec(task)
    instance = instance_for_task(spec)
    model, source = model_for(task)
    if instance is not None:
        # 指定实例：地址 / Key 来自实例行，模型注入每次 chat（模型可能回落实例默认）
        return provider_instances.provider_of_instance(instance.id, model)  # type: ignore[return-value]
    provider = llm_factory.get_llm()  # 经模块属性取，保住既有测试替换工厂的接缝
    if source != SOURCE_TASK or not model:
        return provider
    return TaskModelProvider(provider, model)
