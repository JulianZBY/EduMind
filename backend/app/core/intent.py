"""教学意图分析：从自然语言提取结构化教学要素。"""

import json
from functools import partial

from pydantic import BaseModel, ValidationError

from app.core.llm.base import ChatMessage
from app.core.llm.parsing import parse_json
from app.core.llm.task_routing import get_llm_for

# 「意图分析」任务：模型档位在设置页按任务选，未设置回落全局默认（CONTEXT.md「任务级模型」）。
# 入口仍叫 get_llm：既有测试用它替换对话能力（monkeypatch.setattr(本模块, "get_llm", ...)）。
get_llm = partial(get_llm_for, "intent")


class TeachingIntent(BaseModel):
    topic: str = ""
    grade: str = ""
    duration_minutes: int | None = None
    objectives: list[str] = []
    knowledge_points: list[str] = []
    key_points: list[str] = []
    difficult_points: list[str] = []
    style: str = ""
    teaching_methods: list[str] = []
    interactivity: str = ""


_INTENT_PROMPT = """你是教学智能体的意图分析模块。从教师的备课需求中提取结构化教学要素。

字段（无则用空字符串或空数组，duration_minutes 无则为 null）：
- topic: 教学主题
- grade: 学段/年级
- duration_minutes: 课时时长（数字，分钟）
- objectives: 教学目标（字符串数组）
- knowledge_points: 知识点（字符串数组）
- key_points: 重点（字符串数组）
- difficult_points: 难点（字符串数组）
- style: 风格偏好
- teaching_methods: 教学方法（字符串数组）
- interactivity: 互动需求描述

只输出 JSON，不要其他文字。

注意：教师需求是多轮累积表述。若前后矛盾（如时长、风格、目标前后不一致），以教师最新的表述为准。

教师需求：
__TEXT__
"""


# 互动产物诉求关键词：意图.interactivity 明确表达了想要互动产物（小游戏/动画等）才算命中；
# 「课堂提问」「课堂讨论」类教学互动需求不触发自动生成。
_INTERACTIVE_APPEAL_HINTS = ("小游戏", "游戏", "动画", "互动内容", "交互", "H5", "h5")


def wants_interactive_content(intent: TeachingIntent) -> bool:
    """互动诉求命中：意图的互动需求描述表达了明确的互动产物诉求。"""
    text = (intent.interactivity or "").strip()
    return any(hint in text for hint in _INTERACTIVE_APPEAL_HINTS)


# 增量累积提示词：与全量分析同一组字段与同一口径（最新表述为准），但只喂「已累积意图 + 本轮新增」，
# 不再把整段对话重析一遍。
_MERGE_PROMPT = """你是教学智能体的意图分析模块。把教师本轮新增表述合并进已累积的意图。

规则（字段与取值含义同全量分析）：
- 教师本轮明确新增或修改的字段，按本轮表述更新（含数组字段：本轮列了新内容就整体替换）；
- 本轮没有提到的字段，保持已累积意图的原值，不要清空、不要猜测；
- 前后矛盾（如时长、风格、目标不一致）以教师最新表述为准。

只输出合并后的完整 JSON，不要其他文字。

已累积的意图：
__INTENT__

教师本轮新增表述：
__TEXT__
"""

# 增量累积提示词里定位「本轮新增表述」的分隔标记（测试观测用，与提示词保持同一出处）
MERGE_TEXT_SEPARATOR = "教师本轮新增表述：\n"


def intent_from_payload(payload: dict) -> TeachingIntent:
    """产物区透传的意图结构 → TeachingIntent；结构不完整时退化为仅主题（一键生成不被前端字段变更卡死）。"""
    topic = payload.get("topic") or ""
    try:
        return TeachingIntent.model_validate(payload)
    except ValidationError:
        return TeachingIntent(topic=str(topic))


async def analyze_intent(text: str) -> TeachingIntent:
    """全量意图分析：从整段教师需求里提取结构化要素（无会话时的既有路径）。"""
    llm = get_llm()
    prompt = _INTENT_PROMPT.replace("__TEXT__", text)
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    return TeachingIntent(**data)


async def merge_intent(previous: TeachingIntent, utterance: str) -> TeachingIntent:
    """增量累积：把本轮新增表述合并进已累积意图（上一轮意图 + 本轮新增）。

    同一会话多轮对话不再每轮把全部历史重析一遍：只喂「已累积意图 + 本轮原话」，
    矛盾时以本轮表述为准（与全量分析同一口径，见 ADR-0002）。
    """
    llm = get_llm()
    prompt = _MERGE_PROMPT.replace(
        "__INTENT__", json.dumps(previous.model_dump(), ensure_ascii=False)
    ).replace("__TEXT__", utterance)
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    if not data:
        # 合并失败（模型输出不可解析）时保住已累积的意图，避免当场丢上下文
        return previous
    return TeachingIntent(**data)
