"""冲突检测与教师审核测试（ADR-0001：定义冲突唯一类别，审核前新节点不入图谱）。

主接缝：HTTP API + stub 网关 + 直接种子数据（图谱表、向量库标题索引）。
"""

import uuid

from fastapi.testclient import TestClient

import app.api.v1.documents as documents_module
import app.core.embedding.factory as embedding_factory_module
import app.knowledge.conflict as conflict_module
import app.knowledge.graph as graph_module
import app.knowledge.parsers as parsers_module
import app.knowledge.pipeline as pipeline_module
from app.core.embedding.stub import StubEmbedder
from app.core.llm.providers.stub import StubProvider
from app.db import SessionLocal, init_db
from app.db.models import Document, KnowledgeEdge, KnowledgeNode
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在


def _sfx() -> str:
    return uuid.uuid4().hex[:6]


class _FakeParser:
    """绕过真实解析器，parse_document 只为走通管道。"""

    async def parse(self, file_path: str) -> str:
        return "材料正文（由 fake_extract 提供知识点）"


def _patch_common(monkeypatch, store: VectorStore) -> None:
    """stub 网关 + stub 向量化 + 隔离向量库（标题索引），所有用例共用。"""
    monkeypatch.setattr(conflict_module, "get_llm", lambda: StubProvider())
    # 向量化只依赖 Embedder 接口：冲突模块早绑定，管道晚绑定（走工厂）
    monkeypatch.setattr(conflict_module, "get_embedder", lambda: StubEmbedder())
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: StubEmbedder())
    monkeypatch.setattr(conflict_module, "VectorStore", lambda: store)
    monkeypatch.setattr(graph_module, "VectorStore", lambda: store)


def _patch_extraction(
    monkeypatch, nodes: list[dict], edges: list[dict], detected: list[tuple[str, str]]
) -> None:
    """提取结果固定为种子节点；LLM 比对确定性化：新知识含「（冲突版）」即判矛盾。"""

    async def fake_extract(text: str) -> tuple[list[dict], list[dict]]:
        return nodes, edges

    async def fake_compare(old: str, new: str) -> dict:
        detected.append((old, new))
        if "（冲突版）" in new:
            return {"conflict": True, "description": "新旧定义相互矛盾"}
        return {"conflict": False, "description": ""}

    monkeypatch.setattr(graph_module, "extract_knowledge", fake_extract)
    monkeypatch.setattr(conflict_module, "compare_content", fake_compare)


def _upload(monkeypatch, tmp_path, name: str) -> str:
    monkeypatch.setattr(parsers_module, "get_parser", lambda ft: _FakeParser())

    async def fake_index_chunks(doc_id: str, chunks: list[str]) -> None:
        return None

    monkeypatch.setattr(pipeline_module, "index_chunks", fake_index_chunks)
    monkeypatch.setattr(
        documents_module, "save_upload", lambda content, filename: str(tmp_path / filename)
    )
    r = client.post("/api/v1/documents/upload", files={"file": (name, b"content", "text/plain")})
    assert r.status_code == 200
    return r.json()["id"]


async def _seed_node(title: str, content: str, store: VectorStore) -> str:
    db = SessionLocal()
    try:
        node = KnowledgeNode(user_id="default", title=title, content=content)
        db.add(node)
        db.commit()
        db.refresh(node)
        node_id = node.id
    finally:
        db.close()
    emb = (await StubEmbedder().embed([title]))[0]
    store.add_node_title(node_id, title, emb)
    return node_id


def _seed_edge(from_id: str, to_id: str, relation: str = "前置依赖") -> str:
    db = SessionLocal()
    try:
        edge = KnowledgeEdge(
            user_id="default", from_node=from_id, to_node=to_id, relation_type=relation
        )
        db.add(edge)
        db.commit()
        db.refresh(edge)
        return edge.id
    finally:
        db.close()


def _node_by_title(title: str) -> list[KnowledgeNode]:
    db = SessionLocal()
    try:
        return db.query(KnowledgeNode).filter(KnowledgeNode.title == title).all()
    finally:
        db.close()


def _pending_by_new_title(title: str) -> list[dict]:
    rows = client.get("/api/v1/conflicts", params={"status": "待审"}).json()["conflicts"]
    return [c for c in rows if (c["new_knowledge"] or {}).get("title") == title]


