"""文档上传接口：保存文件 + 创建 Document 记录 + 触发后台解析。"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db import get_session
from app.db.models import Document
from app.knowledge.pipeline import parse_document
from app.knowledge.storage import save_upload

router = APIRouter()

DEFAULT_USER_ID = "default"


@router.post("/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_session)],
    is_reference: Annotated[bool, Form()] = False,
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


@router.get("/documents")
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
