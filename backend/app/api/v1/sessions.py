"""备课会话接口（ADR-0002）：创建 / 列表 / 历史 / 重命名 / 删除。

事实源在服务端：会话与消息落库，教师换设备、清浏览器数据后历史不丢。
本层只做参数校验、转发与 OpenAPI 注解；状态机与业务判断住 `core/`。
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.core import session_service
from app.db import get_session
from app.db.models import PrepSession, SessionMessage
from app.db.sessions import ConversationStore

router = APIRouter()

# 追问粒度三档（CONTEXT.md「追问粒度」）
Granularity = Literal["快速", "标准", "精细"]


class SessionCreateRequest(BaseModel):
    """新建备课会话：标题可留空（首轮需求自动充当标题），并带上本次备课的参考资料。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "一次函数（初二）",
                "granularity": "标准",
                "reference_doc_ids": ["5c9d1e3b-6f47-4a1c-9a2e-0d4c5b7a8f01"],
            }
        }
    )

    title: str = ""
    granularity: Granularity = "标准"
    # 本次备课勾选的参考资料（文档 id）：检索加权 + 生成物溯源
    reference_doc_ids: list[str] = []


class SessionUpdateRequest(BaseModel):
    """重命名会话 / 改会话设置：只改传入的字段，未传的字段保持原值。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "一次函数（初二·修订）",
                "granularity": "精细",
                "reference_doc_ids": ["5c9d1e3b-6f47-4a1c-9a2e-0d4c5b7a8f01"],
            }
        }
    )

    title: str | None = None
    granularity: Granularity | None = None
    reference_doc_ids: list[str] | None = None

    @field_validator("title")
    @classmethod
    def _title_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title 不能为空或全空白；要清掉标题请改为「新的备课会话」")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def _require_at_least_one_field(self):
        if self.title is None and self.granularity is None and self.reference_doc_ids is None:
            raise ValueError("至少提供一个要修改的字段：title / granularity / reference_doc_ids")
        return self


class SessionSummary(BaseModel):
    id: str
    title: str  # 会话标题：默认「新的备课会话」，首轮需求自动充当标题
    granularity: str  # 追问粒度：快速 / 标准 / 精细
    reference_doc_ids: list[str]  # 本次备课勾选的参考资料
    message_count: int  # 消息条数（教师说的 + 助手说的）
    created_at: datetime
    updated_at: datetime  # 最近使用时间：会话列表按它倒序


class MessageItem(BaseModel):
    id: str
    seq: int  # 会话内消息序号：从 1 单调递增，历史按此排序
    role: str  # user = 教师说的 / assistant = 助手说的
    content: str  # 消息原话
    kind: str | None = None  # 回复形态：澄清回复 / 生成回复；教师消息为空
    artifacts: dict | None = None  # 生成回复携带的生成物与命中来源
    created_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class SessionHistoryResponse(BaseModel):
    session: SessionSummary
    messages: list[MessageItem]


class SessionDeleteResponse(BaseModel):
    id: str
    deleted: bool


def _summary(store: ConversationStore, prep: PrepSession) -> SessionSummary:
    return SessionSummary(
        id=prep.id,
        title=prep.title,
        granularity=prep.granularity,
        reference_doc_ids=list(prep.reference_doc_ids or []),
        message_count=store.message_count(prep.id),
        created_at=prep.created_at,
        updated_at=prep.updated_at,
    )


def _message(item: SessionMessage) -> MessageItem:
    return MessageItem(
        id=item.id,
        seq=item.seq,
        role=item.role,
        content=item.content,
        kind=item.kind,
        artifacts=item.artifacts,
        created_at=item.created_at,
    )


@router.post(
    "/sessions",
    response_model=SessionSummary,
    tags=["备课会话"],
    summary="新建备课会话",
    description=(
        "新建一个备课会话并立即落库：标题、追问粒度与参考资料都由服务端保存，"
        "供教师换设备、清浏览器数据后继续备课（后端是唯一事实源）。\n\n"
        "* `title` 留空时先用「新的备课会话」占位，首轮教师需求自动充当标题；\n"
        "* `granularity` 是追问粒度三档：快速 / 标准 / 精细；\n"
        "* `reference_doc_ids` 是本次备课勾选的参考资料（文档 id），影响检索加权与生成物溯源。\n\n"
        "随后的备课对话走 `POST /api/v1/chat` 并携带本接口返回的 `id`。"
    ),
    responses={
        200: json_response(
            "新建成功，返回落库后的会话",
            {
                "id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                "title": "一次函数（初二）",
                "granularity": "标准",
                "reference_doc_ids": ["5c9d1e3b-6f47-4a1c-9a2e-0d4c5b7a8f01"],
                "message_count": 0,
                "created_at": "2026-09-24T10:00:00",
                "updated_at": "2026-09-24T10:00:00",
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def create_session(req: SessionCreateRequest, db: Annotated[Session, Depends(get_session)]):
    """新建备课会话（标题可留空，追回粒度默认标准，参考资料可选）。"""
    prep = session_service.create_session(
        ConversationStore(db),
        title=req.title,
        granularity=req.granularity,
        reference_doc_ids=req.reference_doc_ids,
    )
    return _summary(ConversationStore(db), prep)


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    tags=["备课会话"],
    summary="备课会话列表",
    description=(
        "返回全部备课会话，最近使用（改名或对话过）的排在最前，供会话列表按时间回看。\n\n"
        "`q` 非空时按会话标题过滤：用于长期积累的备课记录里检索标题。"
        "`message_count` 是会话内的消息条数（教师说的 + 助手说的）。"
    ),
    responses={
        200: json_response(
            "会话列表（最近使用在前）",
            {
                "sessions": [
                    {
                        "id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                        "title": "一次函数（初二）",
                        "granularity": "标准",
                        "reference_doc_ids": [],
                        "message_count": 4,
                        "created_at": "2026-09-24T10:00:00",
                        "updated_at": "2026-09-24T10:20:00",
                    }
                ]
            },
        ),
        500: internal_error(),
    },
)
async def list_sessions(
    db: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(description="按标题过滤会话；不传返回全部会话")] = None,
):
    """备课会话列表（最近使用在前，可按标题检索）。"""
    store = ConversationStore(db)
    return SessionListResponse(
        sessions=[_summary(store, prep) for prep in session_service.list_sessions(store, keyword=q)]
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionHistoryResponse,
    tags=["备课会话"],
    summary="备课会话历史",
    description=(
        "返回一个备课会话及其**完整消息历史**（按会话内序号升序），"
        "换设备或清浏览器数据后据此完整回看这次备课。\n\n"
        "`messages[].role`：`user` = 教师说的，`assistant` = 助手说的；"
        "`messages[].kind` 区分助手消息的回复形态——`澄清回复`（内容是追问，"
        "`artifacts` 为空）或 `生成回复`（`artifacts` 携带课件、教案、提纲与命中来源）。"
    ),
    responses={
        200: json_response(
            "会话与按序号排好的消息历史",
            {
                "session": {
                    "id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                    "title": "一次函数（初二）",
                    "granularity": "标准",
                    "reference_doc_ids": [],
                    "message_count": 2,
                    "created_at": "2026-09-24T10:00:00",
                    "updated_at": "2026-09-24T10:00:30",
                },
                "messages": [
                    {
                        "id": "1a2b3c4d-5e6f-4071-8293-a4b5c6d7e8f9",
                        "seq": 1,
                        "role": "user",
                        "content": "给初二讲一次函数，40 分钟",
                        "kind": None,
                        "artifacts": None,
                        "created_at": "2026-09-24T10:00:00",
                    },
                    {
                        "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                        "seq": 2,
                        "role": "assistant",
                        "content": "还差一点信息：希望课件是什么风格？（也可以回复「开始生成」跳过追问）",
                        "kind": "澄清回复",
                        "artifacts": None,
                        "created_at": "2026-09-24T10:00:30",
                    },
                ],
            },
        ),
        404: error_response("会话不存在", "会话不存在: 9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b"),
        500: internal_error(),
    },
)
async def session_history(
    db: Annotated[Session, Depends(get_session)],
    session_id: Annotated[str, Path(description="备课会话 id，取自会话列表")],
):
    """备课会话历史（会话 + 完整消息历史，两种回复形态都在里面）。"""
    store = ConversationStore(db)
    try:
        prep, messages = session_service.get_history(store, session_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SessionHistoryResponse(
        session=_summary(store, prep), messages=[_message(m) for m in messages]
    )


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionSummary,
    tags=["备课会话"],
    summary="重命名备课会话",
    description=(
        "修改备课会话：`title` 重命名，`granularity` 切追问粒度（快速 / 标准 / 精细），"
        "`reference_doc_ids` 换本次备课的参考资料。只改传入的字段，未传的字段保持原值。\n\n"
        "会话内对话时的追问粒度与参考资料以会话上的设置为准，因此改完立即影响后续对话。"
    ),
    responses={
        200: json_response(
            "修改成功，返回更新后的会话",
            {
                "id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                "title": "一次函数（初二·修订）",
                "granularity": "精细",
                "reference_doc_ids": ["5c9d1e3b-6f47-4a1c-9a2e-0d4c5b7a8f01"],
                "message_count": 2,
                "created_at": "2026-09-24T10:00:00",
                "updated_at": "2026-09-24T10:05:00",
            },
        ),
        404: error_response("会话不存在", "会话不存在: 9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b"),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def rename_session(
    req: SessionUpdateRequest,
    db: Annotated[Session, Depends(get_session)],
    session_id: Annotated[str, Path(description="备课会话 id，取自会话列表")],
):
    """重命名备课会话 / 改会话设置（追问粒度、参考资料）。"""
    store = ConversationStore(db)
    try:
        prep = session_service.update_session(
            store,
            session_id,
            title=req.title,
            granularity=req.granularity,
            reference_doc_ids=req.reference_doc_ids,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _summary(store, prep)


@router.delete(
    "/sessions/{session_id}",
    response_model=SessionDeleteResponse,
    tags=["备课会话"],
    summary="删除备课会话",
    description=(
        "删除一个备课会话，连同它的全部消息（不留孤儿消息）。删除后历史接口返回 `404`，"
        "会话列表里也不再出现该会话。"
    ),
    responses={
        200: json_response(
            "删除成功", {"id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b", "deleted": True}
        ),
        404: error_response("会话不存在", "会话不存在: 9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b"),
        500: internal_error(),
    },
)
async def delete_session(
    db: Annotated[Session, Depends(get_session)],
    session_id: Annotated[str, Path(description="备课会话 id，取自会话列表")],
):
    """删除备课会话（连同其全部消息）。"""
    try:
        deleted_id = session_service.delete_session(ConversationStore(db), session_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SessionDeleteResponse(id=deleted_id, deleted=True)
