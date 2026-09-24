"""对话接口：多轮追问澄清 + 编排备课流程。"""

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    internal_error,
    json_response_examples,
    named,
)
from app.core.clarify import build_question, missing_fields
from app.core.intent import analyze_intent
from app.core.orchestrator import orchestrate

router = APIRouter()


class Message(BaseModel):
    """一轮对话：role 为 user / assistant，content 为教师或助手的原话。"""

    role: str
    content: str


class ChatRequest(BaseModel):
    """备课对话请求：整段对话历史 + 追问粒度 + 本次备课的参考资料。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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


class ChatResponse(BaseModel):
    content: str
    artifacts: dict | None = None
    clarifying: bool = False


_SKIP_WORDS = ["开始生成", "就这样", "生成吧", "够了", "可以了", "直接生成"]


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
        "最后一轮命中「开始生成」一类的跳过表达时不再追问，直接出生成物。"
        "`reference_doc_ids` 为发起备课勾选的参考资料，命中后在 `artifacts.references` 溯源。\n\n"
        "对话历史由调用方整段带上（本轮无状态）；会话持久化与状态机收编见票 05。"
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
                            "ppt": {"slides": [], "path": "data/output/ppt-1a2b3c.pptx", "filename": "ppt-1a2b3c.pptx"},
                            "word": {"path": "data/output/word-4d5e6f.docx", "filename": "word-4d5e6f.docx"},
                            "outline": {"path": "data/output/outline-7g8h9i.docx"},
                            "references": ["一次函数讲义.pdf"],
                            "knowledge_hits": 3,
                        },
                        "clarifying": False,
                    },
                ),
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def chat(req: ChatRequest):
    history = req.messages
    message = history[-1].content if history else ""
    user_text = " ".join(m.content for m in history if m.role == "user")

    # 1. 意图分析（基于累积需求）
    intent = await analyze_intent(user_text)

    # 2. 追问判断
    if not intent.topic:
        return ChatResponse(
            content="请问你要讲什么课？可以告诉我主题、学段和大致时长。",
            clarifying=True,
        )

    missing = missing_fields(intent, req.granularity)
    skip = any(k in message for k in _SKIP_WORDS)
    if missing and not skip:
        q = build_question(missing)
        return ChatResponse(
            content=f"还差一点信息：{q}（也可以回复「开始生成」跳过追问）",
            clarifying=True,
        )

    # 3. 生成（携带参考资料标识：检索加权 + 溯源）
    result = await orchestrate(user_text, reference_doc_ids=req.reference_doc_ids)
    topic = result["intent"].get("topic", "")
    n_slides = len(result["ppt"]["slides"])
    kb_note = "已融合本地知识库" if result["knowledge_hits"] else "知识库为空，已由 AI 直接生成"
    content = f"已完成备课「{topic}」：生成 PPT {n_slides} 页、Word 教案、教学提纲。（{kb_note}）"
    references = result.get("references") or []
    if references:
        content += f" 本次命中的来源文档：{'、'.join(references)}。"
    if result.get("interactive"):
        content += " 已按你的互动诉求自动生成互动内容（HTML），可在生成物区打开。"
    result["ppt"]["filename"] = Path(result["ppt"]["path"]).name
    result["word"]["filename"] = Path(result["word"]["path"]).name
    return ChatResponse(content=content, artifacts=result)
