"""票 08：清单维护、唯一主学科、归类与入库关系的离线回归契约。"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, init_db
from app.db.models import Base, KnowledgeEdge, KnowledgeNode
from app.knowledge.graph import extract_knowledge, save_knowledge
from app.knowledge.subjects import initialize_subjects
from app.main import app
from tests.support.fakes import OffListSubjectLLM, PromptCapturingLLM

client = TestClient(app)
init_db()


def test_subject_crud_and_node_reclassification():
    name = f"学科_{uuid.uuid4().hex[:8]}"
    response = client.post("/api/v1/knowledge/subjects", json={"name": f" {name} "})
    assert response.status_code == 201
    subject = response.json()
    assert subject["name"] == name
    assert client.post("/api/v1/knowledge/subjects", json={"name": name}).status_code == 409
    save_knowledge("default", [{"title": name, "content": "正文", "subject": name}], [])
    assert (
        client.patch(
            f"/api/v1/knowledge/subjects/{subject['id']}", json={"name": "数学"}
        ).status_code
        == 409
    )
    with SessionLocal() as db:
        assert (
            db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == name)).one().subject
            == name
        )
    renamed = name + "新"
    assert (
        client.patch(
            f"/api/v1/knowledge/subjects/{subject['id']}", json={"name": renamed}
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        assert (
            db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == name)).one().subject
            == renamed
        )
    assert client.delete(f"/api/v1/knowledge/subjects/{subject['id']}").status_code == 200
    with SessionLocal() as db:
        node = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == name)).one()
        assert node.subject == "未分类"
        db.delete(node)
        db.commit()
    assert client.delete(f"/api/v1/knowledge/subjects/{subject['id']}").status_code == 404
    # 初始化不复活教师删除的清单项。
    init_db()
    assert name not in {
        s["name"] for s in client.get("/api/v1/knowledge/subjects").json()["subjects"]
    }


def test_reserved_and_invalid_subject_names():
    subjects = client.get("/api/v1/knowledge/subjects").json()["subjects"]
    names = {s["name"] for s in subjects}
    assert {
        "语文",
        "数学",
        "英语",
        "物理",
        "化学",
        "生物",
        "历史",
        "地理",
        "政治",
        "信息技术",
        "未分类",
    } <= names
    fallback = next(s for s in subjects if s["name"] == "未分类")
    assert client.delete(f"/api/v1/knowledge/subjects/{fallback['id']}").status_code == 409
    assert (
        client.patch(
            f"/api/v1/knowledge/subjects/{fallback['id']}", json={"name": "其他"}
        ).status_code
        == 409
    )
    for name in ("", "   ", "a" * 101):
        assert client.post("/api/v1/knowledge/subjects", json={"name": name}).status_code == 422


@pytest.mark.asyncio
async def test_extract_uses_current_list_and_chapters(monkeypatch):
    from app.core.llm import factory

    llm = PromptCapturingLLM()
    monkeypatch.setattr(factory, "get_llm", lambda: llm)
    nodes, _ = await extract_knowledge("一次函数\n函数图象")
    subjects = {s["name"] for s in client.get("/api/v1/knowledge/subjects").json()["subjects"]}
    assert len(nodes) == 2
    assert all(n["subject"] in subjects and n["chapter"] for n in nodes)
    assert "不得自造" in llm.prompts[-1]
    assert all(f"- {name}" in llm.prompts[-1] for name in subjects)
    monkeypatch.setattr(factory, "get_llm", lambda: OffListSubjectLLM())
    nodes, _ = await extract_knowledge("考古知识")
    assert nodes[0]["subject"] == "未分类"


@pytest.mark.parametrize("subject", [None, "不存在的学科", ["数学", "物理"]])
def test_save_revalidates_subject(subject):
    title = uuid.uuid4().hex
    save_knowledge("default", [{"title": title, "content": "正文", "subject": subject}], [])
    with SessionLocal() as db:
        node = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == title)).one()
        assert node.subject == "未分类"
        db.delete(node)
        db.commit()


def test_sqlite_constraint_and_idempotent_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'subjects.db'}")
    Base.metadata.create_all(engine)
    initialize_subjects(engine, seed=True)
    initialize_subjects(engine, seed=False)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(
                "INSERT INTO knowledge_nodes (id,user_id,title,content,subject) VALUES ('bad','default','坏','正文','清单外')"
            )
        conn.exec_driver_sql("DELETE FROM subjects WHERE name='数学'")
    initialize_subjects(engine, seed=False)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM subjects WHERE name='数学'").scalar() == 0


def test_related_edges_same_subject_and_cross_subject_semantics(monkeypatch, tmp_path):
    from app.config import settings

    monkeypatch.setattr(settings, "vectors_db_path", str(tmp_path / "related.db"))
    suffix = uuid.uuid4().hex
    embedding = [1.0] + [0.0] * 7
    titles = [f"{label}_{suffix}" for label in ("甲", "乙", "丙", "丁")]
    save_knowledge(
        "default",
        [{"title": titles[0], "content": "正文", "subject": "数学"}],
        [],
        title_embeddings={titles[0]: embedding},
        title_spaces={titles[0]: "test-space"},
    )
    save_knowledge("default", [{"title": titles[1], "content": "正文", "subject": "数学"}], [])
    save_knowledge(
        "default",
        [{"title": titles[2], "content": "正文", "subject": "物理"}],
        [],
        title_embeddings={titles[2]: embedding},
        title_spaces={titles[2]: "test-space"},
    )
    save_knowledge(
        "default",
        [{"title": titles[3], "content": "无关正文", "subject": "历史"}],
        [],
        title_embeddings={titles[3]: [-v for v in embedding]},
        title_spaces={titles[3]: "test-space"},
    )
    with SessionLocal() as db:
        nodes = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title.in_(titles))).all()
        ids = {n.title: n.id for n in nodes}
        edges = db.scalars(
            select(KnowledgeEdge).where(
                KnowledgeEdge.from_node.in_(ids.values()), KnowledgeEdge.to_node.in_(ids.values())
            )
        ).all()
        pairs = {
            frozenset((e.from_node, e.to_node)) for e in edges if e.relation_type == "相关关联"
        }
        assert frozenset((ids[titles[0]], ids[titles[1]])) in pairs
        assert frozenset((ids[titles[0]], ids[titles[2]])) in pairs
        assert all(e.from_node != e.to_node for e in edges)
        assert all(ids[titles[3]] not in pair for pair in pairs)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "", ["数学", "物理"]])
async def test_extract_rejects_missing_or_multiple_subjects(monkeypatch, value):
    from app.core.llm import factory

    monkeypatch.setattr(factory, "get_llm", lambda: OffListSubjectLLM(value))
    nodes, _ = await extract_knowledge("知识正文")
    assert nodes[0]["subject"] == "未分类"


@pytest.mark.asyncio
async def test_current_list_is_injected_and_save_rechecks_after_delete(monkeypatch):
    from app.core.llm import factory

    name = f"新增学科_{uuid.uuid4().hex[:8]}"
    subject = client.post("/api/v1/knowledge/subjects", json={"name": name}).json()
    llm = PromptCapturingLLM()
    monkeypatch.setattr(factory, "get_llm", lambda: llm)
    await extract_knowledge("正文")
    assert f"- {name}" in llm.prompts[-1]
    monkeypatch.setattr(factory, "get_llm", lambda: OffListSubjectLLM(name))
    title = uuid.uuid4().hex
    nodes, edges = await extract_knowledge(title)
    assert nodes[0]["subject"] == name
    assert client.delete(f"/api/v1/knowledge/subjects/{subject['id']}").status_code == 200
    save_knowledge("default", nodes, edges)
    with SessionLocal() as db:
        assert (
            db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == title[:12])).one().subject
            == "未分类"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_before_review", [False, True])
async def test_review_preserves_metadata_but_revalidates_current_subject(
    monkeypatch, tmp_path, delete_before_review
):
    from app.config import settings
    from app.db.models import Conflict
    from app.knowledge.conflict import resolve_conflict

    monkeypatch.setattr(settings, "vectors_db_path", str(tmp_path / "review.db"))
    name = f"裁决学科_{uuid.uuid4().hex[:8]}"
    subject = client.post("/api/v1/knowledge/subjects", json={"name": name}).json()
    title = uuid.uuid4().hex
    with SessionLocal() as db:
        conflict = Conflict(
            user_id="default",
            category="定义冲突",
            status="待审",
            new_knowledge={"title": title, "content": "正文", "subject": name, "chapter": "第一章"},
        )
        db.add(conflict)
        db.commit()
        conflict_id = conflict.id
        assert db.scalar(select(KnowledgeNode.id).where(KnowledgeNode.title == title)) is None
    if delete_before_review:
        assert client.delete(f"/api/v1/knowledge/subjects/{subject['id']}").status_code == 200
    await resolve_conflict(conflict_id, "并存")
    with SessionLocal() as db:
        node = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == title)).one()
        assert node.subject == ("未分类" if delete_before_review else name)
        assert node.chapter == "第一章"
    if not delete_before_review:
        client.delete(f"/api/v1/knowledge/subjects/{subject['id']}")


def test_legacy_subject_migration_and_raw_sql_lifecycle(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE knowledge_nodes (id TEXT PRIMARY KEY, subject TEXT)")
        conn.exec_driver_sql(
            "INSERT INTO knowledge_nodes VALUES ('null', NULL), ('invalid','旧学科'), ('math','数学')"
        )
    Base.metadata.create_all(engine)
    initialize_subjects(engine, seed=True)
    initialize_subjects(engine, seed=False)
    with engine.begin() as conn:
        assert {
            row[0]: row[1]
            for row in conn.exec_driver_sql("SELECT id, subject FROM knowledge_nodes")
        } == {
            "null": "未分类",
            "invalid": "未分类",
            "math": "数学",
        }
        conn.exec_driver_sql("UPDATE subjects SET name='算术' WHERE name='数学'")
        assert (
            conn.exec_driver_sql("SELECT subject FROM knowledge_nodes WHERE id='math'").scalar()
            == "算术"
        )
        conn.exec_driver_sql("DELETE FROM subjects WHERE name='算术'")
        assert (
            conn.exec_driver_sql("SELECT subject FROM knowledge_nodes WHERE id='math'").scalar()
            == "未分类"
        )
        for sql in (
            "UPDATE knowledge_nodes SET subject=NULL WHERE id='math'",
            "UPDATE knowledge_nodes SET subject='已删除学科' WHERE id='math'",
            "DELETE FROM subjects WHERE name='未分类'",
            "UPDATE subjects SET name='其他' WHERE name='未分类'",
        ):
            with pytest.raises(IntegrityError):
                conn.exec_driver_sql(sql)


def test_relation_guard_and_symmetric_deduplication():
    suffix = uuid.uuid4().hex
    a, b = f"a{suffix}", f"b{suffix}"
    save_knowledge(
        "default",
        [{"title": a, "content": "正文"}, {"title": b, "content": "正文"}],
        [
            {"from": a, "to": b, "relation_type": "相关关联"},
            {"from": b, "to": a, "relation_type": "相关关联"},
            {"from": a, "to": a, "relation_type": "相关关联"},
            {"from": a, "to": b, "relation_type": "新关系"},
            {"from": a, "to": "待审未入图节点", "relation_type": "相关关联"},
        ],
    )
    with SessionLocal() as db:
        ids = [
            n.id for n in db.scalars(select(KnowledgeNode).where(KnowledgeNode.title.in_([a, b])))
        ]
        edges = db.scalars(
            select(KnowledgeEdge).where(
                KnowledgeEdge.from_node.in_(ids), KnowledgeEdge.to_node.in_(ids)
            )
        ).all()
        assert len(edges) == 1
        assert edges[0].relation_type == "相关关联"


@pytest.mark.asyncio
@pytest.mark.parametrize("subject_value", ["数学", "清单外学科"])
async def test_pipeline_persists_classification_and_chapter(monkeypatch, tmp_path, subject_value):
    from app.config import settings
    from app.core.llm import factory
    from app.knowledge.pipeline import extract_and_save_knowledge

    monkeypatch.setattr(settings, "vectors_db_path", str(tmp_path / "pipeline.db"))
    monkeypatch.setattr(factory, "get_llm", lambda: OffListSubjectLLM(subject_value))
    title = f"管道{uuid.uuid4().hex[:8]}"
    assert await extract_and_save_knowledge("source-doc", title) == 0
    with SessionLocal() as db:
        node = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == title)).one()
        assert node.subject == (subject_value if subject_value == "数学" else "未分类")
        assert node.chapter == "第1章"
        assert node.source_docs == ["source-doc"]
        from app.core.embedding.factory import get_embedder
        from app.knowledge.title_vectors import title_vector_space
        from app.knowledge.vector_store import VectorStore

        conn = VectorStore()._connect()
        try:
            row = conn.execute(
                "SELECT t.space,length(v.embedding) FROM node_titles t "
                "JOIN node_title_embeddings v ON t.rowid=v.rowid WHERE t.node_id=?",
                (node.id,),
            ).fetchone()
            assert row is not None
            assert row[0] == title_vector_space(get_embedder(), row[1] // 4)
        finally:
            conn.close()


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_subject_name_business_error_is_400_but_framework_errors_are_422(method):
    subject = client.post("/api/v1/knowledge/subjects", json={"name": uuid.uuid4().hex}).json()
    url = "/api/v1/knowledge/subjects" + (f"/{subject['id']}" if method == "PATCH" else "")
    response = client.request(method, url, json={"name": "两行\n名称"})
    assert response.status_code == 400
    assert isinstance(response.json()["detail"], str)
    for payload in ({}, {"name": 42}, {"name": "a" * 101}, {"name": ""}):
        response = client.request(method, url, json=payload)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
    client.delete(f"/api/v1/knowledge/subjects/{subject['id']}")
