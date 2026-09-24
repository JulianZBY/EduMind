"""试卷按需生成接口：LLM 自编出题 → 题目入库（自编+关联知识点）→ 落盘。"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.core.intent import TeachingIntent
from app.generate.exam import generate_exam, render_exam, save_questions_to_bank
from app.knowledge.retrieval.factory import get_retriever

router = APIRouter()


class ExamGenerateRequest(BaseModel):
    """一键生成试卷的请求：备课意图 + 题目数量。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent": {"topic": "一次函数", "grade": "初二", "duration": "40 分钟"},
                "n": 5,
            }
        }
    )

    # 生成物区透传上次备课意图；空意图时仅凭主题生成
    intent: dict = {}
    n: int = 5


class ExamGenerateResponse(BaseModel):
    questions: list[dict]
    filename: str
    bank_saved: int


_EXAM_QUESTION = {
    "type": "选择",
    "content": "下列函数中，属于一次函数的是？",
    "options": ["A. y=2x+1", "B. y=x²", "C. y=1/x", "D. y=√x"],
    "answer": "A",
    "analysis": "一次函数形如 y=kx+b（k≠0）。",
    "knowledge_point": "一次函数的定义",
}


def _intent_from_topic(intent: dict) -> TeachingIntent:
    topic = intent.get("topic")
    return TeachingIntent(topic=topic if isinstance(topic, str) else "")


@router.post(
    "/exam/generate",
    response_model=ExamGenerateResponse,
    tags=["生成物"],
    summary="一键生成试卷",
    description=(
        "按备课意图出题并同侧入库：生成 `n` 道题（默认 5）→ 题目写入题库（来源=`自编`）"
        "→ 按考查知识点关联知识图谱节点 → 渲染 Word 试卷。\n\n"
        "返回的 `questions` 供生成物区直接预览，`bank_saved` 为实际入题库的题目数，"
        "`filename` 可用于 `GET /api/v1/files/{filename}` 下载。\n\n"
        "`intent` 可直接透传上次备课的意图对象；结构不完整时退化为仅凭 `topic` 出题，"
        "不会因为字段缺失卡住一键生成。"
    ),
    responses={
        200: json_response(
            "试卷已生成，题目已入题库",
            {
                "questions": [_EXAM_QUESTION],
                "filename": "exam-8f7e6d5c.docx",
                "bank_saved": 5,
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
        502: error_response(
            "试卷生成失败：模型未返回可解析的题目",
            "试卷生成失败：模型未返回可解析的题目，请重试",
        ),
    },
)
async def generate_exam_paper(req: ExamGenerateRequest):
    try:
        intent = TeachingIntent.model_validate(req.intent)
    except ValidationError:
        # 意图结构不完整时退化为仅主题，一键生成不被前端字段变更卡死
        intent = _intent_from_topic(req.intent)

    retrieval = await get_retriever().retrieve(intent)
    questions = await generate_exam(intent.model_dump(), retrieval.context, n=req.n)
    if not questions:
        raise HTTPException(status_code=502, detail="试卷生成失败：模型未返回可解析的题目，请重试")

    bank_saved = save_questions_to_bank(questions)
    path = render_exam(questions)
    return ExamGenerateResponse(
        questions=questions, filename=Path(path).name, bank_saved=bank_saved
    )
