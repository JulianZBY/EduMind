"""五类生成物的迭代优化：理解修改意见，调整完整内容再渲染（产出新版本，不覆盖旧版）。

课件与教案调整结构（slides / word），提纲调整 Markdown 正文，试卷调整题目集合，
互动内容调整单文件 HTML；共同不变式是「模型没给出可用结果时保留基线内容」——
宁可产出一版内容不变的产出，也不产出一版坏内容。
"""

import json
from functools import partial

from app.core.llm.base import ChatMessage
from app.core.llm.parsing import parse_json
from app.core.llm.task_routing import get_llm_for

# 「生成」任务：模型档位在设置页按任务选，未设置回落全局默认（CONTEXT.md「任务级模型」）。
# 入口仍叫 get_llm：既有测试用它替换对话能力（monkeypatch.setattr(本模块, "get_llm", ...)）。
get_llm = partial(get_llm_for, "generate")

_REVISE_PPT_PROMPT = """你是课件优化助手。根据教师的修改意见，调整已有的 PPT 结构。

当前 PPT 结构（JSON，每页 role + title + points；role 为页面角色标注，保持各页原值不变）：
__CURRENT__

修改意见：
__FEEDBACK__

请输出调整后的完整 PPT 结构，保持 JSON 格式（即使只改一页，也要输出全部页面）：
{"slides": [{"role": "封面|目录|内容|总结", "title": "...", "points": ["..."]}]}

只输出 JSON，不要其他文字。
"""


async def revise_ppt(slides: list[dict], feedback: str) -> list[dict]:
    """根据修改意见调整 PPT 结构，返回新的 slides。"""
    llm = get_llm()
    prompt = _REVISE_PPT_PROMPT.replace(
        "__CURRENT__", json.dumps(slides, ensure_ascii=False)
    ).replace("__FEEDBACK__", feedback)
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    return data.get("slides", slides)


# 与课件同模式：完整结构交 LLM 重排后重新渲染；即使只改一处也要求输出全部字段。
_REVISE_WORD_PROMPT = """你是教案优化助手。根据教师的修改意见，调整已有的教案结构。

当前教案结构（JSON）：
__CURRENT__

修改意见：
__FEEDBACK__

请输出调整后的完整教案结构，保持 JSON 格式（即使只改一处，也要输出全部字段）：
{"objectives": {"knowledge": ["..."], "ability": ["..."], "emotion": ["..."]}, "key_points": ["..."], "difficult_points": ["..."], "process": [{"stage": "...", "minutes": 5, "content": "..."}], "activities": ["..."], "homework": ["..."]}

只输出 JSON，不要其他文字。
"""


async def revise_word(word: dict, feedback: str) -> dict:
    """根据修改意见调整教案结构，返回新的完整结构。"""
    llm = get_llm()
    prompt = _REVISE_WORD_PROMPT.replace(
        "__CURRENT__", json.dumps(word, ensure_ascii=False)
    ).replace("__FEEDBACK__", feedback)
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    return data if data else word


# ---- 提纲：修改意见作用在 Markdown 正文上 ----

_REVISE_OUTLINE_PROMPT = """你是教学设计师。根据教师的修改意见，调整已有的教学提纲。

当前提纲（Markdown）：
__CURRENT__

修改意见：
__FEEDBACK__

请输出调整后的**完整**提纲（Markdown 格式：`#` 章节、`##` 小节、`-` 知识点），保持 JSON 格式：
{"outline": "# 章节\\n## 小节\\n- 知识点"}

只输出 JSON，不要其他文字。
"""


async def revise_outline(text: str, feedback: str) -> str:
    """根据修改意见调整提纲正文；模型没给出可解析正文时保留基线正文。"""
    llm = get_llm()
    prompt = _REVISE_OUTLINE_PROMPT.replace("__CURRENT__", text).replace(
        "__FEEDBACK__", feedback
    )
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    revised = data.get("outline")
    return revised.strip() if isinstance(revised, str) and revised.strip() else text


# ---- 试卷：修改意见作用在题目集合上（改后的题目仍入题库）----

_REVISE_EXAM_PROMPT = """你是出题专家。根据教师的修改意见，调整已有试卷的题目。

当前试题（JSON 数组，每题含 type / content / answer / analysis / knowledge_point，选择题附 options）：
__CURRENT__

修改意见：
__FEEDBACK__

要求：
- 生成 __N__ 道题，题型覆盖选择/填空/简答
- 按修改意见调整；局部调整不要推翻整套题
- 每题仍带 knowledge_point（本题考查的知识点，取自当前试题里的知识点名称），选择题附 options

只输出 JSON，不要其他文字：
{"questions": [{"type": "选择", "content": "题目", "options": ["A. …", "B. …"], "answer": "答案", "analysis": "解析", "knowledge_point": "知识点"}]}
"""


async def revise_exam(questions: list[dict], feedback: str, n: int | None = None) -> list[dict]:
    """根据修改意见重做题目集合；模型没给出可用题目时保留基线题目。"""
    llm = get_llm()
    wanted = n if n and n > 0 else (len(questions) or 5)
    prompt = (
        _REVISE_EXAM_PROMPT.replace("__N__", str(wanted))
        .replace("__CURRENT__", json.dumps(questions, ensure_ascii=False))
        .replace("__FEEDBACK__", feedback)
    )
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    revised = data.get("questions")
    if isinstance(revised, list) and revised:
        return revised
    return questions


# ---- 互动内容：修改意见作用在单文件 HTML 上 ----

# 提示词里保留「HTML5 互动学习小游戏」这一句：stub provider 按它命中固定的单文件 HTML，
# 无 Key 时互动内容的修改同样能走通（与生成路径同一口径）。
_REVISE_CREATIVE_PROMPT = """你是创意内容设计师。根据教师的修改意见，调整已有的 HTML5 互动学习小游戏。

当前单文件 HTML：
__CURRENT__

修改意见：
__FEEDBACK__

要求：
- 仍是单文件 HTML5（内联 CSS + JS，无外部依赖）
- 面向学生互动学习，界面友好
- 直接输出完整 HTML 代码，不要解释
"""


def _extract_html(text: str) -> str:
    """从模型回复里取出 HTML 正文（与 `generate/creative.py` 同一口径：剥代码围栏）。"""
    import re

    match = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    start = text.find("<")
    return (text[start:] if start != -1 else text).strip()


async def revise_creative(html: str, feedback: str) -> str:
    """根据修改意见调整互动内容 HTML；模型没给出单文件 HTML 时保留基线 HTML。"""
    llm = get_llm()
    prompt = _REVISE_CREATIVE_PROMPT.replace("__CURRENT__", html).replace(
        "__FEEDBACK__", feedback
    )
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    revised = _extract_html(result.content)
    lowered = revised.lower()
    # 与生成路径同一判据：不是完整单文件 HTML 就退回基线内容（不落半成品）
    if not (lowered.lstrip().startswith("<!doctype") or "<html" in lowered):
        return html
    return revised
