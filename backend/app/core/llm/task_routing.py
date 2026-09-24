"""任务级模型（CONTEXT.md「任务级模型」）：意图分析 / 生成 / 冲突比对各选一个档位。

三个任务各有一个设置项（`TASK_MODEL_*`），留空 = **回落全局默认**（`LLM_MODEL`，或当前方言预设的
对话模型）。调用方只换工厂入口（`get_llm()` → `get_llm_for("generate")`），其余一行不用改：

- 没设任务档位时直接返回全局默认 provider，行为与收编前完全一致；
- 设了任务档位时返回一个把 `model` 注入每次 `chat` 的代理——各家 OpenAI 兼容实现都认这个入参。

「该任务实际用的模型」由 `model_for()` 给出，设置页的查询接口据此回读（行为可见）。
"""

from app.config import settings
from app.core.catalog import SOURCE_DEFAULT, SOURCE_TASK, TASKS, TASKS_BY_ID, TaskSpec
from app.core.dialects import DIALECTS
from app.core.llm import factory as llm_factory
from app.core.llm.base import ChatMessage, ChatResult, LLMProvider


def task_spec(task: str) -> TaskSpec:
    """按任务名取档位定义；陌生任务名给出可选项（调用方写错时当场可见，而不是静默走默认）。"""
    spec = TASKS_BY_ID.get(task)
    if spec is None:
        raise ValueError(f"未知任务：{task}（可选：{'、'.join(spec.id for spec in TASKS)}）")
    return spec


def global_default_model() -> str:
    """全局默认对话模型：显式 `LLM_MODEL` 优先，否则取当前方言预设的对话模型。

    stub 模式没有模型档位（返回空），此时任务级模型也无从谈起——不会凭空造一个模型名出来。
    """
    provider = (settings.llm_provider or "").strip().lower()
    preset = DIALECTS.get(provider)
    return (settings.llm_model or (preset.chat_model if preset else "")).strip()


def model_for(task: str) -> tuple[str, str]:
    """该任务实际用的模型与它的来源（任务级 / 全局默认）。"""
    spec = task_spec(task)
    chosen = (getattr(settings, spec.field) or "").strip()
    if chosen:
        return chosen, SOURCE_TASK
    return global_default_model(), SOURCE_DEFAULT


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
    """按任务取对话能力：设了任务档位就注入它，没设则直接用全局默认 provider。"""
    provider = llm_factory.get_llm()  # 经模块属性取，保住既有测试替换工厂的接缝
    model, source = model_for(task)
    if source != SOURCE_TASK or not model:
        return provider
    return TaskModelProvider(provider, model)
