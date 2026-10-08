"""教学资料删除级联（票 07）：删除对话框交代的每一条后果都在这里发生，无隐藏级联。

规则（教师逐条确认过的口径，照录为验收依据）：
- **必删**：该资料的分块与向量、文献笔记、引用该资料的待审冲突（撤下）；
- **知识点**：仅来源于该资料的默认删（可勾选改为保留，保留者清空该来源引用）；
  多来源知识点摘除该来源、节点保留；关系边随节点走；
- **被题目考查的知识点**：删除前列出受影响题目；确认后题目保留、考查关系置空；
- 生成物历史版本的溯源文本不改写（史实留痕，版本表只读）。

删除不调用任何云端能力：文献笔记缺失 / 未生成、对话模型未配置都不影响删除。
本模块执行数据删除与来源治理；面向教师的后果描述住在 `app/api/v1/documents.py` 的
OpenAPI 注解与前端删除对话框里（词汇用 CONTEXT.md：教学资料 / 文献笔记 / 知识点 / 冲突）。
"""

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Conflict,
    Document,
    KnowledgeEdge,
    KnowledgeNode,
    LiteratureNote,
    Question,
    QuestionKnowledge,
)
from app.knowledge.storage import normalize_stored_path

# 冲突状态：只有「待审」会被撤下（新知尚未入图谱）；已裁决的冲突是史实留痕
CONFLICT_PENDING = "待审"
PROCESSING_DELETE_MESSAGE = "教学资料正在处理中，暂不可删除。请等待处理结束后再试。"


class DocumentProcessingError(ValueError):
    """处理中不能删除，避免后台解析在删除后继续写入孤儿数据。"""


@dataclass
class KnowledgePointRef:
    """级联涉及的一个知识点（id + 标题，足够对话框与结果摘要指认）。"""

    id: str
    title: str


@dataclass
class AffectedQuestion:
    """考查了将被删除的知识点的题目：删除后题目保留、考查关系置空。"""

    id: str
    content: str
    knowledge_titles: list[str] = field(default_factory=list)


@dataclass
class DeletePreview:
    """删除前预览：对话框照此陈列，不另加也不隐瞒。"""

    document_id: str
    filename: str
    chunk_count: int  # 必删：该资料入库的分块与向量
    literature_note_present: bool  # 必删：文献笔记（缺席时如实报 False）
    pending_conflict_count: int  # 必删：引用该资料的待审冲突（撤下）
    knowledge_single_source: list[KnowledgePointRef]  # 默认删；可勾选保留
    knowledge_multi_source: list[KnowledgePointRef]  # 摘除该来源、节点保留
    affected_questions: list[AffectedQuestion]  # 被考（仅统计将随默认删除的知识点）


@dataclass
class DeleteResult:
    """删除结果：每条规则的执行事实，供界面回执与测试断言。"""

    document_id: str
    filename: str
    chunks_deleted: int
    literature_note_deleted: bool
    conflicts_withdrawn: int
    knowledge_deleted: list[KnowledgePointRef]
    knowledge_kept: list[KnowledgePointRef]  # 保留者已清空 / 摘除该来源引用
    questions_cleared: list[AffectedQuestion]
    file_removed: bool


def source_nodes(db: Session, doc_id: str) -> list[KnowledgeNode]:
    """来源引用含这份资料的全部知识点（单来源与多来源的并集）。"""
    rows = (
        db.execute(select(KnowledgeNode).where(KnowledgeNode.source_docs.isnot(None)))
        .scalars()
        .all()
    )
    return [node for node in rows if doc_id in (node.source_docs or [])]


def _single_source(nodes: list[KnowledgeNode], doc_id: str) -> list[KnowledgeNode]:
    """仅来源于该资料的知识点（默认删的一批）。"""
    return [n for n in nodes if set(n.source_docs or []) == {doc_id}]


def _affected_questions(db: Session, nodes: list[KnowledgeNode]) -> list[AffectedQuestion]:
    """被给定知识点考查的题目（去重；一道题考多个被删知识点只列一行）。"""
    if not nodes:
        return []
    ids = [n.id for n in nodes]
    title_by_id = {n.id: n.title for n in nodes}
    rows = db.execute(
        select(Question, QuestionKnowledge.knowledge_id)
        .join(QuestionKnowledge, QuestionKnowledge.question_id == Question.id)
        .where(QuestionKnowledge.knowledge_id.in_(ids))
    ).all()
    merged: dict[str, AffectedQuestion] = {}
    for question, knowledge_id in rows:
        entry = merged.setdefault(
            question.id,
            AffectedQuestion(id=question.id, content=question.content, knowledge_titles=[]),
        )
        title = title_by_id.get(knowledge_id)
        if title and title not in entry.knowledge_titles:
            entry.knowledge_titles.append(title)
    return list(merged.values())


def _pending_conflicts(db: Session, doc_id: str, nodes: list[KnowledgeNode]) -> list[Conflict]:
    """引用本资料的待审冲突：新知来源、旧知识点来源或快照明确的资料引用。

    与知识点是否保留无关；预览和执行共用，已裁决记录不参与。
    """
    node_ids = {node.id for node in nodes}

    def references_doc(snapshot: dict | None) -> bool:
        data = snapshot or {}
        return data.get("doc_id") == doc_id or doc_id in (data.get("source_docs") or [])

    pending = db.scalars(select(Conflict).where(Conflict.status == CONFLICT_PENDING)).all()
    return [
        conflict
        for conflict in pending
        if conflict.doc_id == doc_id
        or (conflict.existing_knowledge or {}).get("id") in node_ids
        or references_doc(conflict.existing_knowledge)
        or references_doc(conflict.new_knowledge)
    ]


