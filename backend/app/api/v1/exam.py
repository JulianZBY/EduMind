"""试卷按需生成接口：LLM 自编出题 → 题目入库（自编+关联知识点）→ 落盘；另含题库查询。"""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.core import artifacts as artifact_service
from app.core.intent import TeachingIntent
from app.db import get_session
from app.db.artifacts import ArtifactStore
from app.generate.exam import (
    generate_exam,
    query_question,
    query_questions,
    render_exam,
    save_questions_to_bank,
)
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
    # 可选：所属备课会话；带上后本张试卷产出**新版本**并入库（不传则保持既有语义）
    session_id: str | None = None


class ExamGenerateResponse(BaseModel):
    questions: list[dict]
    filename: str
    bank_saved: int
    version_id: str | None = None  # 本次产出的版本 id；不带会话标识时为空
    version: int | None = None  # 试卷在会话内的版本号：从 1 单调递增
    session_id: str | None = None  # 版本所属备课会话


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
        "`filename` 可用于 `GET /api/v1/files/{filename}` 下载，"
        "也可以按版本下载（见 `download_url` 体系：`GET /api/v1/artifacts/{version_id}/download`）。\n\n"
        "`intent` 可直接透传上次备课的意图对象；结构不完整时退化为仅凭 `topic` 出题，"
        "不会因为字段缺失卡住一键生成。\n\n"
        "**带上 `session_id` 时本张试卷落一条新版本**（版本号在会话内单调递增，"
        "旧的试卷版本保持可回看、可下载）；会话不存在返回 `404`。"
    ),
    responses={
        200: json_response(
            "试卷已生成，题目已入题库",
            {
                "questions": [_EXAM_QUESTION],
                "filename": "exam_8f7e6d5c.docx",
                "bank_saved": 5,
                "version_id": "7e6d5c4b-3a2f-4190-8b7c-6d5e4f3a2b1c",
                "version": 1,
                "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
            },
        ),
        404: error_response("备课会话不存在", "会话不存在: 9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b"),
        422: VALIDATION_ERROR,
        500: internal_error(),
        502: error_response(
            "试卷生成失败：模型未返回可解析的题目",
            "试卷生成失败：模型未返回可解析的题目，请重试",
        ),
    },
)
async def generate_exam_paper(
    req: ExamGenerateRequest, db: Annotated[Session, Depends(get_session)]
):
    """按意图出题并入库落盘；带会话标识时同时落一条试卷版本记录。"""
    store = ArtifactStore(db)
    if req.session_id is not None:
        # 先校验会话：不给不存在的会话留无主版本记录，也不白跑一次生成
        try:
            artifact_service.require_session(store, req.session_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

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
    filename = Path(path).name
    if req.session_id is None:
        return ExamGenerateResponse(questions=questions, filename=filename, bank_saved=bank_saved)

    row = artifact_service.record_generation(
        store,
        session_id=req.session_id,
        artifact_type=artifact_service.EXAM,
        path=path,
        content={"questions": questions},
        title=intent.topic,
    )
    return ExamGenerateResponse(
        questions=questions,
        filename=filename,
        bank_saved=bank_saved,
        version_id=row.id,
        version=row.version,
        session_id=row.session_id,
    )


class QuestionKnowledgeRef(BaseModel):
    """题目的一道考查知识点：标题 + 权重（主考 / 涉及）。"""

    id: str
    title: str
    weight: str


class QuestionSummary(BaseModel):
    """列表行：题干 / 题型 / 来源 / 考查知识点（答案在详情里，列表不带）。"""

    id: str
    type: str
    content: str
    source_type: str
    created_at: datetime
    knowledge_points: list[QuestionKnowledgeRef]


class KnowledgePointCount(BaseModel):
    """题库筛选项：一个考查知识点及它的题目数。"""

    title: str
    question_count: int


class QuestionListResponse(BaseModel):
    items: list[QuestionSummary]
    total: int  # 当前筛选条件下的题目总数（分页前）
    limit: int
    offset: int
    # 全部考查知识点（不随筛选变化）：教师换筛选时清单不会自己消失
    knowledge_points: list[KnowledgePointCount]


class QuestionDetail(BaseModel):
    """题目详情：题型 / 答案 / 来源 / 考查知识点齐备。"""

    id: str
    type: str
    content: str
    answer: str
    source_type: str  # 来源：自编 / 上传 / 网络
    source_url: str | None
    created_at: datetime
    knowledge_points: list[QuestionKnowledgeRef]


_BANK_QUESTION = {
    "id": "3f2b1a09-8c7d-4e6f-9a1b-2c3d4e5f6a7b",
    "type": "选择",
    "content": "下列函数中，属于一次函数的是？",
    "source_type": "自编",
    "created_at": "2026-09-24T10:20:30",
    "knowledge_points": [
        {
            "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
            "title": "一次函数的定义",
            "weight": "主考",
        }
    ],
}

_BANK_QUESTION_DETAIL = {**_BANK_QUESTION, "answer": "A", "source_url": None}


@router.get(
    "/questions",
    response_model=QuestionListResponse,
    tags=["题库"],
    summary="题目列表（按考查知识点筛选）",
    description=(
        "题库查询入口：按**考查知识点**筛选题目，返回分页结果与筛选项。\n\n"
        "* `knowledge_point` 填图谱节点标题（与 `GET /api/v1/knowledge/graph` 的 `title` 一致）；"
        "不传则返回全部题目。题目按入库时间**倒序**：试卷刚入库的题目就出现在第一页。\n"
        "* 每道题的 `knowledge_points` 带权重：`主考` 排在前、`涉及` 排在后。\n"
        "* `items` 只带列表要用的字段（题干 / 题型 / 来源 / 考查知识点）；答案在 "
        "`GET /api/v1/questions/{question_id}`。\n"
        "* `knowledge_points` 是**全量**筛选项（含各自题目数），不随当前筛选收窄——"
        "筛过一次之后仍能换回别的知识点。\n"
        "* `limit` 上限 100（一屏工作台密度容量），`total` 为筛选后的总数，供前端翻页。"
    ),
    responses={
        200: json_response(
            "题目列表（含全部筛选项）",
            {
                "items": [_BANK_QUESTION],
                "total": 12,
                "limit": 20,
                "offset": 0,
                "knowledge_points": [
                    {"title": "一次函数的定义", "question_count": 5},
                    {"title": "一次函数的图象", "question_count": 3},
                ],
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def list_questions(
    knowledge_point: Annotated[
        str | None,
        Query(
            description=(
                "按考查知识点筛选：填图谱节点标题（见 GET /api/v1/knowledge/graph 的 title）；"
                "不传返回全部题目"
            ),
            examples=["一次函数的定义"],
        ),
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="本页最多返回多少道题（1–100，默认 20）")
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="跳过前多少道题，用于翻页")] = 0,
):
    return query_questions(knowledge_point=knowledge_point, limit=limit, offset=offset)


@router.get(
    "/questions/{question_id}",
    response_model=QuestionDetail,
    tags=["题库"],
    summary="题目详情",
    description=(
        "取一道题的完整内容：题干 / 题型 / 答案 / 来源 / 考查知识点（含主考与涉及）。\n\n"
        "`question_id` 取自题目列表返回的 `id`；题目不存在时返回 `404`，"
        "而不是空对象——前端据此区分「题目没了」与「题目是空的」。"
    ),
    responses={
        200: json_response("题目详情", _BANK_QUESTION_DETAIL),
        404: error_response("题目不存在：id 写错或题目已删除", "题目不存在"),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def get_question(question_id: str):
    question = query_question(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    return question
