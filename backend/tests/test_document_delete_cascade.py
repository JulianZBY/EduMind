"""教学资料删除级联测试（票 07）：删除对话框交代的每一条后果都有离线断言背书。

级联规则（票面验收项，教师逐条确认过的口径）：
- **必删**：该资料的分块与向量、文献笔记、引用该资料的待审冲突（撤下）；
- **知识点**：仅来源于该资料的默认删（可勾选保留，保留者清空该来源引用）；
  多来源知识点摘除该来源、节点保留；关系边随节点走；
- **被题目考查的知识点**：删除前列出受影响题目；确认后题目保留、考查关系置空；
- 生成物历史版本的溯源文本不改写（史实留痕）。

离线确定性：向量化替身走 tests/support（AGENTS.md 铁律），向量库用密封临时库；
主库数据直接种子，不经上传解析管道。
"""

import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

import app.knowledge.vector_store as vector_store_module
from app.db import SessionLocal, init_db
from app.db.engine import _ensure_sqlite_columns
from app.db.models import (
    ArtifactVersion,
    Conflict,
    Document,
    KnowledgeEdge,
    KnowledgeNode,
    LiteratureNote,
    Question,
    QuestionKnowledge,
)
from app.knowledge.storage import normalize_stored_path, save_upload
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在


@pytest.fixture()
def sealed_vectors(monkeypatch, tmp_path):
    """把 VectorStore 指到密封临时库：删除断言不与同场测试的向量数据串味。"""
    store = VectorStore(str(tmp_path / "vectors.db"))
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)
    return store


# ---- 种子工具：直接落主库与向量库，不触上传/解析管道 ----


def _seed_document(filename: str = "一次函数讲义.pdf", with_file: bool = True) -> Document:
    """种一份已完成的教学资料；with_file 时在磁盘放真实字节（断言删除时一并清走）。"""
    path = Path(save_upload(b"fake document bytes", filename)) if with_file else Path("gone.pdf")
    db = SessionLocal()
    try:
        doc = Document(
            user_id="default",
            filename=filename,
            file_path=str(path),
            file_type="pdf",
            status="已完成",
            parsed_at=None,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc
    finally:
        db.close()


def _seed_node(
    title: str,
    source_docs: list[str],
    user_id: str = "default",
) -> KnowledgeNode:
    db = SessionLocal()
    try:
        node = KnowledgeNode(
            user_id=user_id, title=title, content=f"{title}的完整描述", source_docs=source_docs
        )
        db.add(node)
        db.commit()
        db.refresh(node)
        return node
    finally:
        db.close()


def _seed_edge(from_node: str, to_node: str, relation_type: str = "相关关联") -> None:
    db = SessionLocal()
    try:
        db.add(
            KnowledgeEdge(
                user_id="default", from_node=from_node, to_node=to_node, relation_type=relation_type
            )
        )
        db.commit()
    finally:
        db.close()


def _seed_note(doc_id: str, summary: str = "本资料系统讲解一次函数。") -> None:
    db = SessionLocal()
    try:
        db.add(
            LiteratureNote(
                user_id="default",
                doc_id=doc_id,
                source="教学资料",
                status="已生成",
                summary=summary,
                knowledge_index=[],
            )
        )
        db.commit()
    finally:
        db.close()


def _seed_conflict(doc_id: str, status: str, title: str) -> str:
    db = SessionLocal()
    try:
        conflict = Conflict(
            user_id="default",
            doc_id=doc_id,
            new_knowledge={"title": title, "content": f"{title}的新说法"},
            existing_knowledge={"title": title, "content": f"{title}的旧说法"},
            status=status,
        )
        db.add(conflict)
        db.commit()
        db.refresh(conflict)
        return conflict.id
    finally:
        db.close()


def _seed_question_with_knowledge(node: KnowledgeNode, content: str, weight: str = "主考") -> str:
    """种一道考查指定知识点的题目，返回题目 id。"""
    db = SessionLocal()
    try:
        question = Question(
            user_id="default",
            content=content,
            answer="A",
            type="选择",
            source_type="自编",
        )
        db.add(question)
        db.flush()
        db.add(QuestionKnowledge(question_id=question.id, knowledge_id=node.id, weight=weight))
        db.commit()
        db.refresh(question)
        return question.id
    finally:
        db.close()


def _node_by_id(node_id: str) -> KnowledgeNode | None:
    db = SessionLocal()
    try:
        return db.get(KnowledgeNode, node_id)
    finally:
        db.close()


def _question_knowledge_nodes(question_id: str) -> set[str]:
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(QuestionKnowledge).where(QuestionKnowledge.question_id == question_id)
        ).all()
        return {r.knowledge_id for r in rows}
    finally:
        db.close()


