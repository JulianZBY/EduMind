"""对话接口：多轮追问澄清 + 编排备课流程。"""

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.clarify import build_question, missing_fields
from app.core.intent import analyze_intent
from app.core.orchestrator import orchestrate

router = APIRouter()


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    granularity: str = "标准"
    # 本次备课的参考资料（文档 id）：检索加权 + 回复/教案溯源；不传则行为与现状一致
    reference_doc_ids: list[str] = []


class ChatResponse(BaseModel):
    content: str
    artifacts: dict | None = None
    clarifying: bool = False


_SKIP_WORDS = ["开始生成", "就这样", "生成吧", "够了", "可以了", "直接生成"]


@router.post("/chat", response_model=ChatResponse)
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
        content += " 已按你的互动诉求自动生成互动内容（HTML），可在产物预览区打开。"
    result["ppt"]["filename"] = Path(result["ppt"]["path"]).name
    result["word"]["filename"] = Path(result["word"]["path"]).name
    return ChatResponse(content=content, artifacts=result)
