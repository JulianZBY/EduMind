"""票 02 一次性清理脚本的测试（.scratch/knowledge-restructure/issues/02-demo-data-cleanup.md）。

脚本不是产品代码、不改行为：这里只测它的计划构建 / 门禁 / 删除范围——
用临时库 + 真实 VectorStore（sqlite-vec，本地扩展，离线确定性）复刻票面核实过的现场，
断言「删的恰好是演示数据、questions 与备份分毫不动、门禁对不上就拒绝」。
"""


import importlib.util
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.knowledge.vector_store import VectorStore

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 先注册进 sys.modules：3.14 的 dataclasses 解析注解时要按 __module__ 回查模块对象
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def demo_script():
    return _load_script("cleanup_demo_data")


MAIN_DDL = """
CREATE TABLE documents (id TEXT PRIMARY KEY, filename TEXT, file_path TEXT, status TEXT);
CREATE TABLE knowledge_nodes (id TEXT PRIMARY KEY, title TEXT, source_docs TEXT);
CREATE TABLE knowledge_edges (id TEXT PRIMARY KEY, from_node TEXT, to_node TEXT, relation_type TEXT);
CREATE TABLE conflicts (id TEXT PRIMARY KEY, doc_id TEXT, category TEXT, status TEXT);
CREATE TABLE prep_sessions (id TEXT PRIMARY KEY, title TEXT, reference_doc_ids TEXT);
CREATE TABLE questions (id TEXT PRIMARY KEY, content TEXT);
"""

DOC_IDS = [
    "7679299b-a74b-42f4-b695-0eb58d89d4fb",
    "a181d7d2-61a7-4795-aee6-02190f43478b",
    "9eb4e0bc-c76c-441d-aebc-6c6b7f4ac922",
]
DOC_FILES = [
    "fa279bb0951049d8b694e5b80c448591.docx",
    "7c36ae678f0d4a39bf677c03373ab5f7.png",
    "f706cf9744aa4bbb95b683e274776b01.docx",
]
ORPHAN_WAVS = [
    "84832801101040fc8f851017a0445daa.wav",
    "e148cc887b0641e99ba302fede968b4f.wav",
]
NODE_IDS = [f"node-{i:02d}" for i in range(1, 14)]
ALL_UPLOAD_FILES = [*DOC_FILES, *ORPHAN_WAVS]


def _make_main_db(path: Path, *, reference_doc_ids: list | None = None, extra_doc: bool = False):
    conn = sqlite3.connect(path)
    conn.executescript(MAIN_DDL)
    for doc_id, filename in zip(DOC_IDS, DOC_FILES, strict=True):
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?)",
            (doc_id, filename, f"data\\uploads\\{filename}", "已完成"),
        )
    if extra_doc:
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?)",
            ("kept-doc", "留下的资料.pdf", "data/uploads/kept.pdf", "已完成"),
        )
    for i, node_id in enumerate(NODE_IDS):
        conn.execute(
            "INSERT INTO knowledge_nodes VALUES (?, ?, ?)",
            (node_id, f"TCP 知识点 {i}", json.dumps([DOC_IDS[i % 3]])),
        )
    for i in range(10):
        conn.execute(
            "INSERT INTO knowledge_edges VALUES (?, ?, ?, ?)",
            (f"edge-{i:02d}", NODE_IDS[i], NODE_IDS[(i + 1) % 13], "相关关联"),
        )
    conn.execute(
        "INSERT INTO conflicts VALUES (?, ?, ?, ?)",
        ("conflict-01", DOC_IDS[2], "定义冲突", "并存"),
    )
    conn.execute("INSERT INTO prep_sessions VALUES (?, ?, ?)", ("s1", "讲一次函数", "[]"))
    conn.execute(
        "INSERT INTO prep_sessions VALUES (?, ?, ?)",
        ("s2", "引用演示资料的会话", json.dumps(reference_doc_ids or [])),
    )
    conn.execute("INSERT INTO questions VALUES (?, ?)", ("q1", "题一"))
    conn.execute("INSERT INTO questions VALUES (?, ?)", ("q2", "题二"))
    conn.commit()
    return conn


def _make_vectors(path: Path) -> VectorStore:
    store = VectorStore(db_path=str(path))
    store.add(DOC_IDS[0], ["握手分块"], [[1.0, 0.0]])
    store.add(DOC_IDS[1], [f"板书分块 {i}" for i in range(4)], [[1.0, 0.0]] * 4)
    store.add(DOC_IDS[2], ["修订分块"], [[0.0, 1.0]])
    for i, node_id in enumerate(NODE_IDS):
        store.add_node_title(node_id, f"TCP 知识点 {i}", [float(i), 1.0])
    return store


