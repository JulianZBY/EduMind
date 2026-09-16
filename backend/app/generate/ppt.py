"""PPT 课件生成：LLM 生成结构（页面角色标注）+ python-pptx 角色化主题渲染。"""

import json
from typing import cast

import pptx
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.presentation import Presentation
from pptx.shapes.autoshape import Shape
from pptx.util import Emu, Inches, Pt

from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.llm.parsing import parse_json
from app.generate import unique_output_path

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


def _styled_run(paragraph, text: str, *, size: Pt | None = None, bold: bool = False, color=None):
    """向段落写入一个带样式的 run（角色版式共用的文本工具）。"""
    run = paragraph.add_run()
    run.text = text
    if size is not None:
        run.font.size = size
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    return run


def _write_points(text_frame, points: list, *, size: Pt, bold: bool, color: RGBColor) -> None:
    """逐条写入要点（首条复用首段落）；字数上限由生成 prompt 约定，渲染层不截断。"""
    for i, point in enumerate(points):
        para = text_frame.paragraphs[0] if i == 0 else text_frame.add_paragraph()
        _styled_run(para, _as_text(point), size=size, bold=bold, color=color)


def _slide_size(prs: Presentation) -> tuple[int, int]:
    """幻灯片宽高（EMU），取自演示文稿模板；Length 为 int 子类，stub 允许 None 故按 0 兜底。"""
    width = prs.slide_width or 0
    height = prs.slide_height or 0
    return width, height


def _render_cover(prs: Presentation, s: dict, theme: dict[str, RGBColor]) -> None:
    """封面：大标题 + 色块（底部横贯色带），要点作副标题。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白版式
    width, height = _slide_size(prs)
    band_h = Inches(1.8)
    band = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(0), Emu(height - band_h), Emu(width), Emu(band_h)
    )
    band.fill.solid()
    band.fill.fore_color.rgb = theme["accent"]
    band.line.fill.background()
    title_box = slide.shapes.add_textbox(
        Inches(0.8), Inches(2.4), Emu(width - Inches(1.6)), Inches(1.5)
    )
    _styled_run(
        title_box.text_frame.paragraphs[0],
        s.get("title", ""),
        size=Pt(44),
        bold=True,
        color=theme["title"],
    )
    sub_box = slide.shapes.add_textbox(
        Inches(0.8), Inches(4.2), Emu(width - Inches(1.6)), Inches(1.4)
    )
    _write_points(
        sub_box.text_frame, s.get("points", []), size=Pt(18), bold=False, color=theme["text"]
    )


def _render_toc(prs: Presentation, s: dict, theme: dict[str, RGBColor]) -> None:
    """目录：标题 + 分栏（要点对半拆入左右两栏）。"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白版式
    heading = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(6), Inches(1))
    _styled_run(
        heading.text_frame.paragraphs[0],
        s.get("title", ""),
        size=Pt(32),
        bold=True,
        color=theme["title"],
    )
    points = s.get("points", [])
    mid = (len(points) + 1) // 2
    width, _ = _slide_size(prs)
    gap = Inches(0.4)
    col_width = Emu((width - Inches(1.6) - gap) // 2)
    for ci, column in enumerate([points[:mid], points[mid:]]):
        if not column:
            continue
        x = Inches(0.8) + ci * (col_width + gap)
        box = slide.shapes.add_textbox(Emu(x), Inches(1.8), col_width, Inches(4.8))
        _write_points(box.text_frame, column, size=Pt(18), bold=False, color=theme["text"])


def _render_summary(prs: Presentation, s: dict, theme: dict[str, RGBColor]) -> None:
    """总结：强调色标题 + 标题下强调色条 + 加粗要点。"""
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # 仅标题版式
    width, _ = _slide_size(prs)
    title = slide.shapes.title
    if title is not None:
        title.text = s.get("title", "")
        for para in title.text_frame.paragraphs:
            for run in para.runs:
                run.font.size = Pt(32)
                run.font.bold = True
                run.font.color.rgb = theme["accent"]
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.6), Emu(width - Inches(1.6)), Inches(0.08)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = theme["accent"]
    bar.line.fill.background()
    body = slide.shapes.add_textbox(Inches(0.8), Inches(2.2), Emu(width - Inches(1.6)), Inches(4.4))
    _write_points(body.text_frame, s.get("points", []), size=Pt(20), bold=True, color=theme["text"])


def _render_default(prs: Presentation, s: dict, theme: dict[str, RGBColor]) -> None:
    """默认版式（内容页与旧结构回退共用）：标题 + 正文占位符。theme 预留不改动版式。"""
    slide = prs.slides.add_slide(prs.slide_layouts[1])  # 标题和内容
    title = slide.shapes.title
    if title is not None:
        title.text = s.get("title", "")
    body = cast(Shape, slide.placeholders[1]).text_frame
    body.clear()
    for i, point in enumerate(s.get("points", [])):
        p = body.paragraphs[0] if i == 0 else body.add_paragraph()
        p.text = _as_text(point)


_ROLE_RENDERERS = {
    ROLE_COVER: _render_cover,
    ROLE_TOC: _render_toc,
    ROLE_CONTENT: _render_default,
    ROLE_SUMMARY: _render_summary,
}


def _normalize_role(role) -> str:
    """角色容错：去空白；容忍「封面页」式带页后缀；缺失/未知原样返回（回退默认版式）。"""
    r = str(role or "").strip()
    return r[:-1] if r.endswith("页") and r[:-1] in _ROLE_RENDERERS else r


def render_ppt(slides: list[dict], output_path: str | None = None, style: str = "") -> str:
    """渲染 .pptx，返回文件路径。

    按页面角色差异化版式（封面大标题+色块、目录分栏、总结强调、内容默认），
    配色主题由教师风格偏好映射（简约=黑白灰、学术=深蓝、活泼=暖橙）。
    缺失/未知角色的旧结构输入回退默认版式，不崩溃。
    """
    if output_path is None:
        output_path = unique_output_path("courseware_ppt", ".pptx")
    prs = pptx.Presentation()
    theme = theme_for_style(style)
    for s in slides:
        render = _ROLE_RENDERERS.get(_normalize_role(s.get("role")), _render_default)
        render(prs, s, theme)
    prs.save(output_path)
    return output_path