def _get_document(document_id: str):
    return client.get(f"/api/v1/documents/{document_id}")


def _preview(document_id: str):
    return client.get(f"/api/v1/documents/{document_id}/delete-preview")


def _delete(document_id: str, delete_single_source: bool = True):
    """删除请求显式携带勾选值（级联不静默：选项是明说的，不是默认值里藏着的）。"""
    return client.request(
        "DELETE",
        f"/api/v1/documents/{document_id}",
        json={"delete_single_source_knowledge": delete_single_source},
    )


# ---- 删除前预览：对话框列出的就是会发生的全部 ----


def test_preview_lists_single_source_nodes_and_affected_questions(sealed_vectors):
    """默认删除场景的预览：单来源知识点、被这些知识点考查的题目都列出来。"""
    doc = _seed_document()
    other = _seed_document(filename="另一份资料.pdf")
    single = _seed_node("一次函数的定义", [doc.id])
    multi = _seed_node("函数的概念", [doc.id, other.id])
    _seed_edge(single.id, multi.id)
    _seed_note(doc.id)
    _seed_conflict(doc.id, "待审", "一次函数的定义")
    examined = _seed_node("被考查的定义", [doc.id])
    question_id = _seed_question_with_knowledge(examined, "下列哪项是一次函数？")
    _seed_question_with_knowledge(multi, "函数的概念是？（多来源节点，不受删除影响）")

    r = _preview(doc.id)
    assert r.status_code == 200
    data = r.json()
    assert {n["id"] for n in data["knowledge_single_source"]} == {single.id, examined.id}
    assert [n["id"] for n in data["knowledge_multi_source"]] == [multi.id]
    # 受影响题目只统计「将被删的单来源知识点」；多来源节点保留、其题目不受影响
    assert [q["id"] for q in data["affected_questions"]] == [question_id]
    assert data["affected_questions"][0]["knowledge_titles"] == ["被考查的定义"]
    assert data["chunk_count"] == 0
    assert data["literature_note_present"] is True
    assert data["pending_conflict_count"] == 1


def test_preview_404_for_unknown_document():
    r = _preview(str(uuid.uuid4()))
    assert r.status_code == 404
    assert "资料不存在" in r.json()["detail"]


# ---- 删除级联：默认勾选（删单来源知识点）----


