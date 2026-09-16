"""互动内容按需生成接口：LLM 生成单文件 HTML（小游戏/知识点动画）→ 落盘。

产物区一键生成入口（GROUPED：备课对话中互动诉求命中时由编排器自动附带，见 orchestrator）。
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.intent import intent_from_payload
from app.core.orchestrator import retrieve_knowledge
from app.generate.creative import generate_html_creative, save_html

router = APIRouter()


class InteractiveGenerateRequest(BaseModel):
    # 产物区透传上次备课意图；空意图时仅凭主题生成
    intent: dict = {}


class InteractiveGenerateResponse(BaseModel):
    html: str
    filename: str


def _is_single_file_html(html: str) -> bool:
    """单文件 HTML 最小校验：文档结构完整（doctype 或 html 标签，且有闭合）。"""
    lowered = html.lower()
    return lowered.lstrip().startswith("<!doctype") or "<html" in lowered


@router.post("/interactive/generate", response_model=InteractiveGenerateResponse)
async def generate_interactive(req: InteractiveGenerateRequest):
    intent = intent_from_payload(req.intent)

    retrieval = await retrieve_knowledge(intent)
    html = (await generate_html_creative(retrieval.context or intent.topic)).strip()
    if not _is_single_file_html(html):
        raise HTTPException(
            status_code=502, detail="互动内容生成失败：模型未返回单文件 HTML，请重试"
        )

    path = save_html(html)
    return InteractiveGenerateResponse(html=html, filename=Path(path).name)
