"""试卷生成：LLM 自编出题 + 题库入库 + python-docx 渲染。

按需生成入口（产物区一键生成）；组题模式与网络搜题仅预留（DESIGN.md §5.4）。
题库查询（按考查知识点筛选 / 分页）也住本文件：查询与入库同源，入库的题目立即可查。
"""

import json
from typing import TYPE_CHECKING

from docx import Document as DocxDocument
from sqlalchemy import func, select

from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.llm.parsing import parse_json
from app.generate import unique_output_path

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.db.models import KnowledgeNode

_EXAM_PROMPT = """你是出题专家。根据教学意图和知识内容，生成试卷。

要求：
- 生成 __N__ 道题，题型覆盖选择/填空/简答
- 每题含 type、content、answer、analysis（答案解析）、knowledge_point（本题考查的知识点，取自知识内容中的知识点名称）
- 选择题附 options（选项数组）

只输出 JSON，不要其他文字：
{"questions": [{"type": "选择", "content": "题目", "options": ["A. …", "B. …"], "answer": "答案", "analysis": "解析", "knowledge_point": "知识点"}]}

教学意图：__INTENT__
知识内容：__KNOWLEDGE__
"""


async def generate_exam(intent: dict, knowledge: str, n: int = 5) -> list[dict]:
    llm = get_llm()
    prompt = (
        _EXAM_PROMPT.replace("__N__", str(n))
        .replace("__INTENT__", json.dumps(intent, ensure_ascii=False))
        .replace("__KNOWLEDGE__", knowledge[:6000])
    )
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    return data.get("questions", [])


def save_questions_to_bank(questions: list[dict], user_id: str = "default") -> int:
    """生成题目写入题库：来源=自编，并按考查知识点关联图谱节点（主考/涉及）。"""
    from app.db import SessionLocal
    from app.db.models import KnowledgeNode, Question, QuestionKnowledge

    if not questions:
        return 0
    db = SessionLocal()
    try:
        nodes = (
            db.execute(select(KnowledgeNode).where(KnowledgeNode.user_id == user_id))
            .scalars()
            .all()
        )
        saved = 0
        for q in questions:
            row = Question(
                user_id=user_id,
                content=str(q.get("content", "")).strip(),
                answer=str(q.get("answer", "")).strip(),
                type=str(q.get("type", "")).strip()[:20] or "简答",
                source_type="自编",
            )
            db.add(row)
            db.flush()  # 先取 row.id 再建题目-知识点关联
            for i, node in enumerate(
                _match_nodes(nodes, str(q.get("knowledge_point", "")).strip())
            ):
                db.add(
                    QuestionKnowledge(
                        question_id=row.id,
                        knowledge_id=node.id,
                        weight="主考" if i == 0 else "涉及",
                    )
                )
            saved += 1
        db.commit()
        return saved
    finally:
        db.close()


def _match_nodes(nodes: "Sequence[KnowledgeNode]", knowledge_point: str) -> list["KnowledgeNode"]:
    """考查知识点 → 图谱节点：精确标题优先，其次标题互含（近名容错）。"""
    if not knowledge_point:
        return []
    exact = [n for n in nodes if n.title == knowledge_point]
    if exact:
        return exact
    return [
        n for n in nodes if n.title and (n.title in knowledge_point or knowledge_point in n.title)
    ]