def test_delete_cascades_chunks_vectors_note_conflicts_and_single_source_nodes(sealed_vectors):
    doc = _seed_document()
    other = _seed_document(filename="保留的资料.pdf")
    single = _seed_node("勾股定理", [doc.id])
    multi = _seed_node("直角三角形", [doc.id, other.id])
    _seed_edge(single.id, multi.id)
    other_single = _seed_node("别的资料的知识点", [other.id])
    _seed_edge(single.id, other_single.id, "前置依赖")
    _seed_edge(multi.id, other_single.id)
    retained_question = _seed_question_with_knowledge(multi, "多来源知识点的题目")
    _seed_note(doc.id)
    pending = _seed_conflict(doc.id, "待审", "勾股定理")
    resolved = _seed_conflict(doc.id, "已拒绝", "勾股定理")
    examined = _seed_node("被考的勾股推论", [doc.id])
    question_id = _seed_question_with_knowledge(examined, "勾股定理的推论是什么？")

    # 向量：本资料分块 + 被删知识点的标题向量；另一份资料的分块必须毫发无损
    sealed_vectors.add(doc.id, ["勾股定理的分块"], [[1.0] * 8])
    sealed_vectors.add(other.id, ["别动我的分块"], [[2.0] * 8])
    sealed_vectors.add_node_title(single.id, "勾股定理", [1.0] * 8)
    sealed_vectors.add_node_title(examined.id, "被考的勾股推论", [1.0] * 8)

    r = _delete(doc.id)
    assert r.status_code == 200
    data = r.json()
    assert data["chunks_deleted"] == 1
    assert data["literature_note_deleted"] is True
    assert data["conflicts_withdrawn"] == 1
    assert {n["id"] for n in data["knowledge_deleted"]} == {single.id, examined.id}
    assert [n["id"] for n in data["knowledge_kept"]] == [multi.id]
    assert [q["id"] for q in data["questions_cleared"]] == [question_id]
    assert data["file_removed"] is True

    # 资料：行删、详情 404、磁盘文件清走
    assert _get_document(doc.id).status_code == 404
    assert not Path(doc.file_path).exists()

    # 知识点：单来源删、多来源保留且摘除本资料引用（另一来源原样）
    assert _node_by_id(single.id) is None
    assert _node_by_id(examined.id) is None
    kept = _node_by_id(multi.id)
    assert kept is not None and set(kept.source_docs or []) == {other.id}
    # 关系边随节点走：连着被删节点的边全消；保留节点之间的边不受牵连
    db = SessionLocal()
    try:
        edge_pairs = {
            (e.from_node, e.to_node)
            for e in db.scalars(select(KnowledgeEdge)).all()
        }
    finally:
        db.close()
    assert (single.id, multi.id) not in edge_pairs
    assert (single.id, other_single.id) not in edge_pairs
    assert (multi.id, other_single.id) in edge_pairs
    assert _question_knowledge_nodes(retained_question) == {multi.id}

    # 待审冲突撤下；已裁决的冲突是史实留痕，不动
    db = SessionLocal()
    try:
        assert db.get(Conflict, pending) is None
        assert db.get(Conflict, resolved) is not None
    finally:
        db.close()

    # 向量：本资料分块与被删知识点标题向量清空；另一份资料分块原样
    assert sealed_vectors.list_doc_chunks(doc.id) == (0, [])
    total, chunks = sealed_vectors.list_doc_chunks(other.id)
    assert total == 1 and chunks[0]["content"] == "别动我的分块"
    # 被删知识点的标题向量一并清走（冲突检测近名预筛不再命中幽灵节点）
    assert sealed_vectors.search_node_titles([1.0] * 8, k=10) == []

    # 题目：题目保留，考查关系置空
    db = SessionLocal()
    try:
        assert db.get(Question, question_id) is not None
    finally:
        db.close()
    assert _question_knowledge_nodes(question_id) == set()

def test_delete_single_source_knowledge_kept_clears_source_reference(sealed_vectors):
    """对话框不勾选删除：单来源知识点保留、来源引用清空、边与考查关系都保住。"""
    doc = _seed_document()
    single = _seed_node("函数单调性", [doc.id])
    neighbor = _seed_node("不受影响的知识点", [])
    _seed_edge(single.id, neighbor.id)
    _seed_note(doc.id)
    question_id = _seed_question_with_knowledge(single, "单调性怎么判？")
    sealed_vectors.add_node_title(single.id, "函数单调性", [3.0] * 8)

    r = _delete(doc.id, delete_single_source=False)
    assert r.status_code == 200
    data = r.json()
    assert data["knowledge_deleted"] == []
    assert [n["id"] for n in data["knowledge_kept"]] == [single.id]
    assert data["questions_cleared"] == []

    kept = _node_by_id(single.id)
    assert kept is not None
    assert kept.source_docs == [], "保留者清空该来源引用"
    assert sealed_vectors.search_node_titles([3.0] * 8, k=5) != []
    assert _question_knowledge_nodes(question_id) == {single.id}
    with SessionLocal() as db:
        assert db.scalar(
            select(KnowledgeEdge).where(
                KnowledgeEdge.from_node == single.id, KnowledgeEdge.to_node == neighbor.id
            )
        ) is not None


