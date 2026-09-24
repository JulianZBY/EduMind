"""需求澄清：按追问粒度主动提问，补齐模糊需求；跳过追问为语义判定。"""

from app.core.intent import TeachingIntent
from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.llm.parsing import parse_json

# 每个字段对应的追问话术
FIELD_QUESTIONS = {
    "duration_minutes": "这节课计划多长时间？（如 45 分钟）",
    "style": "希望课件是什么风格？（简约/学术/活泼）",
    "objectives": "这节课想达到什么教学目标？",
    "key_points": "有哪些重点需要突出？",
    "interactivity": "需要哪些互动环节？（提问/讨论/小游戏）",
    "teaching_methods": "偏好哪些教学方法？（讲授/案例/探究）",
}

# 各粒度需要确认的字段（按优先级）
GRANULARITY_FIELDS = {
    "快速": ["duration_minutes", "style"],
    "标准": ["duration_minutes", "style", "objectives", "key_points"],
    "精细": [
        "duration_minutes",
        "style",
        "objectives",
        "key_points",
        "interactivity",
        "teaching_methods",
    ],
}


def missing_fields(intent: TeachingIntent, granularity: str) -> list[str]:
    """返回按粒度仍缺失的要素字段。"""
    fields = GRANULARITY_FIELDS.get(granularity, GRANULARITY_FIELDS["标准"])
    missing = []
    for f in fields:
        val = getattr(intent, f, None)
        if not val:  # None / 空串 / 空列表 均视为缺失
            missing.append(f)
    return missing


def build_question(missing: list[str]) -> str:
    """按优先级返回第一个缺失字段的追问。"""
    if not missing:
        return ""
    return FIELD_QUESTIONS.get(missing[0], "请补充更多教学需求信息")


# 跳过追问的语义判定提示词：按意思判，不按字面词匹配（CONTEXT.md「跳过追问」）。
# 提示词首句是判定器标记：网关（含 stub）按它路由，测试也按它认出「这是语义判定」。
_SKIP_PROMPT = """你是备课会话的语义判定器：判断教师最新这一句话是否表示「信息已经够用，直接给结果」。

判定规则（按意思判断，不要按字面匹配）：
- 「不用再问了」「需求都清楚了」「直接给结果」这类**不同说法**意思相同即算跳过；
- 字面出现「生成」但教师在否定、推迟或只是描述（如「先别生成」「生成之前我还想补充」）不算跳过；
- 还在补充信息、提问、表示不确定或犹豫，都不算跳过。

当前仍缺的要素：__MISSING__
教师最新表述：__TEXT__

只输出 JSON：{"skip": true 或 false}
"""

SKIP_JUDGEMENT_MARKER = "备课会话的语义判定器"


async def should_skip_clarification(utterance: str, missing: list[str]) -> bool:
    """语义判定教师最新表述是否表示「信息够了，直接出结果」。

    判定基于语义而非字面：同义改写能命中，字面像但语义相反（否定 / 推迟）的不命中。
    判定环节本身不打断备课：模型输出不可解析时保守地继续追问。
    """
    llm = get_llm()
    prompt = _SKIP_PROMPT.replace("__MISSING__", "、".join(missing) or "无").replace(
        "__TEXT__", utterance
    )
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    return parse_json(result.content).get("skip") is True
