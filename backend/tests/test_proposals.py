"""新学科提议-批准-入清单-重归类全链路、拒绝路径与重复提议去重口径的离线回归契约。"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, or_, select

from app.db import SessionLocal, init_db
from app.db.models import (
    Base,
    KnowledgeEdge,
    KnowledgeNode,
    Subject,
    SubjectProposal,
)
from app.knowledge.graph import extract_knowledge
from app.knowledge.proposals import record_proposal
from app.main import app
from tests.support.fakes import PromptCapturingLLM, ProposalLLM

client = TestClient(app)
init_db()

PROPOSALS_URL = "/api/v1/knowledge/proposals"


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _install_llm(monkeypatch, llm) -> None:
    from app.core.llm import factory

    monkeypatch.setattr(factory, "get_llm", lambda: llm)


def _pending_names() -> set[str]:
    return {p["name"] for p in client.get(PROPOSALS_URL).json()["proposals"]}


def _subject_names() -> set[str]:
    return {s["name"] for s in client.get("/api/v1/knowledge/subjects").json()["subjects"]}


def _cleanup(name: str) -> None:
    """共享测试库的清场：本用例建的节点、边、清单项与提议全部移除。"""
    with SessionLocal() as db:
        nodes = db.scalars(select(KnowledgeNode).where(KnowledgeNode.subject == name)).all()
        ids = [n.id for n in nodes]
        if ids:
            for edge in db.scalars(
                select(KnowledgeEdge).where(
                    or_(KnowledgeEdge.from_node.in_(ids), KnowledgeEdge.to_node.in_(ids))
                )
            ).all():
                db.delete(edge)
            for node in nodes:
                db.delete(node)
        for subject in db.scalars(select(Subject).where(Subject.name == name)).all():
            db.delete(subject)
        for proposal in db.scalars(
            select(SubjectProposal).where(SubjectProposal.name == name)
        ).all():
            db.delete(proposal)
        db.commit()


def _nodes_by_title_prefix(prefix: str) -> list[KnowledgeNode]:
    with SessionLocal() as db:
        return list(
            db.scalars(select(KnowledgeNode).where(KnowledgeNode.title.like(f"{prefix}%"))).all()
        )


@pytest.mark.asyncio
async def test_proposal_approve_full_chain(monkeypatch, tmp_path):
    """入库→待批提议→（不进清单、不进归类提示词）→批准→入清单+重新归类→重复批准 409。"""
    from app.config import settings
    from app.knowledge.pipeline import extract_and_save_knowledge

    monkeypatch.setattr(settings, "vectors_db_path", str(tmp_path / "chain.db"))
    name = _unique("考古学")
    prefix = f"考古{uuid.uuid4().hex[:6]}"
    text = "\n".join(f"{prefix}点{i}" for i in (1, 2, 3))
    _install_llm(
        monkeypatch, ProposalLLM({"subject": name, "reason": "属于考古学，清单内没有合适学科。"})
    )
    try:
        assert await extract_and_save_knowledge("doc-chain", text) == 0
        nodes = _nodes_by_title_prefix(prefix)
        assert len(nodes) == 3
        assert {n.subject for n in nodes} == {"未分类"}

        proposals = client.get(PROPOSALS_URL).json()["proposals"]
        mine = [p for p in proposals if p["name"] == name]
        assert len(mine) == 1
        proposal = mine[0]
        assert proposal["status"] == "待批"
        assert proposal["reason"] == "属于考古学，清单内没有合适学科。"
        assert sorted(proposal["knowledge_titles"]) == sorted(n.title for n in nodes)

        # 待批不进学科清单（审核前不生效），也不进归类提示词（不可被归类选用）
        assert name not in _subject_names()
        capturing = PromptCapturingLLM()
        _install_llm(monkeypatch, capturing)
        await extract_knowledge("再提取一段正文")
        assert f"- {name}" not in capturing.prompts[-1]

        # 批准：入清单 + 相关「未分类」知识点重新归类
        response = client.post(f"{PROPOSALS_URL}/{proposal['id']}/approve")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "已批准"
        assert result["reclassified"] == 3
        subjects = client.get("/api/v1/knowledge/subjects").json()["subjects"]
        assert name in {s["name"] for s in subjects}
        assert next(s for s in subjects if s["name"] == name)["id"] == result["subject_id"]
        nodes = _nodes_by_title_prefix(prefix)
        assert {n.subject for n in nodes} == {name}

        # 队列只剩已处理项吗——待批队列不再含它；重复批准是 409
        assert name not in _pending_names()
        assert client.post(f"{PROPOSALS_URL}/{proposal['id']}/approve").status_code == 409
    finally:
        _cleanup(name)


@pytest.mark.asyncio
async def test_proposal_reject_path(monkeypatch, tmp_path):
    """拒绝：提议消亡、知识点留在「未分类」、清单不动；再拒绝/再批准都是 409。"""
    from app.config import settings
    from app.knowledge.pipeline import extract_and_save_knowledge

    monkeypatch.setattr(settings, "vectors_db_path", str(tmp_path / "reject.db"))
    name = _unique("博物学")
    prefix = f"博物{uuid.uuid4().hex[:6]}"
    _install_llm(monkeypatch, ProposalLLM({"subject": name, "reason": "博物学内容成体系。"}))
    try:
        await extract_and_save_knowledge("doc-reject", f"{prefix}标本")
        proposal = next(
            p for p in client.get(PROPOSALS_URL).json()["proposals"] if p["name"] == name
        )
        response = client.post(f"{PROPOSALS_URL}/{proposal['id']}/reject")
        assert response.status_code == 200
        assert response.json()["status"] == "已拒绝"

        assert name not in _subject_names()
        assert name not in _pending_names()
        nodes = _nodes_by_title_prefix(prefix)
        assert {n.subject for n in nodes} == {"未分类"}

        assert client.post(f"{PROPOSALS_URL}/{proposal['id']}/reject").status_code == 409
        assert client.post(f"{PROPOSALS_URL}/{proposal['id']}/approve").status_code == 409
        assert client.post(f"{PROPOSALS_URL}/{uuid.uuid4()}/approve").status_code == 404
        assert client.post(f"{PROPOSALS_URL}/{uuid.uuid4()}/reject").status_code == 404
    finally:
        _cleanup(name)


@pytest.mark.asyncio
async def test_duplicate_proposal_dedup(monkeypatch, tmp_path):
    """去重口径：同名已有待批提议时跳过（第一条的标题为准）；名字入清单后不再提议。"""
    from app.config import settings
    from app.knowledge.pipeline import extract_and_save_knowledge

    monkeypatch.setattr(settings, "vectors_db_path", str(tmp_path / "dedup.db"))
    name = _unique("天文观测")
    first, second = uuid.uuid4().hex[:6], uuid.uuid4().hex[:6]
    _install_llm(monkeypatch, ProposalLLM({"subject": name, "reason": "观测天文学内容。"}))
    try:
        await extract_and_save_knowledge("doc-dedup-1", f"天文{first}甲")
        await extract_and_save_knowledge("doc-dedup-2", f"天文{second}乙")
        proposals = [p for p in client.get(PROPOSALS_URL).json()["proposals"] if p["name"] == name]
        assert len(proposals) == 1
        assert proposals[0]["knowledge_titles"] == [f"天文{first}甲"]

        approve = client.post(f"{PROPOSALS_URL}/{proposals[0]['id']}/approve")
        assert approve.status_code == 200
        assert approve.json()["reclassified"] == 1
        # 第二份资料的知识点不在第一条提议的标题里，批准不碰它
        with SessionLocal() as db:
            assert (
                db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == f"天文{second}乙"))
                .one()
                .subject
                == "未分类"
            )
        # 名字已在清单内：再次归类失败也不再产出待批提议
        await extract_and_save_knowledge("doc-dedup-3", f"天文{uuid.uuid4().hex[:6]}丙")
        assert name not in _pending_names()
    finally:
        _cleanup(name)


@pytest.mark.asyncio
async def test_rejected_name_can_be_proposed_again(monkeypatch, tmp_path):
    """拒绝不封杀同名：下次归类再失败时重新落一条待批提议（带新的知识点标题）。"""
    from app.config import settings
    from app.knowledge.pipeline import extract_and_save_knowledge

    monkeypatch.setattr(settings, "vectors_db_path", str(tmp_path / "again.db"))
    name = _unique("矿物学")
    _install_llm(monkeypatch, ProposalLLM({"subject": name, "reason": "矿物学内容。"}))
    try:
        await extract_and_save_knowledge("doc-again-1", f"矿物{uuid.uuid4().hex[:6]}甲")
        proposal = next(
            p for p in client.get(PROPOSALS_URL).json()["proposals"] if p["name"] == name
        )
        assert client.post(f"{PROPOSALS_URL}/{proposal['id']}/reject").status_code == 200

        title = f"矿物{uuid.uuid4().hex[:6]}乙"
        await extract_and_save_knowledge("doc-again-2", title)
        again = [p for p in client.get(PROPOSALS_URL).json()["proposals"] if p["name"] == name]
        assert len(again) == 1
        assert again[0]["knowledge_titles"] == [title]
    finally:
        _cleanup(name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        "字符串提议",
        {},
        {"subject": ""},
        {"subject": "数学"},
        {"subject": "未分类"},
        {"subject": "a" * 101},
        {"subject": ["数学", "物理"]},
        {"subject": "两\n行"},
    ],
)
async def test_invalid_proposal_payloads_are_ignored(monkeypatch, payload):
    """清单内／未分类／空／超长／多行／数组学科的提议一律视为无提议。"""
    _install_llm(monkeypatch, ProposalLLM(payload))
    nodes, _, proposal = await extract_knowledge("正文")
    assert nodes
    assert proposal is None


@pytest.mark.asyncio
async def test_non_string_reason_is_coerced(monkeypatch):
    _install_llm(monkeypatch, ProposalLLM({"subject": "考古学", "reason": ["理由数组"]}))
    _, _, proposal = await extract_knowledge("正文")
    assert proposal == {"subject": "考古学", "reason": ""}


def test_record_proposal_dedup_rules():
    """单元口径：清单内名称、未分类与同名待批都直接跳过（返回 None）。"""
    name = _unique("草稿学")
    try:
        with SessionLocal() as db:
            assert record_proposal(db, name="数学", reason="r", knowledge_titles=["t"]) is None
            assert record_proposal(db, name="未分类", reason="r", knowledge_titles=["t"]) is None
            assert record_proposal(db, name="a" * 101, reason="r", knowledge_titles=["t"]) is None
            first = record_proposal(db, name=name, reason="r", knowledge_titles=[" b ", "", "a"])
            db.commit()
            assert first is not None
            assert first.knowledge_titles == ["a", "b"]
        with SessionLocal() as db:
            assert record_proposal(db, name=name, reason="r2", knowledge_titles=["c"]) is None
            db.rollback()
    finally:
        _cleanup(name)


def test_approve_reclassifies_and_supplements_same_subject_edges():
    """批准的重新归类复用 08 建边入口：同学科补「相关关联」，不重复调用云端向量化。"""
    name = _unique("航海学")
    a, b = f"航海甲{uuid.uuid4().hex[:6]}", f"航海乙{uuid.uuid4().hex[:6]}"
    from app.knowledge.graph import save_knowledge

    save_knowledge(
        "default", [{"title": a, "content": "正文"}, {"title": b, "content": "正文"}], []
    )
    try:
        with SessionLocal() as db:
            record_proposal(db, name=name, reason="航海知识成体系。", knowledge_titles=[a, b])
            db.commit()
        proposal = next(
            p for p in client.get(PROPOSALS_URL).json()["proposals"] if p["name"] == name
        )
        response = client.post(f"{PROPOSALS_URL}/{proposal['id']}/approve")
        assert response.status_code == 200
        assert response.json()["reclassified"] == 2
        with SessionLocal() as db:
            nodes = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title.in_([a, b]))).all()
            assert {n.subject for n in nodes} == {name}
            ids = {n.id for n in nodes}
            edges = db.scalars(
                select(KnowledgeEdge).where(
                    or_(KnowledgeEdge.from_node.in_(ids), KnowledgeEdge.to_node.in_(ids))
                )
            ).all()
            assert any(e.relation_type == "相关关联" for e in edges)
    finally:
        _cleanup(name)


def test_approve_skips_subject_added_by_teacher_and_leaves_classified_nodes():
    """教师先手动建了同学科：批准不重复新增；已归入其他学科的知识点不动。"""
    name = _unique("版本学")
    a, b = f"版本甲{uuid.uuid4().hex[:6]}", f"版本乙{uuid.uuid4().hex[:6]}"
    from app.knowledge.graph import save_knowledge

    save_knowledge(
        "default", [{"title": a, "content": "正文"}, {"title": b, "content": "正文"}], []
    )
    with SessionLocal() as db:
        node_a = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == a)).one()
        node_a.subject = "数学"
        db.commit()
    try:
        with SessionLocal() as db:
            record_proposal(db, name=name, reason="r", knowledge_titles=[a, b])
            db.commit()
        # 教师在批准前先手动建了同学科：批准不重复新增、复用那一项
        created = client.post("/api/v1/knowledge/subjects", json={"name": name}).json()
        proposal = next(
            p for p in client.get(PROPOSALS_URL).json()["proposals"] if p["name"] == name
        )
        response = client.post(f"{PROPOSALS_URL}/{proposal['id']}/approve")
        assert response.status_code == 200
        assert response.json()["subject_id"] == created["id"]
        assert response.json()["reclassified"] == 1
        subjects = [
            s
            for s in client.get("/api/v1/knowledge/subjects").json()["subjects"]
            if s["name"] == name
        ]
        assert len(subjects) == 1
        with SessionLocal() as db:
            by_title = {
                n.title: n.subject
                for n in db.scalars(
                    select(KnowledgeNode).where(KnowledgeNode.title.in_([a, b]))
                ).all()
            }
            assert by_title == {a: "数学", b: name}
    finally:
        _cleanup(name)


def test_proposals_table_created_idempotently(tmp_path):
    """新表走既有 create_all 迁移链：已有库补建 subject_proposals，重复执行幂等。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'proposals.db'}")
    Base.metadata.create_all(engine)
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(subject_proposals)")}
    assert {
        "id",
        "user_id",
        "name",
        "reason",
        "knowledge_titles",
        "status",
        "created_at",
        "updated_at",
    } <= cols