def test_delete_removes_only_target_document(sealed_vectors):
    """删除一份资料不得波及另一份资料的分块、知识点、文献笔记与待审冲突。"""
    doc = _seed_document()
    other = _seed_document(filename="无关资料.pdf")
    other_node = _seed_node("无关知识点", [other.id])
    _seed_note(other.id)
    _seed_conflict(other.id, "待审", "无关知识点")
    sealed_vectors.add(other.id, ["无关分块"], [[4.0] * 8])

    assert _delete(doc.id).status_code == 200

    assert _get_document(other.id).status_code == 200
    assert _node_by_id(other_node.id) is not None
    assert sealed_vectors.list_doc_chunks(other.id)[0] == 1
    db = SessionLocal()
    try:
        assert (
            db.scalar(select(LiteratureNote).where(LiteratureNote.doc_id == other.id))
            is not None
        )
        assert len(
            db.scalars(
                select(Conflict).where(Conflict.doc_id == other.id, Conflict.status == "待审")
            ).all()
        ) == 1
    finally:
        db.close()


# ---- 删除接口契约 ----


def test_delete_unknown_document_returns_404(sealed_vectors):
    r = _delete(str(uuid.uuid4()))
    assert r.status_code == 404
    assert "资料不存在" in r.json()["detail"]


def test_delete_rejects_unknown_request_fields():
    """请求体字段拼错是 422：对话框交代的选项之外没有隐藏开关。"""
    doc = _seed_document()
    r = client.request("DELETE", f"/api/v1/documents/{doc.id}", json={"wipe_everything": True})
    assert r.status_code == 422


def test_document_with_missing_note_and_file_still_deletes(sealed_vectors):
    """文献笔记缺席 / 文件已不在：删除照常完成，结果如实报 false。"""
    doc = _seed_document(with_file=False)
    r = _delete(doc.id)
    assert r.status_code == 200
    data = r.json()
    assert data["literature_note_deleted"] is False
    assert data["file_removed"] is False
    assert _get_document(doc.id).status_code == 404


# ---- 史实留痕：生成物历史版本不被删除牵连 ----


def test_artifact_provenance_untouched(sealed_vectors):
    doc = _seed_document()
    db = SessionLocal()
    try:
        version = ArtifactVersion(
            user_id="default",
            session_id=_seed_session_id(),
            artifact_type="教案",
            version=1,
            filename="教案 v1.docx",
            title="勾股定理教案",
            content={"provenance": f"参考了资料 {doc.filename}"},
        )
        db.add(version)
        db.commit()
        snapshot = (version.id, version.content, version.filename)
    finally:
        db.close()

    assert _delete(doc.id).status_code == 200

    db = SessionLocal()
    try:
        row = db.get(ArtifactVersion, snapshot[0])
    finally:
        db.close()
    assert row is not None
    assert row.content == snapshot[1]
    assert row.filename == snapshot[2]


def _seed_session_id() -> str:
    from app.db.models import PrepSession

    db = SessionLocal()
    try:
        session = PrepSession(user_id="default", title="未命名备课")
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id
    finally:
        db.close()


# ---- 路径规范化守卫：读写统一 POSIX 分隔符 + 幂等迁移 ----


def test_normalize_stored_path_converts_windows_separators():
    assert normalize_stored_path("data\\uploads\\a.pdf") == "data/uploads/a.pdf"
    assert normalize_stored_path("/mnt/data/uploads/a.pdf") == "/mnt/data/uploads/a.pdf"
    assert normalize_stored_path("") == ""


def test_save_upload_returns_posix_path(tmp_path, monkeypatch):
    monkeypatch.setattr("app.knowledge.storage.UPLOAD_DIR", tmp_path)
    stored = save_upload(b"bytes", "讲义.pdf")
    assert "\\" not in stored
    assert (tmp_path / Path(stored).name).read_bytes() == b"bytes"