def query_questions(
    knowledge_point: str | None = None,
    limit: int = 20,
    offset: int = 0,
    user_id: str = "default",
) -> dict:
    """题库查询：按考查知识点筛选 + 分页，并回带全部筛选项（列表与详情同一份出参形状）。

    筛选项 `knowledge_points` 是**全量**的：它不随当前筛选收窄，否则教师筛过一次之后
    就再也换不回别的知识点。题目按入库时间倒序，试卷刚入库的题目在第一页。
    """
    from app.db import SessionLocal
    from app.db.models import KnowledgeNode, Question, QuestionKnowledge

    db = SessionLocal()
    try:
        filters = [Question.user_id == user_id]
        if knowledge_point:
            # 按图谱节点标题匹配（教师看到的就是这个标题）；子查询避免一题多链时出重复行
            linked = (
                select(QuestionKnowledge.question_id)
                .join(KnowledgeNode, KnowledgeNode.id == QuestionKnowledge.knowledge_id)
                .where(KnowledgeNode.title == knowledge_point)
            )
            filters.append(Question.id.in_(linked))
        total = db.scalar(select(func.count(Question.id)).where(*filters)) or 0
        rows = (
            db.execute(
                select(Question)
                .where(*filters)
                .order_by(Question.created_at.desc(), Question.id.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return {
            "items": _serialize_questions(db, list(rows)),
            "total": total,
            "limit": limit,
            "offset": offset,
            "knowledge_points": _knowledge_point_facets(db, user_id),
        }
    finally:
        db.close()


def query_question(question_id: str, user_id: str = "default") -> dict | None:
    """按 id 取一道题（含考查知识点）；题目不存在时返回 None，由接口层转 404。"""
    from app.db import SessionLocal
    from app.db.models import Question

    db = SessionLocal()
    try:
        row = db.execute(
            select(Question).where(Question.id == question_id, Question.user_id == user_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return _serialize_questions(db, [row])[0]
    finally:
        db.close()


def _serialize_questions(db, rows: list) -> list[dict]:
    """题目行 → 出参：考查知识点一并取出，权重「主考」排在「涉及」前。

    出参含答案，列表接口由响应模型裁掉（详情才外露答案），避免两处各写一份形状。
    """
    from app.db.models import KnowledgeNode, QuestionKnowledge

    if not rows:
        return []
    links = db.execute(
        select(QuestionKnowledge, KnowledgeNode)
        .join(KnowledgeNode, KnowledgeNode.id == QuestionKnowledge.knowledge_id)
        .where(QuestionKnowledge.question_id.in_([row.id for row in rows]))
    ).all()
    by_question: dict[str, list[dict]] = {}
    for link, node in links:
        by_question.setdefault(link.question_id, []).append(
            {"id": node.id, "title": node.title, "weight": link.weight}
        )
    for points in by_question.values():
        points.sort(key=lambda point: (point["weight"] != "主考", point["title"]))
    return [
        {
            "id": row.id,
            "type": row.type,
            "content": row.content,
            "answer": row.answer,
            "source_type": row.source_type,
            "source_url": row.source_url,
            "created_at": row.created_at,
            "knowledge_points": by_question.get(row.id, []),
        }
        for row in rows
    ]


def _knowledge_point_facets(db, user_id: str) -> list[dict]:
    """考查知识点 → 题目数：题库筛选项的来源，按题目数倒序（同数按标题）。"""
    from app.db.models import KnowledgeNode, Question, QuestionKnowledge

    rows = db.execute(
        select(KnowledgeNode.title, func.count(func.distinct(QuestionKnowledge.question_id)))
        .join(QuestionKnowledge, QuestionKnowledge.knowledge_id == KnowledgeNode.id)
        .join(Question, Question.id == QuestionKnowledge.question_id)
        .where(Question.user_id == user_id)
        .group_by(KnowledgeNode.title)
        .order_by(
            func.count(func.distinct(QuestionKnowledge.question_id)).desc(), KnowledgeNode.title
        )
    ).all()
    return [{"title": title, "question_count": count} for title, count in rows]


def render_exam(questions: list[dict], output_path: str | None = None) -> str:
    """渲染 .docx：试题 + 答案解析两部分，试题行标注考查知识点。"""
    if output_path is None:
        output_path = unique_output_path("exam", ".docx")
    doc = DocxDocument()
    doc.add_heading("试卷", level=0)
    doc.add_heading("试题", level=1)
    for i, q in enumerate(questions, 1):
        knowledge_point = str(q.get("knowledge_point") or "").strip()
        tag = f"（考查知识点：{knowledge_point}）" if knowledge_point else ""
        doc.add_paragraph(f"{i}. [{q.get('type', '')}]{tag} {q.get('content', '')}")
        for option in q.get("options") or []:
            doc.add_paragraph(f"　　{option}")
    doc.add_heading("答案解析", level=1)
    for i, q in enumerate(questions, 1):
        line = f"{i}. {q.get('answer', '')}"
        analysis = str(q.get("analysis") or "").strip()
        if analysis:
            line += f"　解析：{analysis}"
        doc.add_paragraph(line)
    doc.save(output_path)
    return output_path
