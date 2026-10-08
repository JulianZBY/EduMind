"""教学资料接口（知识库区，CONTEXT.md 第 4 节）：上传 / 列表 / 详情 / 参考资料标记。

解析状态口径：**处理中** → **已完成** / **有冲突** / **失败**。
上传立即返回（状态 `处理中`），解析交后台任务；前端按 `refetchInterval` 轮询本文件的
列表与详情端点跟到终态，不需要教师手动刷新（`docs/architecture.md`「一份资料从上传到入库」）。
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi import (
    Path as PathParam,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    PROVIDER_NOT_CONFIGURED,
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.config import settings
from app.db import get_session
from app.db.models import Document, LiteratureNote
from app.knowledge.literature_note import (
    SOURCE_DOCUMENT,
    STATUS_GENERATED,
    STATUS_PENDING,
    STATUS_UNCONFIGURED,
)
from app.knowledge.pipeline import parse_document
from app.knowledge.storage import save_upload
from app.knowledge.vector_store import VectorStore

router = APIRouter()

DEFAULT_USER_ID = "default"

# 解析状态四值（CONTEXT.md 第 4 节状态口径）：写成 Literal 让生成的 TS 类型是联合类型，
# 前端判断「是否已到终态」不必靠字符串猜。
ParseStatus = Literal["处理中", "已完成", "有冲突", "失败"]

# 详情页一次最多列出多少个分块：大资料可能上千块，避免整篇回传。
CHUNK_PREVIEW_LIMIT = 200


class DocumentView(BaseModel):
    """一份教学资料：上传响应与列表项共用的形状。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                "filename": "一次函数讲义.pdf",
                "file_type": "pdf",
                "status": "处理中",
                "is_reference": True,
            }
        }
    )

    id: str
    filename: str
    file_type: str  # 扩展名，决定走哪个解析器（pdf / docx / pptx / png / mp4 / mp3 …）
    status: ParseStatus
    is_reference: bool
    # 解析失败的原因（面向教师的一句话）；状态不是「失败」时为空
    failure_reason: str = ""


class DocumentListResponse(BaseModel):
    documents: list[DocumentView]


class DocumentChunk(BaseModel):
    """一个分块：`chunk_id` 全局唯一，`chunk_index` 是它在原文中的次序。"""

    chunk_id: int
    chunk_index: int
    content: str


class KnowledgeIndexEntry(BaseModel):
    """文献笔记的知识点索引条目：`id` 是知识图谱节点，可直接定位到该知识点。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"id": "2c1d0e9f-8a7b-4c6d-9e2f-1a3b5c7d9e1f", "title": "TCP三次握手"}
        }
    )

    id: str
    title: str


class LiteratureNoteView(BaseModel):
    """文献笔记（CONTEXT.md「文献笔记」，ADR-0007）：资料的摘要卡 = 资料概要 + 知识点索引。

    `status` 口径：`已生成` = 概要与索引可用；`未配置` = 对话模型未配置、笔记没有生成
    （分块与解析照常入库），界面据此给「去设置页」引导；`未生成` = 解析未到终态
    （处理中 / 失败）或概要生成没有成功——不返回假摘要。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "已生成",
                "source": "教学资料",
                "summary": "本资料系统讲解一次函数的定义、图像与 k、b 的几何意义，适合初中代数备课。",
                "knowledge_index": [
                    {"id": "2c1d0e9f-8a7b-4c6d-9e2f-1a3b5c7d9e1f", "title": "一次函数"}
                ],
            }
        }
    )

    status: Literal["已生成", "未配置", "未生成"]
    source: Literal["教学资料", "网页"]
    summary: str  # 资料概要；未配置 / 未生成时为空字符串（不返回假摘要）
    knowledge_index: list[KnowledgeIndexEntry]  # 可点进知识图谱的知识点索引


class DocumentDetail(DocumentView):
    parsed_at: datetime | None  # 解析完成时间；处理中为空
    conflict_count: int  # 待审冲突数，对应状态「有冲突」
    chunk_count: int  # 该资料入库的分块总数
    chunks: list[DocumentChunk]  # 详情页展示的头 CHUNK_PREVIEW_LIMIT 个分块
    literature_note: LiteratureNoteView  # 文献笔记（ADR-0007）：资料的管理入口


class ReferenceRequest(BaseModel):
    """参考资料标记的目标值（幂等设置，不是翻转）。"""

    model_config = ConfigDict(json_schema_extra={"example": {"is_reference": True}})

    is_reference: bool


def _view(doc: Document) -> DocumentView:
    return DocumentView(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        status=cast(ParseStatus, doc.status),
        is_reference=doc.is_reference,
        failure_reason=doc.failure_reason or "",
    )


