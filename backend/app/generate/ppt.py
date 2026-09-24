"""PPT 课件生成：LLM 生成结构（页面角色标注）+ python-pptx 角色化主题渲染。"""

import json

import pptx
from pptx.dml.color import RGBColor

from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.llm.parsing import parse_json
from app.generate import unique_output_path
from app.generate.ppt_layout import render_editorial

# 页面角色：生成 prompt 的约定字段，渲染器据此差异化版式（缺失/未知回退默认版式）
ROLE_COVER = "封面"
ROLE_TOC = "目录"
ROLE_CONTENT = "内容"
ROLE_SUMMARY = "总结"

_PPT_PROMPT = """你是教学课件设计师。根据教学意图和知识内容，生成 PPT 结构。

要求：
- 结构：封面 → 目录 → 内容页(3-6页) → 总结页
- 每页标注角色：role 取值 封面/目录/内容/总结，与页面在结构中的位置对应
- 每页：role + title（≤15字）+ points（要点，≤5条，每条≤30字）
- 逻辑清晰、图文并茂

只输出 JSON，不要其他文字：
{"slides": [{"role": "封面|目录|内容|总结", "title": "...", "points": ["..."]}]}

教学意图：__INTENT__
知识内容：__KNOWLEDGE__
"""

# 三套配色主题映射教师风格偏好：简约=黑白灰、学术=深蓝、活泼=暖橙；
# 风格未表达或无匹配时回退默认主题。配图不做，由教师自行添加。
PPT_THEMES: dict[str, dict[str, str]] = {
    "简约": {"accent": "404040", "title": "1A1A1A", "text": "333333"},
    "学术": {"accent": "1F3864", "title": "1F3864", "text": "262626"},
    "活泼": {"accent": "E8642C", "title": "C55A11", "text": "404040"},
}
_DEFAULT_STYLE = "简约"


def theme_for_style(style: str) -> dict[str, RGBColor]:
    """风格偏好 → 配色主题（RGB）；偏好为空或无匹配时回退默认主题。"""
    name = next((n for n in PPT_THEMES if n in (style or "")), _DEFAULT_STYLE)
    return {key: RGBColor.from_string(value) for key, value in PPT_THEMES[name].items()}


async def generate_ppt_structure(intent: dict, knowledge: str) -> list[dict]:
    llm = get_llm()
    prompt = _PPT_PROMPT.replace("__INTENT__", json.dumps(intent, ensure_ascii=False)).replace(
        "__KNOWLEDGE__", knowledge[:6000]
    )
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    return data.get("slides", [])


def _as_text(point) -> str:
    """容错：LLM 偶发输出嵌套 list，统一转为字符串。"""
    if isinstance(point, str):
        return point
    if isinstance(point, list):
        return "；".join(str(x) for x in point)
    return str(point)


def render_ppt(slides: list[dict], output_path: str | None = None, style: str = "") -> str:
    """渲染 .pptx，返回文件路径。

    16:9 宽屏，封面、学习路径、内容卡片、总结采用统一主题。
    过长文本分页保留，未知角色按内容页处理。
    """
    if output_path is None:
        output_path = unique_output_path("courseware_ppt", ".pptx")
    prs = pptx.Presentation()
    theme = theme_for_style(style)
    render_editorial(prs, slides, theme)
    prs.save(output_path)
    return output_path
