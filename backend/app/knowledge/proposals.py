"""新学科提议的待批队列与教师批准。

AI 归类认为清单内学科都不合适时产出提议（学科名 + AI 理由 + 涉及的知识点）。
待批提议不进学科清单、不可被归类选用、也不进冲突审核——与冲突「待审」同哲学：
审核前不生效。批准是教师显式动作：批准才入清单并触发相关「未分类」知识点重新归类；
拒绝后提议消亡、知识点留在「未分类」。

清单与归类复用 subjects.py，建边复用 graph.py 的入库建边入口，
不另造第二套。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeNode, Subject, SubjectProposal
from app.knowledge.subjects import UNCLASSIFIED, SubjectError, list_subjects, validate_subject_name

# 提议终态（CONTEXT.md 词条「提议」「批准」「拒绝」）。
PROPOSAL_PENDING = "待批"
PROPOSAL_APPROVED = "已批准"
PROPOSAL_REJECTED = "已拒绝"


class ProposalError(ValueError):
    """提议业务错误；薄路由只映射状态码。"""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def list_pending_proposals(db: Session) -> list[SubjectProposal]:
    """待批队列：只列出还没被教师处理过的提议（按提出时间稳定排序）。"""
    return list(
        db.scalars(
            select(SubjectProposal)
            .where(SubjectProposal.status == PROPOSAL_PENDING)
            .order_by(SubjectProposal.created_at, SubjectProposal.id)
        )
    )


def record_proposal(
    db: Session, *, name: str, reason: str, knowledge_titles: list[str]
) -> SubjectProposal | None:
    """落一条待批提议；去重口径：同名已在清单内或已有待批提议时跳过（返回 None）。

    入库管道调用（尽力而为，失败或应跳过都不阻断解析主流程）。
    """
    try:
        name = validate_subject_name(name)
    except SubjectError:
        return None
    if name == UNCLASSIFIED:
        return None
    if name in {s.name for s in list_subjects(db)}:
        return None
    exists = db.scalar(
        select(SubjectProposal.id).where(
            SubjectProposal.name == name, SubjectProposal.status == PROPOSAL_PENDING
        )
    )
    if exists is not None:
        return None
    titles = sorted({t.strip() for t in (knowledge_titles or []) if t and t.strip()})
    proposal = SubjectProposal(
        user_id="default",
        name=name,
        reason=(reason or "").strip(),
        knowledge_titles=titles,
        status=PROPOSAL_PENDING,
    )
    db.add(proposal)
    db.flush()
    return proposal


def _get_pending(db: Session, proposal_id: str) -> SubjectProposal:
    proposal = db.get(SubjectProposal, proposal_id)
    if proposal is None:
        raise ProposalError(404, "提议不存在。")
    if proposal.status != PROPOSAL_PENDING:
        raise ProposalError(409, "这条提议已经处理过，不能重复处理。")
    return proposal


def approve_proposal(db: Session, proposal_id: str) -> tuple[SubjectProposal, str, int]:
    """批准：提议入清单 + 相关「未分类」知识点重新归类，在同一事务内。

    返回 (提议, 学科 id, 重新归类数)。只把仍为「未分类」的相关知识点改为新学科
    ——教师已归入其他学科或手动归类的节点不动；同学科补「相关关联」复用入库建边入口
    ，不重复调用云端向量化。学科名已在清单内（例如教师先手动加过）时
    跳过新增、复用那一项，仍执行重新归类。
    """
    from app.knowledge.graph import supplement_related

    proposal = _get_pending(db, proposal_id)
    try:
        name = validate_subject_name(proposal.name)
    except SubjectError as exc:
        raise ProposalError(exc.status_code, str(exc)) from exc
    if name == UNCLASSIFIED:
        raise ProposalError(400, "提议的学科不能是「未分类」。")
    subject = db.scalar(select(Subject).where(Subject.name == name))
    if subject is None:
        subject = Subject(name=name)
        db.add(subject)
        db.flush()
    titles = [t for t in (proposal.knowledge_titles or []) if t]
    nodes = (
        db.scalars(
            select(KnowledgeNode).where(
                KnowledgeNode.user_id == proposal.user_id,
                KnowledgeNode.subject == UNCLASSIFIED,
                KnowledgeNode.title.in_(titles),
            )
        ).all()
        if titles
        else []
    )
    for node in nodes:
        node.subject = name
        supplement_related(db, node, None, None)
    proposal.status = PROPOSAL_APPROVED
    db.commit()
    db.refresh(proposal)
    return proposal, subject.id, len(nodes)


def reject_proposal(db: Session, proposal_id: str) -> SubjectProposal:
    """拒绝：提议消亡，知识点留在「未分类」，清单不动。"""
    proposal = _get_pending(db, proposal_id)
    proposal.status = PROPOSAL_REJECTED
    db.commit()
    db.refresh(proposal)
    return proposal
