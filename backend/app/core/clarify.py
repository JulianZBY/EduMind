"""需求澄清：按追问粒度主动提问，补齐模糊需求。"""

from app.core.intent import TeachingIntent

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