def test_legacy_windows_file_paths_normalized_in_migration(tmp_path):
    """存量 Windows 路径在引擎迁移链里统一为 POSIX 分隔符，且幂等（票 02 清理后的防御）。"""
    db_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE documents (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36),"
        " filename VARCHAR(255), file_path VARCHAR(500), file_type VARCHAR(20))"
    )
    legacy.execute(
        "INSERT INTO documents (id, user_id, filename, file_path, file_type)"
        " VALUES ('d-win', 'default', '讲义.pdf', 'data\\uploads\\win.pdf', 'pdf')"
    )
    legacy.execute(
        "INSERT INTO documents (id, user_id, filename, file_path, file_type)"
        " VALUES ('d-posix', 'default', '笔记.pdf', 'data/uploads/posix.pdf', 'pdf')"
    )
    legacy.commit()
    legacy.close()

    legacy_engine = create_engine(f"sqlite:///{db_path}")
    try:
        _ensure_sqlite_columns(legacy_engine)
        _ensure_sqlite_columns(legacy_engine)  # 幂等：再跑一次不报错、结果不变
        with legacy_engine.connect() as conn:
            win = conn.exec_driver_sql(
                "SELECT file_path FROM documents WHERE id = 'd-win'"
            ).one()[0]
            posix = conn.exec_driver_sql(
                "SELECT file_path FROM documents WHERE id = 'd-posix'"
            ).one()[0]
        assert win == "data/uploads/win.pdf"
        assert posix == "data/uploads/posix.pdf"
    finally:
        legacy_engine.dispose()


# ---- OpenAPI 契约：删除与预览挂「知识库」tag 且注解齐全 ----


def test_delete_endpoints_declared_in_openapi():
    schema = client.get("/openapi.json").json()
    delete = schema["paths"]["/api/v1/documents/{document_id}"]["delete"]
    preview = schema["paths"]["/api/v1/documents/{document_id}/delete-preview"]["get"]
    for op in (delete, preview):
        assert op["tags"] == ["知识库"]
        assert op["summary"]
        assert op["description"]
        assert "200" in op["responses"] and "404" in op["responses"]
    assert "409" in delete["responses"]
    assert "422" in delete["responses"]
    assert delete["requestBody"]["content"]["application/json"]["schema"]


@pytest.mark.parametrize("delete_single_source", [True, False])
def test_withdraws_cross_document_conflicts_referencing_sources(
    sealed_vectors, delete_single_source
):
    doc = _seed_document()
    other = _seed_document(filename="冲突来源.pdf")
    single = _seed_node("单来源旧知识", [doc.id])
    multi = _seed_node("多来源旧知识", [doc.id, other.id])
    conflicts = []
    with SessionLocal() as db:
        for snapshot in (
            {"id": single.id},
            {"id": multi.id},
            {"source_docs": [doc.id]},
            {"doc_id": doc.id},
        ):
            conflict = Conflict(
                user_id="default", doc_id=other.id, status="待审",
                new_knowledge={"title": "新知识"}, existing_knowledge=snapshot,
            )
            db.add(conflict)
            conflicts.append(conflict)
        resolved = Conflict(
            user_id="default", doc_id=other.id, status="已接受",
            new_knowledge={"title": "已裁决知识", "source_docs": [doc.id]},
            existing_knowledge={"id": single.id},
        )
        # 新知识快照的明确资料引用也须撤下。
        new_snapshot = Conflict(
            user_id="default", doc_id=other.id, status="待审",
            new_knowledge={"title": "新知识", "source_docs": [doc.id]},
            existing_knowledge={},
        )
        db.add_all([resolved, new_snapshot])
        db.commit()
        withdrawn_ids = [c.id for c in [*conflicts, new_snapshot]]
        resolved_id = resolved.id
    assert _preview(doc.id).json()["pending_conflict_count"] == len(withdrawn_ids)
    response = _delete(doc.id, delete_single_source)
    assert response.status_code == 200
    assert response.json()["conflicts_withdrawn"] == len(withdrawn_ids)
    with SessionLocal() as db:
        assert all(db.get(Conflict, cid) is None for cid in withdrawn_ids)
        resolved_row = db.get(Conflict, resolved_id)
        assert resolved_row is not None and resolved_row.new_knowledge is not None
        assert resolved_row.new_knowledge["source_docs"] == [doc.id]
    multi_row = _node_by_id(multi.id)
    assert multi_row is not None and multi_row.source_docs == [other.id]
    assert _get_document(other.id).status_code == 200
    if not delete_single_source:
        single_row = _node_by_id(single.id)
        assert single_row is not None and single_row.source_docs == []


