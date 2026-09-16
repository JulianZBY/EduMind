"""教学意图分析：从自然语言提取结构化教学要素。"""

from pydantic import BaseModel, ValidationError

from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.llm.parsing import parse_json


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


def intent_from_payload(payload: dict) -> TeachingIntent:
    """产物区透传的意图结构 → TeachingIntent；结构不完整时退化为仅主题（一键生成不被前端字段变更卡死）。"""
    try:
        return TeachingIntent.model_validate(payload)
    except ValidationError:
        return TeachingIntent(topic=str(payload.get("topic") or ""))


async def analyze_intent(text: str) -> TeachingIntent:
    llm = get_llm()
    prompt = _INTENT_PROMPT.replace("__TEXT__", text)
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    return TeachingIntent(**data)