async def test_same_name_contradiction_pends_and_stays_out_of_graph(monkeypatch, tmp_path):
    """AC1：同名但内容矛盾 → 待审队列出现记录，图谱无重复同名节点。"""
    store = VectorStore(str(tmp_path / "v.db"))
    _patch_common(monkeypatch, store)
    title = f"TCP三次握手_{_sfx()}"
    old_id = await _seed_node(title, "通过三次报文交换建立可靠连接", store)
    detected: list[tuple[str, str]] = []
    _patch_extraction(
        monkeypatch,
        [{"title": title, "content": "（冲突版）两次报文即可建立连接"}],
        [],
        detected,
    )
    doc_id = _upload(monkeypatch, tmp_path, f"矛盾材料_{_sfx()}.txt")

    pending = _pending_by_new_title(title)
    assert len(pending) == 1
    assert pending[0]["diff_description"] == "新旧定义相互矛盾"
    assert pending[0]["existing_knowledge"]["id"] == old_id
    assert detected, "同名候选应经过 LLM 比对"

    rows = _node_by_title(title)
    assert len(rows) == 1 and rows[0].id == old_id, "审核前新节点不入图谱，无重复同名节点"

    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        assert doc is not None
        assert doc.status == "有冲突"
        assert doc.conflict_count == 1
    finally:
        db.close()


async def test_near_name_candidates_reach_llm_compare(monkeypatch, tmp_path):
    """AC2：字面不同、向量相近的近名候选进入 LLM 比对并可产生待审。"""
    store = VectorStore(str(tmp_path / "v.db"))
    _patch_common(monkeypatch, store)
    old_title = f"TCP三次握手_{_sfx()}"
    new_title = f"三次握手过程_{_sfx()}"  # 字面不同；stub 向量同向 → 余弦距离 0 → 近名候选
    old_content = "通过三次报文交换建立可靠连接"
    old_id = await _seed_node(old_title, old_content, store)
    new_content = "（冲突版）握手次数其实无关紧要"
    detected: list[tuple[str, str]] = []
    _patch_extraction(monkeypatch, [{"title": new_title, "content": new_content}], [], detected)
    _upload(monkeypatch, tmp_path, f"近名材料_{_sfx()}.txt")

    pending = _pending_by_new_title(new_title)
    assert len(pending) == 1
    assert pending[0]["existing_knowledge"]["id"] == old_id
    assert (old_content, new_content) in detected, "近名候选应交 LLM 比对"
    assert _node_by_title(new_title) == [], "审核前近名冲突节点不入图谱"


async def test_review_accept_new_replaces_old(monkeypatch, tmp_path):
    """AC3a：接受新 → 旧节点被替换，旧节点的边重挂到新节点。"""
    store = VectorStore(str(tmp_path / "v.db"))
    _patch_common(monkeypatch, store)
    title = f"TCP三次握手_{_sfx()}"
    helper_title = f"可靠传输_{_sfx()}"
    new_content = "（冲突版）两次报文即可建立连接"
    old_id = await _seed_node(title, "通过三次报文交换建立可靠连接", store)
    helper_id = await _seed_node(helper_title, "传输层需要可靠性机制", store)
    _seed_edge(old_id, helper_id)
    detected: list[tuple[str, str]] = []
    _patch_extraction(monkeypatch, [{"title": title, "content": new_content}], [], detected)
    _upload(monkeypatch, tmp_path, f"替换材料_{_sfx()}.txt")

    conflict_id = _pending_by_new_title(title)[0]["id"]
    r = client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": "接受新"})
    assert r.status_code == 200
    assert r.json()["status"] == "已接受"

    rows = _node_by_title(title)
    assert len(rows) == 1
    new_node = rows[0]
    assert new_node.id != old_id, "旧节点已被替换"
    assert new_node.content == new_content

    db = SessionLocal()
    try:
        assert db.get(KnowledgeNode, old_id) is None
        edges = db.query(KnowledgeEdge).filter(KnowledgeEdge.from_node == new_node.id).all()
        assert [e.to_node for e in edges] == [helper_id], "旧节点的边应重挂到新节点"
    finally:
        db.close()

    hits = store.search_node_titles((await StubEmbedder().embed([title]))[0], k=5)
    hit_ids = {h["node_id"] for h in hits}
    assert old_id not in hit_ids and new_node.id in hit_ids, "标题索引应同步替换"


