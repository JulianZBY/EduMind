"""试卷按需生成接口：LLM 自编出题 → 题目入库（自编+关联知识点）→ 落盘。"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.core.intent import TeachingIntent
from app.core.orchestrator import retrieve_knowledge
from app.generate.exam import generate_exam, render_exam, save_questions_to_bank

router = APIRouter()


class ExamGenerateRequest(BaseModel):
    # 产物区透传上次备课意图；空意图时仅凭主题生成
    intent: dict = {}
    n: int = 5


class ExamGenerateResponse(BaseModel):
    questions: list[dict]
    filename: str
    bank_saved: int


def _intent_from_topic(intent: dict) -> TeachingIntent:
    topic = intent.get("topic")
    return TeachingIntent(topic=topic if isinstance(topic, str) else "")


@router.post("/exam/generate", response_model=ExamGenerateResponse)
async def generate_exam_paper(req: ExamGenerateRequest):
    try:
        intent = TeachingIntent.model_validate(req.intent)
    except ValidationError:
        # 意图结构不完整时退化为仅主题，一键生成不被前端字段变更卡死
        intent = _intent_from_topic(req.intent)

    retrieval = await retrieve_knowledge(intent)
    questions = await generate_exam(intent.model_dump(), retrieval.context, n=req.n)
    if not questions:
        raise HTTPException(status_code=502, detail="试卷生成失败：模型未返回可解析的题目，请重试")

    bank_saved = save_questions_to_bank(questions)
    path = render_exam(questions)
    return ExamGenerateResponse(
        questions=questions, filename=Path(path).name, bank_saved=bank_saved
    )
