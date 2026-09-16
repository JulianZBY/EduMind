"""教学提纲生成。"""

import json

from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm

_OUTLINE_PROMPT = """你是教学设计师。根据教学意图和知识内容，生成教学提纲（大纲）。

要求：分章节、分知识点，层次清晰，用 Markdown 格式（# 章节、## 小节、- 知识点）。

教学意图：__INTENT__
知识内容：__KNOWLEDGE__
"""


async def generate_outline(intent: dict, knowledge: str) -> str:
    llm = get_llm()
    prompt = (
        _OUTLINE_PROMPT.replace("__INTENT__", json.dumps(intent, ensure_ascii=False)).replace(
            "__KNOWLEDGE__", knowledge[:6000]
        )
    )
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    return result.content
