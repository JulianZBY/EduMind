"""课件/教案迭代接口：修改意见 → 调整再生成（产出新版本，不覆盖旧版）。"""

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
from app.db import get_session
from app.db.artifacts import ArtifactStore
from app.db.models import ArtifactVersion
from app.generate.ppt import render_ppt
from app.generate.revise import revise_ppt, revise_word
from app.generate.word import render_word

router = APIRouter()


class ReviseRequest(BaseModel):
    """课件修改请求：待改的课件结构 + 修改意见 + 原风格偏好 +（可选）以哪一版为基线。"""

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
                "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                "base_version_id": "3f2a1b0c-9d8e-4f70-8a1b-2c3d4e5f6a7b",
            }
        }
    )

    slides: list[dict]
    feedback: str
    # 课件主题化：修改后重渲染沿用原风格偏好映射配色主题；不传则回退默认主题
    style: str = ""
    # 可选：所属备课会话；带上后本次修改产出**新版本**并入库（不传则保持既有语义，只回文件名）
    session_id: str | None = None
    # 可选：以哪一版为基线（版本 id 取自版本列表）；不传时用该会话该生成物的当前版本
    base_version_id: str | None = None


class ReviseResponse(BaseModel):
    slides: list[dict]
    filename: str
    version_id: str | None = None  # 本次产出的版本 id；不带会话标识时为空
    version: int | None = None  # 本次产出的版本号：比基线更高，基线版本保持可取回
    session_id: str | None = None  # 版本所属备课会话；不带会话标识时为空