async def test_review_keep_old_discards_new(monkeypatch, tmp_path):
    """AC3b：保留旧 → 新知丢弃，图谱不变；重复审核返回 409。"""
    store = VectorStore(str(tmp_path / "v.db"))
    _patch_common(monkeypatch, store)
    title = f"TCP三次握手_{_sfx()}"
    old_content = "通过三次报文交换建立可靠连接"
    old_id = await _seed_node(title, old_content, store)
    detected: list[tuple[str, str]] = []
    _patch_extraction(
        monkeypatch, [{"title": title, "content": "（冲突版）两次报文即可建立连接"}], [], detected
    )
    _upload(monkeypatch, tmp_path, f"丢弃材料_{_sfx()}.txt")

    conflict_id = _pending_by_new_title(title)[0]["id"]
    r = client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": "保留旧"})
    assert r.status_code == 200
    assert r.json()["status"] == "已拒绝"

    rows = _node_by_title(title)
    assert len(rows) == 1 and rows[0].id == old_id and rows[0].content == old_content

    r2 = client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": "保留旧"})
    assert r2.status_code == 409


async def test_review_coexist_keeps_both(monkeypatch, tmp_path):
    """AC3c：并存 → 新旧双节点保留（并标注差异）。"""
    store = VectorStore(str(tmp_path / "v.db"))
    _patch_common(monkeypatch, store)
    old_title = f"TCP三次握手_{_sfx()}"
    new_title = f"三次握手过程_{_sfx()}"
    await _seed_node(old_title, "通过三次报文交换建立可靠连接", store)
    new_content = "（冲突版）握手次数其实无关紧要"
    detected: list[tuple[str, str]] = []
    _patch_extraction(monkeypatch, [{"title": new_title, "content": new_content}], [], detected)
    _upload(monkeypatch, tmp_path, f"并存材料_{_sfx()}.txt")

    pending = _pending_by_new_title(new_title)[0]
    r = client.post(f"/api/v1/conflicts/{pending['id']}/review", json={"action": "并存"})
    assert r.status_code == 200
    assert r.json()["status"] == "并存"

    new_rows = _node_by_title(new_title)
    assert len(new_rows) == 1 and new_rows[0].content == new_content
    assert len(_node_by_title(old_title)) == 1, "旧节点保留，双节点并存"

    row = client.get("/api/v1/conflicts", params={"status": "并存"}).json()["conflicts"]
    assert any(c["id"] == pending["id"] and c["diff_description"] for c in row), "差异说明应保留"


def test_review_validations(monkeypatch):
    """未知冲突 404；非法动作 422；未审核冲突不可被无关动作绕过校验。"""
    r404 = client.post(f"/api/v1/conflicts/{uuid.uuid4()}/review", json={"action": "保留旧"})
    assert r404.status_code == 404

    r422 = client.post(f"/api/v1/conflicts/{uuid.uuid4()}/review", json={"action": "覆盖"})
    assert r422.status_code == 422


async def test_non_conflicting_knowledge_saves_directly(monkeypatch, tmp_path):
    """AC4：无矛盾的新知识直接入库（既有行为保持）；同名一致重述去重不入库。"""
    store = VectorStore(str(tmp_path / "v.db"))
    _patch_common(monkeypatch, store)
    old_title = f"TCP三次握手_{_sfx()}"
    old_content = "通过三次报文交换建立可靠连接"
    await _seed_node(old_title, old_content, store)
    near_title = f"三次握手过程_{_sfx()}"  # 近名但比对无矛盾 → 作为新节点入库
    fresh_title = f"UDP协议_{_sfx()}"  # 无候选 → 直接入库
    detected: list[tuple[str, str]] = []
    _patch_extraction(
        monkeypatch,
        [
            {"title": old_title, "content": "一致的重述（无冲突标记）"},
            {"title": near_title, "content": "握手过程的分步描述（无冲突标记）"},
            {"title": fresh_title, "content": "无连接的传输层协议"},
        ],
        [],
        detected,
    )
    doc_id = _upload(monkeypatch, tmp_path, f"一致材料_{_sfx()}.txt")

    assert _pending_by_new_title(old_title) == []
    assert _pending_by_new_title(near_title) == []
    assert _pending_by_new_title(fresh_title) == []

    old_rows = _node_by_title(old_title)
    assert len(old_rows) == 1 and old_rows[0].content == old_content, (
        "同名一致重述去重，无重复同名节点"
    )
    assert len(_node_by_title(near_title)) == 1, "近名无矛盾节点正常入库"
    assert len(_node_by_title(fresh_title)) == 1

    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        assert doc is not None
        assert doc.status == "已完成"
        assert doc.conflict_count == 0
    finally:
        db.close()