def _make_uploads(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name in ALL_UPLOAD_FILES:
        (path / name).write_bytes(b"demo")


@dataclass
class Scene:
    main_db: Path
    vectors_db: Path
    uploads: Path
    main: sqlite3.Connection


@pytest.fixture()
def scene(tmp_path):
    main_db = tmp_path / "edumind.db"
    vectors_db = tmp_path / "vectors.db"
    uploads = tmp_path / "uploads"
    _make_main_db(main_db)
    _make_vectors(vectors_db)
    _make_uploads(uploads)
    yield Scene(main_db, vectors_db, uploads, sqlite3.connect(main_db))


def _vec_conn(demo_script, vectors_db: Path) -> sqlite3.Connection:
    return demo_script.connect_vectors(str(vectors_db))


# ---- 门禁：现场计数与票面核实值对不上就拒绝 ----


def test_gate_blocks_when_document_count_mismatch(demo_script, tmp_path):
    main_db = tmp_path / "edumind.db"
    main = _make_main_db(main_db, extra_doc=True)
    plan = demo_script.build_plan(
        main, _vec_conn(demo_script, tmp_path / "vectors.db"), tmp_path / "uploads"
    )
    problems = demo_script.find_gate_problems(main, plan)
    assert any("documents" in p for p in problems)
    main.close()


def test_gate_blocks_when_prep_session_references_demo_doc(demo_script, tmp_path):
    main_db = tmp_path / "edumind.db"
    main = _make_main_db(main_db, reference_doc_ids=[DOC_IDS[0]])
    plan = demo_script.build_plan(
        main, _vec_conn(demo_script, tmp_path / "vectors.db"), tmp_path / "uploads"
    )
    problems = demo_script.find_gate_problems(main, plan)
    assert any("reference_doc_ids" in p for p in problems)
    assert any(DOC_IDS[0] in p for p in problems)
    main.close()


# ---- 计划：清单与票面逐项对账 ----


def test_build_plan_lists_exact_ticket_inventory(demo_script, scene):
    plan = demo_script.build_plan(
        scene.main, _vec_conn(demo_script, scene.vectors_db), scene.uploads
    )
    assert sorted(d.id for d in plan.docs) == sorted(DOC_IDS)
    assert sorted(plan.node_ids) == sorted(NODE_IDS)
    assert len(plan.edge_ids) == 10
    assert len(plan.conflict_ids) == 1
    assert len(plan.chunk_rows) == 6
    assert sorted(row.node_id for row in plan.node_title_rows) == sorted(NODE_IDS)
    assert sorted(f.name for f in plan.uploads_delete) == sorted(ALL_UPLOAD_FILES)


# ---- dry-run：只出清单，不落任何写 ----


def test_dry_run_changes_nothing(demo_script, scene, capsys):
    vec = _vec_conn(demo_script, scene.vectors_db)
    code = demo_script.dry_run(scene.main, vec, scene.uploads)
    assert code == 0
    assert scene.main.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3
    assert scene.main.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 2
    assert vec.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 6
    assert sorted(p.name for p in scene.uploads.iterdir()) == sorted(ALL_UPLOAD_FILES)
    out = capsys.readouterr().out
    assert DOC_FILES[0] in out and ORPHAN_WAVS[0] in out


def test_dry_run_on_already_clean_library_reports_noop(demo_script, scene, tmp_path, capsys):
    vec = _vec_conn(demo_script, scene.vectors_db)
    demo_script.execute_cleanup(
        scene.main, vec, scene.main_db, scene.vectors_db, scene.uploads, tmp_path / "backup"
    )
    capsys.readouterr()
    code = demo_script.dry_run(scene.main, vec, scene.uploads)
    assert code == 0
    assert "已清理" in capsys.readouterr().out


# ---- 真删：范围恰为演示数据，questions 不动，备份可查 ----


def test_execute_deletes_demo_scope_and_keeps_questions(demo_script, scene, tmp_path):
    vec = _vec_conn(demo_script, scene.vectors_db)
    backup_dir = tmp_path / "backup"
    demo_script.execute_cleanup(
        scene.main, vec, scene.main_db, scene.vectors_db, scene.uploads, backup_dir
    )

    assert scene.main.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
    assert scene.main.execute("SELECT COUNT(*) FROM knowledge_nodes").fetchone()[0] == 0
    assert scene.main.execute("SELECT COUNT(*) FROM knowledge_edges").fetchone()[0] == 0
    assert scene.main.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0] == 0
    assert scene.main.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 2
    assert vec.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
    assert vec.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 0
    assert vec.execute("SELECT COUNT(*) FROM node_titles").fetchone()[0] == 0
    assert vec.execute("SELECT COUNT(*) FROM node_title_embeddings").fetchone()[0] == 0
    assert list(scene.uploads.iterdir()) == []

    # 备份：删前状态可回溯
    bak = sqlite3.connect(backup_dir / scene.main_db.name)
    assert bak.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3
    bak.close()
    bak_vec = _vec_conn(demo_script, backup_dir / scene.vectors_db.name)
    assert bak_vec.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 6
    bak_vec.close()


def test_execute_refuses_second_run(demo_script, scene, tmp_path):
    vec = _vec_conn(demo_script, scene.vectors_db)
    demo_script.execute_cleanup(
        scene.main, vec, scene.main_db, scene.vectors_db, scene.uploads, tmp_path / "backup"
    )
    with pytest.raises(demo_script.CleanupRefused):
        demo_script.execute_cleanup(
            scene.main, vec, scene.main_db, scene.vectors_db, scene.uploads, tmp_path / "backup2"
        )


def test_execute_refuses_when_gate_fails(demo_script, tmp_path):
    main_db = tmp_path / "edumind.db"
    main = _make_main_db(main_db, reference_doc_ids=[DOC_IDS[0]])
    vec = _vec_conn(demo_script, tmp_path / "vectors.db")
    uploads = tmp_path / "uploads"
    _make_uploads(uploads)
    with pytest.raises(demo_script.CleanupRefused):
        demo_script.execute_cleanup(
            main, vec, main_db, tmp_path / "vectors.db", uploads, tmp_path / "backup"
        )
    # 拒绝即零副作用
    assert main.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 3
    assert sorted(p.name for p in uploads.iterdir()) == sorted(ALL_UPLOAD_FILES)
    main.close()
