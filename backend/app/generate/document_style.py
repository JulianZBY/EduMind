"""Shared print typography for generated teaching documents."""

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


def style_document(doc):
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2.2)
    for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "List Bullet"):
        style = doc.styles[name]
        style.font.name = "Microsoft YaHei"
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "微软雅黑")
        style.font.color.rgb = RGBColor.from_string("263D34")
        # Suppress template-specific borders, including Word's blue title rule.
        borders = OxmlElement("w:pBdr")
        for edge in ("top", "left", "bottom", "right", "between"):
            border = OxmlElement(f"w:{edge}")
            border.set(qn("w:val"), "nil")
            borders.append(border)
        style.element.get_or_add_pPr().append(borders)
    subtitle = doc.styles["Subtitle"]
    subtitle.font.size = Pt(11)
    subtitle.font.italic = False
    subtitle.font.color.rgb = RGBColor.from_string("728577")
    normal = doc.styles["Normal"]
    normal.font.size = Pt(10.5)
    normal.paragraph_format.line_spacing = 1.4
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.widow_control = True
    for name, size in (("Title", 27), ("Heading 1", 15), ("Heading 2", 11)):
        style = doc.styles[name]
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string("286757")
        style.paragraph_format.space_before = Pt(16)
        style.paragraph_format.space_after = Pt(8)
        style.paragraph_format.keep_with_next = True
