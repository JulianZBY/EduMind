"""Upload + instruction -> new PPTX, never overwrite the source."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.generate import unique_output_path
from app.generate.ppt_edit import MAX_BYTES, apply_edits, plan_edits, read_presentation

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/presentations/edit")
async def edit_presentation(
    file: Annotated[UploadFile, File()],
    feedback: Annotated[str, Form(min_length=1, max_length=2000)],
):
    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(415, "目前支持 .pptx，请先将旧版 .ppt 另存为 .pptx")
    if not feedback.strip():
        raise HTTPException(422, "请填写修改要求")
    raw = await file.read(MAX_BYTES + 1)
    await file.close()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "PPTX 不能超过 20 MB")
    try:
        prs = await asyncio.to_thread(read_presentation, raw)
    except Exception as exc:
        raise HTTPException(
            422, str(exc) if isinstance(exc, ValueError) else "无法读取有效的 PPTX"
        ) from exc
    if settings.llm_provider == "stub":
        raise HTTPException(503, "请先在后端配置真实的大模型服务，演示模式不支持按要求修改 PPT")
    try:
        plan = await asyncio.wait_for(plan_edits(prs, feedback.strip()), timeout=120)
        changes = apply_edits(prs, plan)
        if not changes:
            raise HTTPException(
                422,
                "未产生文本修改。请明确页码和文字调整要求；图片、图表、增删页与布局修改暂不支持",
            )
        path = unique_output_path("edited_presentation", ".pptx")
        await asyncio.to_thread(prs.save, path)
        return {"filename": Path(path).name, "slides": len(prs.slides), "changes": changes}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, "编辑结果无法应用，请缩小修改范围并重试") from exc
    except Exception as exc:
        logger.exception("Presentation editing failed")
        raise HTTPException(502, "大模型服务暂时不可用，请稍后重试；原文件未修改") from exc