def preview_delete(db: Session, doc: Document, chunk_count: int) -> DeletePreview:
    """删除前预览：按默认勾选（删单来源知识点）口径列出全部后果。"""
    nodes = source_nodes(db, doc.id)
    singles = _single_source(nodes, doc.id)
    multis = [n for n in nodes if n not in singles]
    pending = len(_pending_conflicts(db, doc.id, nodes))
    note = (
        db.execute(select(LiteratureNote).where(LiteratureNote.doc_id == doc.id))
        .scalars()
        .one_or_none()
    )
    return DeletePreview(
        document_id=doc.id,
        filename=doc.filename,
        chunk_count=chunk_count,
        literature_note_present=note is not None,
        pending_conflict_count=pending,
        knowledge_single_source=[
            KnowledgePointRef(id=n.id, title=n.title) for n in sorted(singles, key=lambda n: n.title)
        ],
        knowledge_multi_source=[
            KnowledgePointRef(id=n.id, title=n.title) for n in sorted(multis, key=lambda n: n.title)
        ],
        affected_questions=_affected_questions(db, singles),
    )


def delete_document(
    db: Session,
    doc: Document,
    *,
    delete_single_source_knowledge: bool = True,
) -> DeleteResult:
    """删除教学资料并按规则级联，返回每条规则的执行事实。

    `delete_single_source_knowledge=False`：仅来源于该资料的知识点保留，
    来源引用清空（`source_docs` 摘除本资料）；关系与题目考查关系原样保留。
    """
    from app.knowledge.vector_store import VectorStore  # 局部导入：测试按模块替换密封实例

    if doc.status == "处理中":
        raise DocumentProcessingError(PROCESSING_DELETE_MESSAGE)

    store = VectorStore()

    nodes = source_nodes(db, doc.id)
    pending_conflicts = _pending_conflicts(db, doc.id, nodes)
    singles = _single_source(nodes, doc.id)
    multis = [n for n in nodes if n not in singles]
    deleted_points: list[KnowledgePointRef] = []
    kept_points = [KnowledgePointRef(id=n.id, title=n.title) for n in multis]

    questions_cleared: list[AffectedQuestion] = []
    if delete_single_source_knowledge:
        deleted_points = [KnowledgePointRef(id=n.id, title=n.title) for n in singles]
        # 被题目考查的知识点：题目保留，考查关系置空
        questions_cleared = _affected_questions(db, singles)
        if singles:
            ids = [n.id for n in singles]
            db.execute(
                delete(QuestionKnowledge).where(QuestionKnowledge.knowledge_id.in_(ids)),
                execution_options={"synchronize_session": False},
            )
            # 关系边随节点走：连着被删节点的边一并消失
            db.execute(
                delete(KnowledgeEdge).where(
                    KnowledgeEdge.from_node.in_(ids) | KnowledgeEdge.to_node.in_(ids)
                ),
                execution_options={"synchronize_session": False},
            )
            for node in singles:
                store.remove_node_title(node.id)
                db.delete(node)

    # 多来源知识点（以及勾选保留的单来源）：摘除该来源引用、节点保留
    for node in multis:
        node.source_docs = [d for d in (node.source_docs or []) if d != doc.id]
    if not delete_single_source_knowledge:
        for node in singles:
            node.source_docs = [d for d in (node.source_docs or []) if d != doc.id]
        kept_points = [KnowledgePointRef(id=n.id, title=n.title) for n in singles] + kept_points

    # 必删：文献笔记（1:1，缺席不算失败）
    note = (
        db.execute(select(LiteratureNote).where(LiteratureNote.doc_id == doc.id))
        .scalars()
        .one_or_none()
    )
    if note is not None:
        db.delete(note)

    # 必删：引用该资料的待审冲突（撤下）；已裁决的冲突是史实留痕，不动
    conflicts_withdrawn = len(pending_conflicts)
    for conflict in pending_conflicts:
        db.delete(conflict)

    # 必删：分块与向量（独立向量库，主库提交前先清）；回执记实际清掉的分块数
    chunks_deleted = store.delete_doc(doc.id)

    # 资料本体与落盘文件；生成物版本表不触碰（溯源文本不改写）
    file_removed = _remove_upload_file(doc.file_path)
    result = DeleteResult(
        document_id=doc.id,
        filename=doc.filename,
        chunks_deleted=chunks_deleted,
        literature_note_deleted=note is not None,
        conflicts_withdrawn=conflicts_withdrawn,
        knowledge_deleted=deleted_points,
        knowledge_kept=kept_points,
        questions_cleared=questions_cleared,
        file_removed=file_removed,
    )
    db.delete(doc)
    db.commit()
    return result


def _remove_upload_file(file_path: str) -> bool:
    """删掉资料落盘文件；文件已不在（迁移 / 手工清理）时如实报 False。"""
    path = Path(normalize_stored_path(file_path))
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
