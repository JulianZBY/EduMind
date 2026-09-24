"""课件/教案迭代接口：修改意见 → 调整再生成。"""

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.generate.ppt import render_ppt
from app.generate.ppt_layout import pages
from app.generate.revise import revise_ppt, revise_word
from app.generate.word import render_word

router = APIRouter()


class ReviseRequest(BaseModel):
    slides: list[dict]
    feedback: str
    # 课件主题化：修改后重渲染沿用原风格偏好映射配色主题；不传则回退默认主题
    style: str = ""


class ReviseResponse(BaseModel):
    slides: list[dict]
    filename: str


class ReviseWordRequest(BaseModel):
    word: dict
    feedback: str
    # 溯源：修改后再渲染仍保留「参考资料」一节；不传则不追加
    references: list[str] = []


class ReviseWordResponse(BaseModel):
    word: dict
    filename: str


@router.post("/revise", response_model=ReviseResponse)
async def revise(req: ReviseRequest):
    new_slides = list(pages(await revise_ppt(req.slides, req.feedback)))
    path = render_ppt(new_slides, style=req.style)  # 默认统一随机命名，连续修改互不覆盖
    return ReviseResponse(slides=new_slides, filename=Path(path).name)


@router.post("/revise/word", response_model=ReviseWordResponse)
async def revise_word_endpoint(req: ReviseWordRequest):
    """教案修改：与课件同模式——完整结构交 LLM 重排后重新渲染为新文件。"""
    new_word = await revise_word(req.word, req.feedback)
    path = render_word(new_word, references=req.references or None)
    return ReviseWordResponse(word=new_word, filename=Path(path).name)
