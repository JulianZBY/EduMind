"""文档上传接口：保存文件 + 创建 Document 记录 + 触发后台解析。"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.openapi_examples import VALIDATION_ERROR, internal_error, json_response
from app.db import get_session
from app.db.models import Document
from app.knowledge.pipeline import parse_document
from app.knowledge.storage import save_upload

router = APIRouter()

DEFAULT_USER_ID = "default"


@router.post(
    "/documents/upload",
    tags=["知识库"],
    summary="上传教学资料",
    description=(
        "上传一份教学资料并**立即返回**：文件落盘 + 建文档记录 + 交后台解析（解析完成前"
        "`status` 为 `处理中`）。\n\n"
        "上传后请轮询 `GET /api/v1/documents` 直到状态从 `处理中` 变为 `已完成`（或 "
        "`有冲突` / `失败`），不要靠等待本请求变慢来判断进度。\n\n"
        "`is_reference=true` 把文档标记为参考资料：发起备课时勾选其 id 会提高检索权重，"
        "并在生成物中溯源。"
    ),
    responses={
        200: json_response(
            "已接收，后台解析中",
            {
                "id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                "filename": "一次函数讲义.pdf",
                "file_type": "pdf",
                "status": "处理中",
                "is_reference": True,
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Annotated[
        UploadFile,
        File(description="教学资料文件：PDF / Word / PPT / 图片 / 视频 / 录音"),
    ],
    db: Annotated[Session, Depends(get_session)],
    is_reference: Annotated[
        bool, Form(description="是否标记为参考资料：影响备课检索加权与生成物溯源")
    ] = False,
):
    content = await file.read()
    filename = file.filename or "upload.bin"
    file_path = save_upload(content, filename)
    ext = Path(filename).suffix.lstrip(".").lower()

    doc = Document(
        user_id=DEFAULT_USER_ID,
        filename=filename,
        file_path=file_path,
        file_type=ext,
        status="处理中",
        is_reference=is_reference,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 后台异步解析（MinerU 等为异步流程）
    background_tasks.add_task(parse_document, doc.id)

    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "status": doc.status,
        "is_reference": doc.is_reference,
    }


@router.get(
    "/documents",
    tags=["知识库"],
    summary="教学资料列表",
    description=(
        "返回全部教学资料及其解析状态，供知识库工作台轮询进度。\n\n"
        "`status` 取值：`处理中` → 后台解析尚未结束；`已完成` → 已入库可检索；"
        "`有冲突` → 已入库但检测到待裁决的定义冲突（见冲突审核区）；`失败` → 解析失败，"
        "可按原文重新上传。`is_reference` 为参考资料标记。"
    ),
    responses={
        200: json_response(
            "资料列表",
            {
                "documents": [
                    {
                        "id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                        "filename": "一次函数讲义.pdf",
                        "file_type": "pdf",
                        "status": "已完成",
                        "is_reference": True,
                    },
                    {
                        "id": "1a2b3c4d-5e6f-4071-8293-a4b5c6d7e8f9",
                        "filename": "课堂录音.mp3",
                        "file_type": "mp3",
                        "status": "处理中",
                        "is_reference": False,
                    },
                ]
            },
        ),
        500: internal_error(),
    },
)
async def list_documents(db: Annotated[Session, Depends(get_session)]):
    docs = db.query(Document).all()
    return {
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "status": d.status,
                "is_reference": d.is_reference,
            }
            for d in docs
        ]
    }
