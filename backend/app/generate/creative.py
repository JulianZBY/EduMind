"""创意内容生成：HTML5 互动小游戏 / 知识点动画。"""

import re
from pathlib import Path

from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.generate import unique_output_path

_CREATIVE_PROMPT = """你是创意内容设计师。根据下面的知识点，生成一个 HTML5 互动学习小游戏或知识点动画。

要求：
- 单文件 HTML（内联 CSS + JS，无外部依赖）
- 面向学生互动学习，界面友好
- 直接输出完整 HTML 代码，不要解释

知识点：__KNOWLEDGE__
"""


def _extract_html(text: str) -> str:
    m = re.search(r"```(?:html)?\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    start = text.find("<")
    return text[start:] if start != -1 else text


async def generate_html_creative(knowledge: str) -> str:
    llm = get_llm()
    prompt = _CREATIVE_PROMPT.replace("__KNOWLEDGE__", knowledge[:4000])
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    return _extract_html(result.content)


def save_html(html: str, output_path: str | None = None) -> str:
    """保存 .html，返回路径。newline=""：按原样写入，单文件产物与内存内容字节一致。"""
    if output_path is None:
        output_path = unique_output_path("creative", ".html")
    Path(output_path).write_text(html, encoding="utf-8", newline="")
    return output_path
