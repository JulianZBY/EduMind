"""票 08 P1：待审不入图，所有裁决建点分支共享已入图补边。"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal, init_db
from app.db.models import Conflict, KnowledgeEdge, KnowledgeNode, Subject
from app.main import app

client = TestClient(app)
init_db()


@pytest.fixture
def review_case(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "vectors_db_path", str(tmp_path / "titles.db"))
    suffix = uuid.uuid4().hex
    subject = f"裁决补边{suffix}"
    with SessionLocal() as db:
        db.add(Subject(name=subject))
        db.flush()
        old = KnowledgeNode(
            user_id="default",
            title=f"旧{suffix}",
            content="旧正文",
            subject=subject,
            source_docs=["old-doc"],
        )
        peer = KnowledgeNode(
            user_id="default", title=f"邻{suffix}", content="邻正文", subject=subject
        )
        db.add_all([old, peer])
        db.flush()
        edge = KnowledgeEdge(
            user_id="default", from_node=peer.id, to_node=old.id, relation_type="前置依赖"
        )
        db.add(edge)
        db.commit()
        return {
            "old": old.id,
            "peer": peer.id,
            "title": f"新{suffix}",
            "subject": subject,
            "old_title": old.title,
            "edge": edge.id,
        }


def seed_conflict(case, category):
    with SessionLocal() as db:
        conflict = Conflict(
            user_id="default",
            doc_id="new-doc",
            category=category,
            new_knowledge={"title": case["title"], "content": "新正文", "subject": case["subject"]},
            existing_knowledge={"id": case["old"], "title": case["old_title"]},
        )
        db.add(conflict)
        db.commit()
        return conflict.id


@pytest.mark.parametrize(
    ("category", "action"),
    [
        ("定义冲突", "接受新"),
        ("定义冲突", "并存"),
        ("结构冲突", "接受新"),
        ("结构冲突", "并存"),
        ("常识存疑", "照常入库"),
        ("常识存疑", "编辑修正后入库"),
    ],
)
def test_each_review_insert_supplements_related_only_after_review(review_case, category, action):
    case = review_case
    conflict_id = seed_conflict(case, category)
    with SessionLocal() as db:
        assert (
            db.scalar(select(KnowledgeNode.id).where(KnowledgeNode.title == case["title"])) is None
        )
        assert list(
            db.scalars(select(KnowledgeEdge.id).where(KnowledgeEdge.from_node == case["peer"]))
        ) == [case["edge"]]
    response = client.post(
        f"/api/v1/conflicts/{conflict_id}/review",
        json={"action": action, "revised_content": "修正正文"},
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        node = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == case["title"])).one()
        edges = list(
            db.scalars(
                select(KnowledgeEdge).where(
                    (KnowledgeEdge.from_node == node.id) | (KnowledgeEdge.to_node == node.id)
                )
            )
        )
        assert any(
            e.relation_type == "相关关联" and case["peer"] in (e.from_node, e.to_node)
            for e in edges
        )
        assert all(e.from_node != e.to_node for e in edges)
        assert all(
            db.get(KnowledgeNode, e.from_node) and db.get(KnowledgeNode, e.to_node) for e in edges
        )
        if action == "接受新":
            assert db.get(KnowledgeNode, case["old"]) is None
            inherited = db.get(KnowledgeEdge, case["edge"])
            assert inherited is not None and inherited.to_node == node.id
            assert node.source_docs == ["old-doc", "new-doc"]
        else:
            assert db.get(KnowledgeNode, case["old"]) is not None
        if action == "编辑修正后入库":
            assert node.content == "修正正文"


@pytest.fixture
def title_embedder(monkeypatch):
    import app.knowledge.conflict as conflict_module
    from tests.support.fakes import TitleVectorEmbedder

    embedder = TitleVectorEmbedder()
    monkeypatch.setattr(conflict_module, "get_embedder", lambda: embedder)
    return embedder


def attach_vector(conflict_id, case, embedder):
    from app.knowledge.title_vectors import TITLE_VECTOR_KEY, title_vector_record

    with SessionLocal() as db:
        conflict = db.get(Conflict, conflict_id)
        assert conflict is not None and conflict.new_knowledge is not None
        conflict.new_knowledge = {
            **conflict.new_knowledge,
            TITLE_VECTOR_KEY: title_vector_record(
                case["title"], [1.0] + [0.0] * (embedder.dimensions - 1), embedder
            ),
        }
        db.commit()


def entry(conflict_id):
    response = client.get("/api/v1/conflicts", params={"status": "待审"})
    assert response.status_code == 200
    return next(c for c in response.json()["conflicts"] if c["id"] == conflict_id)


def canonical_edges(edges, new_id=None):
    result = set()
    for edge in edges:
        f, t, relation = edge["from"], edge["to"], edge["relation_type"]
        f = "__new__" if f == new_id else f
        t = "__new__" if t == new_id else t
        if relation == "相关关联":
            f, t = sorted((f, t))
        result.add((f, t, relation))
    return result


@pytest.mark.parametrize("action", ["接受新", "并存", "保留旧"])
def test_complete_local_preview_matches_review_with_external_endpoint(
    review_case, title_embedder, action
):
    case = review_case
    conflict_id = seed_conflict(case, "结构冲突")
    attach_vector(conflict_id, case, title_embedder)
    # 明确关系的端点在旧点邻域外、且不属于同学科候选，仍须出现在完整预览。
    with SessionLocal() as db:
        external = KnowledgeNode(user_id="default", title=uuid.uuid4().hex, content="正文")
        db.add(external)
        db.flush()
        external_id = external.id
        conflict = db.get(Conflict, conflict_id)
        assert conflict is not None and conflict.new_knowledge is not None
        conflict.new_knowledge = {
            **conflict.new_knowledge,
            "relations": [
                {"from_title": case["title"], "to_title": external.title, "relation": "推导关系"},
                {"from_title": case["title"], "to_title": case["title"], "relation": "相关关联"},
                {
                    "from_title": case["title"],
                    "to_title": case["peer"] + "不存在",
                    "relation": "相关关联",
                },
            ],
        }
        db.commit()
    title_embedder.fail = True
    preview = entry(conflict_id)["structure_preview"]
    assert preview["complete"] is True
    assert preview["reason"] == ""
    outcome = next(o for o in preview["outcomes"] if o["action"] == action)
    if action != "保留旧":
        assert external_id in {n["id"] for n in outcome["nodes"]}
    assert title_embedder.calls == []
    assert (
        client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": action}).status_code
        == 200
    )
    assert title_embedder.calls == []
    with SessionLocal() as db:
        node = db.scalar(select(KnowledgeNode).where(KnowledgeNode.title == case["title"]))
        new_id = node.id if node else None
        ids = {new_id if n["id"] == "__new__" else n["id"] for n in outcome["nodes"]}
        actual = list(
            db.scalars(
                select(KnowledgeEdge).where(
                    KnowledgeEdge.from_node.in_(ids), KnowledgeEdge.to_node.in_(ids)
                )
            )
        )
        edges = [
            {"from": e.from_node, "to": e.to_node, "relation_type": e.relation_type} for e in actual
        ]
        assert canonical_edges(edges, new_id) == canonical_edges(outcome["edges"])
        if action != "保留旧":
            incident = list(
                db.scalars(
                    select(KnowledgeEdge).where(
                        (KnowledgeEdge.from_node == new_id) | (KnowledgeEdge.to_node == new_id)
                    )
                )
            )
            assert all(e.from_node in ids and e.to_node in ids for e in incident)


@pytest.mark.parametrize("change", ["missing", "title", "model", "dimension", "unknown", "foreign"])
def test_incomplete_preview_zero_embed(review_case, title_embedder, change):
    from app.knowledge.title_vectors import title_vector_space
    from app.knowledge.vector_store import VectorStore

    case = review_case
    conflict_id = seed_conflict(case, "结构冲突")
    if change != "missing":
        attach_vector(conflict_id, case, title_embedder)
    if change == "title":
        with SessionLocal() as db:
            c = db.get(Conflict, conflict_id)
            assert c is not None and c.new_knowledge is not None
            c.new_knowledge = {**c.new_knowledge, "title": "变更标题"}
            db.commit()
    if change == "model":
        title_embedder.model = "model-b"
    if change == "dimension":
        title_embedder.dimensions = 3
    if change in ("unknown", "foreign"):
        space = None if change == "unknown" else "foreign-space"
        VectorStore().add_node_title(case["old"], case["old_title"], [1.0] + [0.0] * 7, space=space)
        assert not VectorStore().title_space_complete(title_vector_space(title_embedder, 8), 8)
    title_embedder.fail = True
    preview = entry(conflict_id)["structure_preview"]
    assert preview["complete"] is False
    assert "预览不完整" in preview["reason"]
    assert title_embedder.calls == []
    with SessionLocal() as db:
        conflict = db.get(Conflict, conflict_id)
        assert conflict is not None and conflict.status == "待审"
        assert (
            db.scalar(select(KnowledgeNode.id).where(KnowledgeNode.title == case["title"])) is None
        )


def graph_snapshot():
    with SessionLocal() as db:
        return (
            [
                (n.id, n.title, n.content, n.subject, n.source_docs)
                for n in db.scalars(select(KnowledgeNode).order_by(KnowledgeNode.id))
            ],
            [
                (e.id, e.from_node, e.to_node, e.relation_type)
                for e in db.scalars(select(KnowledgeEdge).order_by(KnowledgeEdge.id))
            ],
        )


def index_snapshot(store):
    conn = store._connect()
    try:
        return (
            conn.execute("SELECT * FROM node_titles ORDER BY node_id").fetchall(),
            conn.execute(
                "SELECT rowid,embedding FROM node_title_embeddings ORDER BY rowid"
            ).fetchall(),
        )
    finally:
        conn.close()


@pytest.mark.parametrize("action", ["接受新", "并存", "照常入库", "编辑修正后入库"])
def test_real_fixed_dimension_409_preserves_all_state(review_case, title_embedder, action):
    from app.knowledge.vector_store import VectorStore

    case = review_case
    category = "定义冲突" if action in ("接受新", "并存") else "常识存疑"
    conflict_id = seed_conflict(case, category)
    attach_vector(conflict_id, case, title_embedder)
    store = VectorStore()
    store.add_node_title(case["old"], case["old_title"], [1.0, 0.0, 0.0], space="old-model")
    store.add_node_title(case["peer"], "邻", [0.0, 1.0, 0.0], space="old-model")
    before_graph, before_index = graph_snapshot(), index_snapshot(store)
    response = client.post(
        f"/api/v1/conflicts/{conflict_id}/review",
        json={"action": action, "revised_content": "修正正文"},
    )
    assert response.status_code == 409
    assert "维度" in response.json()["detail"]
    assert graph_snapshot() == before_graph
    assert index_snapshot(store) == before_index
    with SessionLocal() as db:
        c = db.get(Conflict, conflict_id)
        assert c is not None
        assert (c.status, c.review_action, c.revised_content) == ("待审", None, None)


@pytest.mark.asyncio
async def test_detection_saves_private_vector_without_graph_or_index_writes(
    review_case, title_embedder, monkeypatch
):
    import app.knowledge.conflict as conflict_module
    from app.knowledge.title_vectors import TITLE_VECTOR_KEY
    from tests.support.fakes import ContradictingLLM

    case = review_case
    monkeypatch.setattr(conflict_module, "get_llm", lambda: ContradictingLLM())
    nodes = [{"title": case["old_title"], "content": "矛盾正文", "subject": case["subject"]}]
    before = graph_snapshot()
    pending, duplicate = await conflict_module.detect_conflicts("default", nodes, "new-doc")
    assert pending == nodes and duplicate == []
    assert graph_snapshot() == before
    assert len(title_embedder.calls) == 1
    with SessionLocal() as db:
        c = db.scalars(
            select(Conflict).where(Conflict.existing_knowledge["id"].as_string() == case["old"])
        ).one()
        assert c.new_knowledge is not None
        assert set(c.new_knowledge[TITLE_VECTOR_KEY]) == {"title", "values", "space"}
        conflict_id = c.id
    title_embedder.fail = True
    response = entry(conflict_id)
    assert TITLE_VECTOR_KEY not in response["new_knowledge"]
    assert "values" not in str(response)
    assert len(title_embedder.calls) == 1
    from app.knowledge.vector_store import VectorStore

    conn = VectorStore()._connect()
    try:
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name='node_titles'").fetchone()
            is None
        )
    finally:
        conn.close()


@pytest.mark.parametrize(
    "action,category", [("保留旧", "定义冲突"), ("保留旧", "结构冲突"), ("拒绝", "常识存疑")]
)
def test_non_insert_review_keeps_graph_and_index(review_case, title_embedder, action, category):
    from app.knowledge.vector_store import VectorStore

    case = review_case
    conflict_id = seed_conflict(case, category)
    store = VectorStore()
    store.add_node_title(case["old"], case["old_title"], [1.0, 0.0], space="old")
    before = graph_snapshot(), index_snapshot(store)
    title_embedder.fail = True
    assert (
        client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": action}).status_code
        == 200
    )
    assert (graph_snapshot(), index_snapshot(store)) == before
    assert title_embedder.calls == []


def test_provider_value_error_is_not_dimension_409(review_case, monkeypatch):
    import app.knowledge.conflict as conflict_module

    def unconfigured():
        raise ValueError("向量化未配置。")

    monkeypatch.setattr(conflict_module, "get_embedder", unconfigured)
    conflict_id = seed_conflict(review_case, "定义冲突")
    response = TestClient(app, raise_server_exceptions=False).post(
        f"/api/v1/conflicts/{conflict_id}/review", json={"action": "接受新"}
    )
    assert response.status_code == 500


@pytest.mark.parametrize("action", ["接受新", "并存"])
def test_complete_semantic_preview_matches_actual_and_no_deleted_endpoint(
    review_case, title_embedder, action
):
    from app.knowledge.title_vectors import title_vector_space
    from app.knowledge.vector_store import VectorStore

    case = review_case
    conflict_id = seed_conflict(case, "结构冲突")
    attach_vector(conflict_id, case, title_embedder)
    with SessionLocal() as db:
        semantic = KnowledgeNode(user_id="default", title=uuid.uuid4().hex, content="正文")
        db.add(semantic)
        db.commit()
        semantic_id, semantic_title = semantic.id, semantic.title
    store = VectorStore()
    space = title_vector_space(title_embedder, 8)
    for node_id, title in ((case["old"], case["old_title"]), (semantic_id, semantic_title)):
        store.add_node_title(node_id, title, [1.0] + [0.0] * 7, space=space)
    title_embedder.fail = True
    preview = entry(conflict_id)["structure_preview"]
    assert preview["complete"] is True
    outcome = next(o for o in preview["outcomes"] if o["action"] == action)
    assert semantic_id in {n["id"] for n in outcome["nodes"]}
    assert (
        client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": action}).status_code
        == 200
    )
    assert title_embedder.calls == []
    with SessionLocal() as db:
        node = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == case["title"])).one()
        incident = list(
            db.scalars(
                select(KnowledgeEdge).where(
                    (KnowledgeEdge.from_node == node.id) | (KnowledgeEdge.to_node == node.id)
                )
            )
        )
        actual = [
            {"from": e.from_node, "to": e.to_node, "relation_type": e.relation_type}
            for e in incident
        ]
        promised = [e for e in outcome["edges"] if "__new__" in (e["from"], e["to"])]
        assert canonical_edges(actual, node.id) == canonical_edges(promised)
        if action == "接受新":
            assert all(case["old"] not in (e.from_node, e.to_node) for e in incident)
            assert (
                store.search_node_titles([1.0] + [0.0] * 7, space=space, excluded_ids=(node.id,))[
                    0
                ]["node_id"]
                == semantic_id
            )


def test_fixed_dimension_local_preview_and_recomputed_review_409(review_case, title_embedder):
    from app.knowledge.vector_store import VectorStore

    case = review_case
    conflict_id = seed_conflict(case, "结构冲突")
    attach_vector(conflict_id, case, title_embedder)
    store = VectorStore()
    store.add_node_title(case["old"], case["old_title"], [1.0, 0.0], space="old")
    before = graph_snapshot(), index_snapshot(store)
    title_embedder.fail = True
    assert entry(conflict_id)["structure_preview"]["complete"] is False
    assert title_embedder.calls == []
    title_embedder.fail = False
    title_embedder.model = "new-model"  # 强制实际裁决重算；先算再检验实际维度。
    response = client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": "接受新"})
    assert response.status_code == 409
    assert title_embedder.calls == [[case["title"]]]
    assert (graph_snapshot(), index_snapshot(store)) == before


def test_changed_model_recomputes_only_current_title_and_ignores_foreign_unknown(
    review_case, title_embedder
):
    from app.knowledge.title_vectors import title_vector_space
    from app.knowledge.vector_store import VectorStore

    case = review_case
    conflict_id = seed_conflict(case, "结构冲突")
    attach_vector(conflict_id, case, title_embedder)
    old_space = title_vector_space(title_embedder, 8)
    title_embedder.model = "new-model"
    new_space = title_vector_space(title_embedder, 8)
    store = VectorStore()
    ids = {}
    with SessionLocal() as db:
        for name in ("foreign", "unknown", "compatible"):
            node = KnowledgeNode(user_id="default", title=uuid.uuid4().hex, content="正文")
            db.add(node)
            db.flush()
            ids[name] = node.id
            store.add_node_title(
                node.id,
                node.title,
                [1.0] + [0.0] * 7,
                space={"foreign": old_space, "unknown": None, "compatible": new_space}[name],
            )
        db.commit()
    assert entry(conflict_id)["structure_preview"]["complete"] is False
    assert title_embedder.calls == []
    assert (
        client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": "并存"}).status_code
        == 200
    )
    assert title_embedder.calls == [[case["title"]]]
    with SessionLocal() as db:
        node = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == case["title"])).one()
        linked = set(
            db.scalars(
                select(KnowledgeEdge.to_node).where(
                    KnowledgeEdge.from_node == node.id, KnowledgeEdge.relation_type == "相关关联"
                )
            )
        )
        assert ids["compatible"] in linked
        assert ids["foreign"] not in linked and ids["unknown"] not in linked


def test_review_rechecks_subject_after_list_renamed_or_deleted(review_case, title_embedder):
    case = review_case
    conflict_id = seed_conflict(case, "定义冲突")
    attach_vector(conflict_id, case, title_embedder)
    with SessionLocal() as db:
        subject = db.scalars(select(Subject).where(Subject.name == case["subject"])).one()
        subject_id = subject.id
    renamed = case["subject"] + "新"
    assert (
        client.patch(f"/api/v1/knowledge/subjects/{subject_id}", json={"name": renamed}).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": "并存"}).status_code
        == 200
    )
    with SessionLocal() as db:
        node = db.scalars(select(KnowledgeNode).where(KnowledgeNode.title == case["title"])).one()
        assert node.subject == "未分类"
        old = db.get(KnowledgeNode, case["old"])
        assert old is not None and old.subject == renamed
    assert client.delete(f"/api/v1/knowledge/subjects/{subject_id}").status_code == 200
    conflict_id = seed_conflict({**case, "title": case["title"] + "删除后"}, "常识存疑")
    assert (
        client.post(
            f"/api/v1/conflicts/{conflict_id}/review", json={"action": "照常入库"}
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        node = db.scalars(
            select(KnowledgeNode).where(KnowledgeNode.title == case["title"] + "删除后")
        ).one()
        assert node.subject == "未分类"
