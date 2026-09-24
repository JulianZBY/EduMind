"""课件/教案迭代优化：理解修改意见，调整完整结构再渲染。"""

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