def _document_or_404(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"资料不存在: {document_id}")
    return doc


def _literature_note_view(db: Session, doc: Document) -> LiteratureNoteView:
    """资料的文献笔记视图：行缺席（处理中 / 失败 / 存量老资料）时如实报「未生成」。"""
    note = (
        db.execute(select(LiteratureNote).where(LiteratureNote.doc_id == doc.id))
        .scalars()
        .one_or_none()
    )
    if note is None:
        return LiteratureNoteView(
            status=STATUS_PENDING, source=SOURCE_DOCUMENT, summary="", knowledge_index=[]
        )
    return LiteratureNoteView(
        status=cast(
            Literal["已生成", "未配置", "未生成"],
            note.status if note.status in (STATUS_GENERATED, STATUS_UNCONFIGURED) else STATUS_PENDING,
        ),
        source=cast(Literal["教学资料", "网页"], note.source),
        summary=note.summary or "",
        knowledge_index=[KnowledgeIndexEntry(**entry) for entry in (note.knowledge_index or [])],
    )


@router.post(
    "/documents/upload",
    response_model=DocumentView,
    tags=["知识库"],
    summary="上传教学资料",
    description=(
        "上传一份教学资料并**立即返回**：文件落盘 + 建文档记录 + 交后台解析（解析完成前"
        "`status` 为 `处理中`）。\n\n"
        "上传后请轮询 `GET /api/v1/documents` 直到状态从 `处理中` 变为 `已完成`（或 "
        "`有冲突` / `失败`），不要靠等待本请求变慢来判断进度。\n\n"
        "`is_reference=true` 把文档标记为参考资料：发起备课时勾选其 id 会提高检索权重，"
        "并在生成物中溯源。后续可用 `PATCH /api/v1/documents/{document_id}/reference` "
        "随时切换该标记。\n\n"
        "**入口即拒绝的两种情况**：扩展名不在可解析清单内返回 `415`（清单见错误说明）；"
        "空文件返回 `400`。这两种情况不落盘、不建记录——收下再让后台解析失败，"
        "教师只会看到一个没有原因的「失败」。\n\n"
        "解析失败时资料的 `failure_reason` 给出面向教师的一句原因（文件损坏 / 能力未配置 / 被中断）。"
    ),
    responses={
        200: json_response(
            "已接收并交后台解析（`status` 为 `处理中`）",
            {
                "id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                "filename": "一次函数讲义.pdf",
                "file_type": "pdf",
                "status": "处理中",
                "is_reference": True,
            },
        ),
        400: error_response("空文件：没有可解析的内容", "文件是空的，请确认后重新选择"),
        413: error_response("文件过大：超过单次上传上限（默认 200 MB）", "文件过大"),
        415: error_response(
            "不支持的资料格式：扩展名不在可解析清单内",
            "不支持的资料格式「exe」。可上传：pdf、doc、docx、ppt、pptx、png、jpg …",
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
        503: PROVIDER_NOT_CONFIGURED,
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
    # 上传大小上限：超出即 413，避免整份超大文件先吃内存再被拒（M4）。
    # `file.size` 由 multipart 解析填入；读后再断一次，兜底 size 缺失的情形。
    limit_mb = settings.max_upload_bytes // (1024 * 1024)
    if file.size is not None and file.size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"文件过大：超过 {limit_mb} MB 上限")
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"文件过大：超过 {limit_mb} MB 上限")
    filename = file.filename or "upload.bin"
    ext = Path(filename).suffix.lstrip(".").lower()
    from app.knowledge.parsers import get_parser, supported_file_types  # 延迟导入避免循环

    # 入口校验（先于落盘）：不支持的格式与空文件当场拒绝，不留一条没有原因的「失败」
    if ext not in supported_file_types():
        shown = ext or "无扩展名"
        raise HTTPException(
            status_code=415,
            detail=f"不支持的资料格式「{shown}」。可上传：{'、'.join(supported_file_types())}",
        )
    if not content:
        raise HTTPException(status_code=400, detail="文件是空的，请确认后重新选择")
    # 同步落盘：放线程池，不阻塞事件循环（M1）
    file_path = await asyncio.to_thread(save_upload, content, filename)

    # 录音资料唯一解析路径是百炼 paraformer：未配置时立刻给教师 503 引导，
    # 而不是收下文件再落一个没有原因的「失败」（产品没有假转写兜底）。
    from app.knowledge.parsers.audio import AudioParser

    if isinstance(get_parser(ext), AudioParser):
        from app.core.asr.factory import get_transcriber

        get_transcriber()  # 未配置抛 ProviderNotConfigured → 全局 503 处理器给引导

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

    return _view(doc)


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    tags=["知识库"],
    summary="教学资料列表",
    description=(
        "返回全部教学资料及其解析状态，供知识库工作台轮询进度。\n\n"
        "`status` 取值：`处理中` → 后台解析尚未结束；`已完成` → 已入库可检索；"
        "`有冲突` → 已入库但检测到待裁决的矛盾（见冲突审核区）；`失败` → 解析失败，"
        "可按原文重新上传。`is_reference` 为参考资料标记。\n\n"
        "含 `处理中` 的资料时，客户端应保持轮询直到全部落到终态；"
        "单份资料的完整信息（分块、冲突数、完成时间）见 "
        "`GET /api/v1/documents/{document_id}`。"
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
    return DocumentListResponse(documents=[_view(d) for d in docs])


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    tags=["知识库"],
    summary="教学资料详情",
    description=(
        "一份教学资料的全部信息：解析状态与参考资料标记（与列表同一口径），"
        "外加解析完成时间、待审冲突数、入库的分块明细（可回溯到来源资料），"
        "以及这份资料的**文献笔记**（资料概要 + 知识点索引，ADR-0007）。\n\n"
        "`literature_note.status` 口径：`已生成` = 概要与索引可用；`未配置` = 对话模型"
        "未配置、笔记没有生成（分块与解析照常入库），界面据此给「去设置页」引导，"
        "接口不返回假摘要；`未生成` = 解析未到终态或概要生成没有成功。\n\n"
        "`chunks` 只返回前 200 个分块，`chunk_count` 是该资料的分块总数；"
        "资料仍在 `处理中` 时 `parsed_at` 为空、`chunks` 为空——"
        "列表与详情的状态都会随后台解析自动变化，客户端无需手动刷新。"
    ),
    responses={
        200: json_response(
            "教学资料详情",
            {
                "id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                "filename": "一次函数讲义.pdf",
                "file_type": "pdf",
                "status": "已完成",
                "is_reference": True,
                "parsed_at": "2026-09-24T10:30:00",
                "conflict_count": 0,
                "chunk_count": 12,
                "chunks": [
                    {
                        "chunk_id": 42,
                        "chunk_index": 0,
                        "content": "一次函数：形如 y=kx+b（k≠0）的函数。",
                    }
                ],
                "literature_note": {
                    "status": "已生成",
                    "source": "教学资料",
                    "summary": "本资料系统讲解一次函数的定义、图像与 k、b 的几何意义，适合初中代数备课。",
                    "knowledge_index": [
                        {"id": "2c1d0e9f-8a7b-4c6d-9e2f-1a3b5c7d9e1f", "title": "一次函数"}
                    ],
                },
            },
        ),
        404: error_response(
            "资料不存在：id 不属于任何一份已上传的教学资料",
            "资料不存在: 7f6e5d4c-3b2a-4918-8776-655443322110",
        ),
        500: internal_error(),
    },
)
async def get_document(
    document_id: Annotated[str, PathParam(description="教学资料 id，取自上传响应或资料列表")],
    db: Annotated[Session, Depends(get_session)],
):
    doc = _document_or_404(db, document_id)
    chunk_count, chunks = VectorStore().list_doc_chunks(document_id, limit=CHUNK_PREVIEW_LIMIT)
    return DocumentDetail(
        **_view(doc).model_dump(),
        parsed_at=doc.parsed_at,
        conflict_count=doc.conflict_count or 0,
        chunk_count=chunk_count,
        chunks=[DocumentChunk(**c) for c in chunks],
        literature_note=_literature_note_view(db, doc),
    )


@router.patch(
    "/documents/{document_id}/reference",
    response_model=DocumentView,
    tags=["知识库"],
    summary="切换参考资料标记",
    description=(
        "把教学资料标记为参考资料（或取消标记），用于备课检索加权与生成物溯源。\n\n"
        "请求体给的是**目标值**而不是翻转动作，重复提交同一值结果一致（幂等）；"
        "响应即最新状态，切换无需等待任何后台任务。"
    ),
    responses={
        200: json_response(
            "切换后的资料（标记已生效）",
            {
                "id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                "filename": "一次函数讲义.pdf",
                "file_type": "pdf",
                "status": "已完成",
                "is_reference": True,
            },
        ),
        404: error_response(
            "资料不存在：id 不属于任何一份已上传的教学资料",
            "资料不存在: 7f6e5d4c-3b2a-4918-8776-655443322110",
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def set_reference(
    document_id: Annotated[str, PathParam(description="教学资料 id，取自上传响应或资料列表")],
    req: ReferenceRequest,
    db: Annotated[Session, Depends(get_session)],
):
    doc = _document_or_404(db, document_id)
    doc.is_reference = req.is_reference
    db.commit()
    db.refresh(doc)
    return _view(doc)
