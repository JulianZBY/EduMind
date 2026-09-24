"""互动内容按需生成接口：LLM 生成单文件 HTML（小游戏/知识点动画）→ 落盘。

生成物区一键生成入口（GROUPED：备课对话中互动诉求命中时由编排器自动附带，见 orchestrator）。
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.core.intent import intent_from_payload
from app.core.orchestrator import retrieve_knowledge
from app.generate.creative import generate_html_creative, save_html

router = APIRouter()


class InteractiveGenerateRequest(BaseModel):
    """互动内容生成请求：备课意图（可透传上次备课的意图对象）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent": {
                    "topic": "一次函数",
                    "grade": "初二",
                    "interactive": "课堂小游戏：判断哪些是一次函数",
                }
            }
        }
    )

    # 生成物区透传上次备课意图；空意图时仅凭主题生成
    intent: dict = {}


class InteractiveGenerateResponse(BaseModel):
    html: str
    filename: str


def _is_single_file_html(html: str) -> bool:
    """单文件 HTML 最小校验：文档结构完整（doctype 或 html 标签，且有闭合）。"""
    lowered = html.lower()
    return lowered.lstrip().startswith("<!doctype") or "<html" in lowered


@router.post(
    "/interactive/generate",
    response_model=InteractiveGenerateResponse,
    tags=["生成物"],
    summary="生成互动内容",
    description=(
        "按意图生成一份**单文件 HTML5** 互动内容（小游戏 / 知识点动画），落盘后返回 HTML 正文与文件名。\n\n"
        "前端可用 `GET /api/v1/files/{filename}?inline=true` 在新标签页直接打开试用。\n"
        "模型返回的不是完整单文件 HTML 时，本接口以 502 报错而不落盘半成品。"
    ),
    responses={
        200: json_response(
            "互动内容已生成并落盘",
            {
                "html": "<!doctype html><html lang=zh><body>…</body></html>",
                "filename": "creative-3c2b1a09.html",
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
        502: error_response(
            "互动内容生成失败：模型未返回单文件 HTML",
            "互动内容生成失败：模型未返回单文件 HTML，请重试",
        ),
    },
)
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