def test_processing_document_delete_rejected_without_side_effects(sealed_vectors):
    doc = _seed_document()
    single = _seed_node("处理中的知识点", [doc.id])
    _seed_note(doc.id)
    pending_id = _seed_conflict(doc.id, "待审", "处理中的冲突")
    sealed_vectors.add(doc.id, ["已入库分块"], [[1.0] * 8])
    with SessionLocal() as db:
        doc_row = db.get(Document, doc.id)
        assert doc_row is not None
        doc_row.status = "处理中"
        db.commit()
    response = _delete(doc.id)
    assert response.status_code == 409
    assert response.json()["detail"] == "教学资料正在处理中，暂不可删除。请等待处理结束后再试。"
    assert Path(doc.file_path).exists()
    assert sealed_vectors.list_doc_chunks(doc.id)[0] == 1
    single_row = _node_by_id(single.id)
    assert single_row is not None and single_row.source_docs == [doc.id]
    with SessionLocal() as db:
        doc_row = db.get(Document, doc.id)
        assert doc_row is not None and doc_row.status == "处理中"
        assert db.get(Conflict, pending_id) is not None
        assert db.scalar(select(LiteratureNote).where(LiteratureNote.doc_id == doc.id)) is not None


@pytest.mark.parametrize("status", ["已完成", "有冲突", "失败"])
def test_terminal_document_status_allows_delete(sealed_vectors, status):
    doc = _seed_document()
    with SessionLocal() as db:
        doc_row = db.get(Document, doc.id)
        assert doc_row is not None
        doc_row.status = status
        db.commit()
    assert _delete(doc.id).status_code == 200


def test_delete_uses_normalized_file_path(sealed_vectors):
    doc = _seed_document()
    original = Path(doc.file_path)
    with SessionLocal() as db:
        doc_row = db.get(Document, doc.id)
        assert doc_row is not None
        doc_row.file_path = doc.file_path.replace("/", "\\")
        db.commit()
    assert _delete(doc.id).json()["file_removed"] is True
    assert not original.exists()


def test_vector_delete_doc_removes_embedding_rows_and_is_idempotent(sealed_vectors):
    sealed_vectors.add("deleted", ["first", "second"], [[1.0] * 8, [2.0] * 8])
    sealed_vectors.add("retained", ["third"], [[3.0] * 8])
    assert sealed_vectors.delete_doc("deleted") == 2
    assert sealed_vectors.delete_doc("deleted") == 0
    connection = sealed_vectors._connect()
    try:
        assert connection.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1
        # 不只断言检索结果（JOIN 会藏住幽灵向量），直接确认向量行无残留。
        assert connection.execute("SELECT count(*) FROM chunk_embeddings").fetchone()[0] == 1
    finally:
        connection.close()


def test_save_upload_normalizes_directory_before_writing(tmp_path, monkeypatch):
    destination = tmp_path / "nested" / "uploads"
    windows_directory = Path(str(destination).replace("/", "\\"))
    monkeypatch.setattr("app.knowledge.storage.UPLOAD_DIR", windows_directory)
    stored = save_upload(b"original bytes", "讲义.pdf")
    assert Path(stored).parent == destination
    assert Path(stored).read_bytes() == b"original bytes"
    assert not windows_directory.exists()


def test_question_preview_deduplicates_and_only_removes_deleted_links(sealed_vectors):
    doc = _seed_document()
    first = _seed_node("题目考查的第一知识点", [doc.id])
    second = _seed_node("题目考查的第二知识点", [doc.id])
    retained = _seed_node("题目保留的知识点", [])
    question_id = _seed_question_with_knowledge(first, "一道考查多个知识点的题目")
    with SessionLocal() as db:
        for node in (second, retained):
            db.add(QuestionKnowledge(question_id=question_id, knowledge_id=node.id, weight="涉及"))
        db.commit()
    preview = _preview(doc.id).json()
    assert len(preview["affected_questions"]) == 1
    assert set(preview["affected_questions"][0]["knowledge_titles"]) == {first.title, second.title}
    # 空请求体仍按默认勾选删除单来源知识点。
    response = client.request("DELETE", f"/api/v1/documents/{doc.id}", json={})
    assert response.status_code == 200
    assert len(response.json()["questions_cleared"]) == 1
    assert _question_knowledge_nodes(question_id) == {retained.id}