class ReviseWordRequest(BaseModel):
    """教案修改请求：待改的教案结构 + 修改意见 + 参考资料 +（可选）以哪一版为基线。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "word": {
                    "objectives": {"knowledge": ["理解一次函数的定义"]},
                    "process": [{"stage": "情境导入", "minutes": 5, "content": "…"}],
                },
                "feedback": "教学目标再具体一点，写出可观察的行为动词",
                "references": ["一次函数讲义.pdf"],
                "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                "base_version_id": "6d5c4b3a-2e1f-4a90-8b7c-6d5e4f3a2b1c",
            }
        }
    )

    word: dict
    feedback: str
    # 溯源：修改后再渲染仍保留「参考资料」一节；不传则不追加
    references: list[str] = []
    # 可选：所属备课会话；带上后本次修改产出**新版本**并入库
    session_id: str | None = None
    # 可选：以哪一版为基线；不传时用该会话该生成物的当前版本
    base_version_id: str | None = None


class ReviseWordResponse(BaseModel):
    word: dict
    filename: str
    version_id: str | None = None  # 本次产出的版本 id；不带会话标识时为空
    version: int | None = None  # 本次产出的版本号
    session_id: str | None = None  # 版本所属备课会话


def _resolve_baseline(
    db: Session, artifact_type: str, session_id: str | None, base_version_id: str | None
) -> ArtifactVersion:
    """解析这次修改的基线版本（CONTEXT.md「基线」）：404 = 基线或会话不存在，422 = 类别不符。"""
    try:
        return artifact_service.resolve_baseline(
            ArtifactStore(db),
            artifact_type=artifact_type,
            session_id=session_id,
            base_version_id=base_version_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post(
    "/revise",
    response_model=ReviseResponse,
    tags=["生成物"],
    summary="按修改意见重做课件",
    description=(
        "对**所选课件**提修改意见并重新生成：把待改的课件结构连同意见交模型重排，"
        "再渲染为**新文件**（旧文件保留，因此可反复修改互不覆盖）。\n\n"
        "本接口只作用于传入的这一份课件，不影响同次备课的教案与提纲；"
        "`style` 用于沿用原课件风格（配色主题），不传则回退默认主题。\n\n"
        "**带上 `session_id` 时本次修改落一条新版本**（`origin=修改`）：版本号比基线更高，"
        "基线版本保持可回看、可下载；`base_version_id` 指定以哪一版为基线（版本 id 取自版本列表），"
        "不传时以该会话的当前版本为基线。基线或会话不存在返回 `404`，"
        "`base_version_id` 不是课件版本返回 `422`。\n\n"
        "不带 `session_id` / `base_version_id` 时保持既有语义：只返回修改后的结构与新文件名，不落版本记录。"
    ),
    responses={
        200: json_response(
            "修改后的课件、新文件名与（带会话时的）新版本标识",
            {
                "slides": [
                    {
                        "title": "一次函数",
                        "bullets": ["形如 y=kx+b（k≠0）", "出租车计价就是一次函数"],
                    }
                ],
                "filename": "courseware_ppt_6a5b4c3d.pptx",
                "version_id": "4a3b2c1d-0e9f-4a81-9b2c-3d4e5f6a7b8c",
                "version": 2,
                "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
            },
        ),
        404: error_response(
            "基线版本或备课会话不存在",
            "生成物版本不存在: 3f2a1b0c-9d8e-4f70-8a1b-2c3d4e5f6a7b",
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def revise(req: ReviseRequest, db: Annotated[Session, Depends(get_session)]):
    """课件修改：重排结构 → 重新渲染为新文件；带会话标识时产出新版本并入库。"""
    baseline: ArtifactVersion | None = None
    if req.session_id is not None or req.base_version_id is not None:
        baseline = _resolve_baseline(
            db, artifact_service.PPT, req.session_id, req.base_version_id
        )

    new_slides = await revise_ppt(req.slides, req.feedback)
    path = render_ppt(new_slides, style=req.style)  # 默认统一随机命名，连续修改互不覆盖
    filename = Path(path).name
    if baseline is None:
        return ReviseResponse(slides=new_slides, filename=filename)

    row = artifact_service.record_revision(
        ArtifactStore(db), baseline=baseline, path=path, content={"slides": new_slides}
    )
    return ReviseResponse(
        slides=new_slides,
        filename=filename,
        version_id=row.id,
        version=row.version,
        session_id=row.session_id,
    )


@router.post(
    "/revise/word",
    response_model=ReviseWordResponse,
    tags=["生成物"],
    summary="按修改意见重做教案",
    description=(
        "与课件修改同模式：完整教案结构交模型重排后**重新渲染为新 Word 文件**，旧文件保留。\n\n"
        "传 `references` 时再渲染的教案保留「参考资料」一节，保证修改后溯源不断。\n\n"
        "**带上 `session_id` 时本次修改落一条新版本**（`origin=修改`）：版本号比基线更高，"
        "基线版本保持可回看、可下载；`base_version_id` 指定以哪一版为基线，"
        "不传时以该会话的当前版本为基线。基线或会话不存在返回 `404`，"
        "`base_version_id` 不是教案版本返回 `422`。\n\n"
        "不带 `session_id` / `base_version_id` 时保持既有语义：只返回修改后的结构与新文件名，不落版本记录。"
    ),
    responses={
        200: json_response(
            "修改后的教案、新文件名与（带会话时的）新版本标识",
            {
                "word": {
                    "objectives": {"knowledge": ["能说出一次函数的定义并判断给定函数"]},
                    "process": [{"stage": "情境导入", "minutes": 5, "content": "…"}],
                },
                "filename": "lesson_plan_9i8h7g6f.docx",
                "version_id": "6d5c4b3a-2e1f-4a90-8b7c-6d5e4f3a2b1c",
                "version": 2,
                "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
            },
        ),
        404: error_response(
            "基线版本或备课会话不存在",
            "生成物版本不存在: 6d5c4b3a-2e1f-4a90-8b7c-6d5e4f3a2b1c",
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def revise_word_endpoint(
    req: ReviseWordRequest, db: Annotated[Session, Depends(get_session)]
):
    """教案修改：与课件同模式——完整结构交 LLM 重排后重新渲染为新文件，带会话时入库为版本。"""
    baseline: ArtifactVersion | None = None
    if req.session_id is not None or req.base_version_id is not None:
        baseline = _resolve_baseline(
            db, artifact_service.WORD, req.session_id, req.base_version_id
        )

    new_word = await revise_word(req.word, req.feedback)
    path = render_word(new_word, references=req.references or None)
    filename = Path(path).name
    if baseline is None:
        return ReviseWordResponse(word=new_word, filename=filename)

    row = artifact_service.record_revision(
        ArtifactStore(db), baseline=baseline, path=path, content={"word": new_word}
    )
    return ReviseWordResponse(
        word=new_word,
        filename=filename,
        version_id=row.id,
        version=row.version,
        session_id=row.session_id,
    )
