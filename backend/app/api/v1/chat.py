"""对话接口：备课会话主入口（澄清 / 生成两种回复形态）。

本层只做参数校验与转发：澄清与追问的判断、意图累积、状态机流转都住 `core/`
（`core/conversation.py` 状态机、`core/session_service.py` 一轮对话的落地）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response_examples,
    named,
)
from app.core import session_service
from app.db import get_session
from app.db.sessions import ConversationStore

router = APIRouter()


class Message(BaseModel):
    """一轮对话：role 为 user / assistant，content 为教师或助手的原话。"""

    role: str
    content: str


class ChatRequest(BaseModel):
    """备课对话请求：对话内容 + 追问粒度 + 本次备课的参考资料 +（可选）备课会话 id。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                "messages": [
                    {"role": "user", "content": "给初二讲一次函数，40 分钟"},
                    {"role": "assistant", "content": "还差一点信息：想用什么教学风格？"},
                    {"role": "user", "content": "情境导入为主，开始生成"},
                ],
                "granularity": "标准",
                "reference_doc_ids": ["5c9d1e3b-6f47-4a1c-9a2e-0d4c5b7a8f01"],
            }
        }
    )

    messages: list[Message]
    granularity: str = "标准"
    # 本次备课的参考资料（文档 id）：检索加权 + 回复/教案溯源；不传则行为与现状一致
    reference_doc_ids: list[str] = []
    # 可选：备课会话 id（取自会话列表）。携带后会话成为事实源；不传保持无状态既有行为
    session_id: str | None = None


class ChatResponse(BaseModel):
    content: str
    artifacts: dict | None = None
    clarifying: bool = False
    # 本轮落库的备课会话 id；无状态请求（未带 session_id）为空
    session_id: str | None = None


def _last_teacher_utterance(messages: list[Message]) -> str:
    """取最后一条教师消息的内容：跳过追问按**本轮原话**做语义判定。"""
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _full_history_text(messages: list[Message]) -> str:
    """无状态请求的意图输入：把整段教师需求拼起来全量分析（收编前的既有行为）。"""
    return " ".join(m.content for m in messages if m.role == "user")


@router.post(
    "/chat",
    response_model=ChatResponse,
    tags=["备课会话"],
    summary="备课对话",
    description=(
        "备课对话主入口，后端按**累积需求**分析意图后二选一：\n\n"
        "1. **澄清回复**：`clarifying=true`、`artifacts=null`，内容是下一个追问；"
        "追问粒度分快速 / 标准 / 精细三档，粒度越高追问越细。\n"
        "2. **生成回复**：`clarifying=false`，`artifacts` 携带本次的课件、教案、提纲，"
        "以及命中的参考资料来源。\n\n"
        "教师表示「信息已经够用」时（按语义判断，不靠关键词匹配）不再追问，直接出生成物。\n\n"
        "**两种调用方式**：\n\n"
        "* 带 `session_id`（取自会话列表）：以服务端会话为事实源——本轮需求与回复入库，"
        "意图按会话增量累积（不重析全部历史）。此时 `messages` 里**最后一条教师消息**是本轮新增需求，"
        "其余内容以服务端历史为准；追问粒度与参考资料也以会话上的设置为准（改它们用 "
        "`PATCH /api/v1/sessions/{session_id}`），请求里的 `granularity` / `reference_doc_ids` 不生效。"
        "会话不存在时返回 `404`。\n"
        "* 不带 `session_id`：保持无状态既有行为——整段对话历史由调用方带上，"
        "后端每轮全量重析意图，不落库、不回显 `session_id`。"
    ),
    responses={
        200: json_response_examples(
            "澄清回复或生成回复，由 `clarifying` 区分",
            {
                "澄清回复": named(
                    "信息不足，继续追问",
                    {
                        "content": "还差一点信息：这节课的重点难点是什么？（也可以回复「开始生成」跳过追问）",
                        "artifacts": None,
                        "clarifying": True,
                        "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                    },
                ),
                "生成回复": named(
                    "信息够用，直出生成物",
                    {
                        "content": (
                            "已完成备课「一次函数」：生成 PPT 12 页、Word 教案、教学提纲。"
                            "（已融合本地知识库） 本次命中的来源文档：一次函数讲义.pdf。"
                        ),
                        "artifacts": {
                            "intent": {"topic": "一次函数", "grade": "初二"},
                            "ppt": {
                                "slides": [],
                                "path": "data/output/ppt-1a2b3c.pptx",
                                "filename": "ppt-1a2b3c.pptx",
                            },
                            "word": {
                                "path": "data/output/word-4d5e6f.docx",
                                "filename": "word-4d5e6f.docx",
                            },
                            "outline": {
                                "text": "# 一次函数\n## 定义与图像\n- 正比例函数",
                                "path": "data/output/outline-7g8h9i.docx",
                                "filename": "outline-7g8h9i.docx",
                            },
                            "references": ["一次函数讲义.pdf"],
                            "knowledge_hits": 3,
                        },
                        "clarifying": False,
                        "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                    },
                ),
            },
        ),
        404: error_response("备课会话不存在", "会话不存在: 9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b"),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def chat(req: ChatRequest, db: Annotated[Session, Depends(get_session)]):
    """备课对话：澄清或生成二选一；带会话 id 时消息与累积意图落库。"""
    if req.session_id is None:
        outcome = await session_service.run_stateless_turn(
            _full_history_text(req.messages),
            utterance=_last_teacher_utterance(req.messages),
            granularity=req.granularity,
            reference_doc_ids=req.reference_doc_ids,
        )
        return ChatResponse(
            content=outcome.content, artifacts=outcome.artifacts, clarifying=outcome.clarifying
        )

    latest_utterance = _last_teacher_utterance(req.messages)
    if not latest_utterance.strip():
        raise HTTPException(
            status_code=422,
            detail="messages 里缺少教师消息（role=user）：带 session_id 时本轮新增需求取自最后一条教师消息",
        )
    try:
        outcome = await session_service.handle_turn(
            ConversationStore(db), req.session_id, latest_utterance
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ChatResponse(
        content=outcome.content,
        artifacts=outcome.artifacts,
        clarifying=outcome.clarifying,
        session_id=req.session_id,
    )