def test_delete_without_configured_llm(sealed_vectors, monkeypatch):
    from app.config import settings
    from app.core.llm.factory import get_llm

    monkeypatch.setattr(settings, "llm_provider", "")
    get_llm.cache_clear()
    doc = _seed_document()
    assert _preview(doc.id).status_code == 200
    assert _delete(doc.id).status_code == 200


@pytest.mark.parametrize("status", ["有冲突", "处理中", "失败", "已完成"])
@pytest.mark.parametrize("remaining_count", [0, 1])
def test_cross_document_withdrawal_refreshes_source_detail(
    sealed_vectors, status, remaining_count
):
    deleted = _seed_document()
    retained = _seed_document(filename="保留的冲突来源.pdf")
    old = _seed_node("被引用的旧知识", [deleted.id])
    with SessionLocal() as db:
        source = db.get(Document, retained.id)
        assert source is not None
        source.status = status
        source.conflict_count = 1 + remaining_count
        db.add(Conflict(
            user_id="default", doc_id=retained.id, status="待审",
            new_knowledge={"title": "待撤下新知识"}, existing_knowledge={"id": old.id},
        ))
        db.commit()
    # 同资料其余待审不引用被删资料，必须留下；已裁决记录不计入待审数。
    for _ in range(remaining_count):
        _seed_conflict(retained.id, "待审", "不受删除影响的矛盾")
    _seed_conflict(retained.id, "已接受", "已裁决史实")
    assert _delete(deleted.id).status_code == 200
    detail = _get_document(retained.id)
    assert detail.status_code == 200
    assert detail.json()["conflict_count"] == remaining_count
    expected_status = "已完成" if status == "有冲突" and remaining_count == 0 else status
    assert detail.json()["status"] == expected_status


@pytest.mark.parametrize("path_kind", ["empty", "dot", "missing", "directory"])
def test_web_document_without_local_original_deletes(sealed_vectors, tmp_path, path_kind):
    paths = {"empty": "", "dot": ".", "missing": str(tmp_path / "gone"), "directory": str(tmp_path)}
    doc = _seed_document(with_file=False)
    single = _seed_node("网页中的知识点", [doc.id])
    _seed_note(doc.id)
    pending_id = _seed_conflict(doc.id, "待审", "网页中的矛盾")
    sealed_vectors.add(doc.id, ["网页分块"], [[1.0] * 8])
    with SessionLocal() as db:
        row = db.get(Document, doc.id)
        assert row is not None
        row.file_type = "网页"
        row.file_path = paths[path_kind]
        db.commit()
    response = _delete(doc.id)
    assert response.status_code == 200
    assert response.json()["file_removed"] is False
    assert response.json()["chunks_deleted"] == 1
    assert response.json()["literature_note_deleted"] is True
    assert _node_by_id(single.id) is None
    assert _get_document(doc.id).status_code == 404
    assert tmp_path.is_dir()
    assert sealed_vectors.list_doc_chunks(doc.id) == (0, [])
    with SessionLocal() as db:
        assert db.get(Conflict, pending_id) is None


def test_delete_api_error_examples_and_punctuation(sealed_vectors):
    schema = client.get("/openapi.json").json()
    preview = schema["paths"]["/api/v1/documents/{document_id}/delete-preview"]["get"]
    delete = schema["paths"]["/api/v1/documents/{document_id}"]["delete"]
    assert "example" in preview["responses"]["422"]["content"]["application/json"]
    document_id = "7f6e5d4c-3b2a-4918-8776-655443322110"
    for operation, response in ((preview, _preview(document_id)), (delete, _delete(document_id))):
        example = operation["responses"]["404"]["content"]["application/json"]["example"]
        assert response.status_code == 404
        assert example == response.json() == {"detail": f"资料不存在：{document_id}"}
