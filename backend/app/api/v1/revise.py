"""课件/教案迭代接口：修改意见 → 调整再生成。"""

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.openapi_examples import VALIDATION_ERROR, internal_error, json_response
from app.generate.ppt import render_ppt
from app.generate.revise import revise_ppt, revise_word
from app.generate.word import render_word

router = APIRouter()


class ReviseRequest(BaseModel):
    """课件修改请求：待改的课件结构 + 修改意见 + 原风格偏好。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "slides": [
                    {
                        "title": "一次函数",
                        "bullets": ["形如 y=kx+b（k≠0）", "图象是一条直线"],
                    }
                ],
                "feedback": "把第二页的例子换成生活情境，语言再简洁些",
                "style": "情境导入",
            }
        }
    )

    slides: list[dict]
    feedback: str
    # 课件主题化：修改后重渲染沿用原风格偏好映射配色主题；不传则回退默认主题
    style: str = ""


class ReviseResponse(BaseModel):
    slides: list[dict]
    filename: str


class ReviseWordRequest(BaseModel):
    """教案修改请求：待改的教案结构 + 修改意见 + 参考资料（再渲染时保留溯源一节）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "word": {
                    "objectives": {"knowledge": ["理解一次函数的定义"]},
                    "process": [{"stage": "情境导入", "minutes": 5, "content": "…"}],
                },
                "feedback": "教学目标再具体一点，写出可观察的行为动词",
                "references": ["一次函数讲义.pdf"],
            }
        }
    )

    word: dict
    feedback: str
    # 溯源：修改后再渲染仍保留「参考资料」一节；不传则不追加
    references: list[str] = []


class ReviseWordResponse(BaseModel):
    word: dict
    filename: str


@router.post(
    "/revise",
    response_model=ReviseResponse,
    tags=["生成物"],
    summary="按修改意见重做课件",
    description=(
        "对**所选课件**提修改意见并重新生成：把待改的课件结构连同意见交模型重排，"
        "再渲染为**新文件**（旧文件保留，因此可反复修改互不覆盖）。\n\n"
        "本接口只作用于传入的这一份课件，不影响同次备课的教案与提纲；"
        "`style` 用于沿用原课件风格（配色主题），不传则回退默认主题。"
    ),
    responses={
        200: json_response(
            "修改后的课件与新文件名",
            {
                "slides": [
                    {
                        "title": "一次函数",
                        "bullets": ["形如 y=kx+b（k≠0）", "出租车计价就是一次函数"],
                    }
                ],
                "filename": "ppt-6a5b4c3d.pptx",
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def revise(req: ReviseRequest):
    new_slides = await revise_ppt(req.slides, req.feedback)
    path = render_ppt(new_slides, style=req.style)  # 默认统一随机命名，连续修改互不覆盖
    return ReviseResponse(slides=new_slides, filename=Path(path).name)


@router.post(
    "/revise/word",
    response_model=ReviseWordResponse,
    tags=["生成物"],
    summary="按修改意见重做教案",
    description=(
        "与课件修改同模式：完整教案结构交模型重排后**重新渲染为新 Word 文件**，旧文件保留。\n\n"
        "传 `references` 时再渲染的教案保留「参考资料」一节，保证修改后溯源不断。"
    ),
    responses={
        200: json_response(
            "修改后的教案与新文件名",
            {
                "word": {
                    "objectives": {"knowledge": ["能说出一次函数的定义并判断给定函数"]},
                    "process": [{"stage": "情境导入", "minutes": 5, "content": "…"}],
                },
                "filename": "word-9i8h7g6f.docx",
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def revise_word_endpoint(req: ReviseWordRequest):
    """教案修改：与课件同模式——完整结构交 LLM 重排后重新渲染为新文件。"""
    new_word = await revise_word(req.word, req.feedback)
    path = render_word(new_word, references=req.references or None)
    return ReviseWordResponse(word=new_word, filename=Path(path).name)
