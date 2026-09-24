"""互动内容按需生成接口：LLM 生成单文件 HTML（小游戏/知识点动画）→ 落盘。

生成物区一键生成入口（GROUPED：备课对话中互动诉求命中时由编排器自动附带，见 orchestrator）。
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.core import artifacts as artifact_service
from app.core.intent import intent_from_payload
from app.db import get_session
from app.db.artifacts import ArtifactStore
from app.generate.creative import generate_html_creative, save_html
from app.knowledge.retrieval.factory import get_retriever

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
    # 可选：所属备课会话；带上后本份互动内容产出**新版本**并入库（不传则保持既有语义）
    session_id: str | None = None


class InteractiveGenerateResponse(BaseModel):
    html: str
    filename: str
    version_id: str | None = None  # 本次产出的版本 id；不带会话标识时为空
    version: int | None = None  # 互动内容在会话内的版本号：从 1 单调递增
    session_id: str | None = None  # 版本所属备课会话


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
        "模型返回的不是完整单文件 HTML 时，本接口以 502 报错而不落盘半成品。\n\n"
        "**带上 `session_id` 时本份互动内容落一条新版本**（版本号在会话内单调递增，"
        "旧的互动内容版本保持可回看、可下载，也可用版本下载端点直内联打开）；"
        "会话不存在返回 `404`。"
    ),
    responses={
        200: json_response(
            "互动内容已生成并落盘",
            {
                "html": "<!doctype html><html lang=zh><body>…</body></html>",
                "filename": "creative_3c2b1a09.html",
                "version_id": "8f7e6d5c-4b3a-4291-9c8d-7e6f5a4b3c2d",
                "version": 1,
                "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
            },
        ),
        404: error_response(
            "备课会话不存在", "会话不存在: 9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b"
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
        502: error_response(
            "互动内容生成失败：模型未返回单文件 HTML",
            "互动内容生成失败：模型未返回单文件 HTML，请重试",
        ),
    },
)
async def generate_interactive(
    req: InteractiveGenerateRequest, db: Annotated[Session, Depends(get_session)]
):
    """按意图生成单文件 HTML 互动内容；带会话标识时同时落一条版本记录。"""
    store = ArtifactStore(db)
    if req.session_id is not None:
        # 先校验会话：不给不存在的会话留无主版本记录，也不白跑一次生成
        try:
            artifact_service.require_session(store, req.session_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    intent = intent_from_payload(req.intent)

    retrieval = await get_retriever().retrieve(intent)
    html = (await generate_html_creative(retrieval.context or intent.topic)).strip()
    if not _is_single_file_html(html):
        raise HTTPException(
            status_code=502, detail="互动内容生成失败：模型未返回单文件 HTML，请重试"
        )

    path = save_html(html)
    filename = Path(path).name
    if req.session_id is None:
        return InteractiveGenerateResponse(html=html, filename=filename)

    row = artifact_service.record_generation(
        store,
        session_id=req.session_id,
        artifact_type=artifact_service.CREATIVE,
        path=path,
        content={"html": html},
        title=intent.topic,
    )
    return InteractiveGenerateResponse(
        html=html,
        filename=filename,
        version_id=row.id,
        version=row.version,
        session_id=row.session_id,
    )
