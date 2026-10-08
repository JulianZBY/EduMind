#!/usr/bin/env python3
"""一次性清理脚本：TCP 演示数据全清（票 02，.scratch/knowledge-restructure/issues/02-demo-data-cleanup.md）。

教师已批准全删（2026-10-08）。默认 **dry-run**：只打印将删的每一行 / 每一文件清单；
真删必须显式加 `--execute`。执行前置门禁：现场计数必须与票面核实值逐一相符、
且无 prep_sessions.reference_doc_ids 指向演示资料，任何一项不符即拒绝、零副作用——
防误删，也防重复执行（清理过一次后再跑会因「全零现场」直接报无事可做）。

删除范围（与票面一一对应）：
- 主库 edumind.db：documents 3 行、knowledge_nodes 13 行、这些节点间的 knowledge_edges 10 行、
  conflicts 1 行（doc 指向演示资料的）；questions 表分毫不动；
- 向量库 data/vectors.db：上述 3 份资料的 chunks/chunk_embeddings、13 个节点的
  node_titles/node_title_embeddings；
- data/uploads/：全部 5 个文件（3 个属演示资料 + 2 个上传被拒遗留的孤儿 wav）。

真删前先用 SQLite backup API（WAL 下对在线服务安全）把两个库备份到
`data/cleanup-backup-<时间戳>/`。运行（backend 目录下）：
`uv run python scripts/cleanup_demo_data.py`          # dry-run
`uv run python scripts/cleanup_demo_data.py --execute`  # 真删
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import sqlite_vec

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
MAIN_DB = BASE_DIR / "edumind.db"
VECTORS_DB = BASE_DIR / "data" / "vectors.db"
UPLOADS_DIR = BASE_DIR / "data" / "uploads"

# 票面（2026-10-08）核实过的现场计数：门禁基准。现场与它对不上 → 拒绝执行。
EXPECTED = {
    "documents": 3,
    "knowledge_nodes": 13,
    "knowledge_edges": 10,
    "conflicts": 1,
    "chunks": 6,
    "node_titles": 13,
    "uploads_files": 5,
}


class CleanupRefused(RuntimeError):
    """门禁不过，拒绝执行（零副作用）。"""


def connect_vectors(path: str) -> sqlite3.Connection:
    """打开向量库：vec0 虚表必须加载 sqlite-vec 才能读写（同 app/knowledge/vector_store.py）。"""
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    return conn


@dataclass
class DocRow:
    id: str
    filename: str
    file_path: str
    status: str


@dataclass
class ChunkRow:
    id: int
    doc_id: str
    chunk_index: int


@dataclass
class NodeTitleRow:
    node_id: str
    title: str


@dataclass
class SessionRef:
    session_id: str
    title: str
    doc_ids: list[str]


@dataclass
class Plan:
    docs: list[DocRow] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    edge_ids: list[str] = field(default_factory=list)
    conflict_ids: list[str] = field(default_factory=list)
    chunk_rows: list[ChunkRow] = field(default_factory=list)
    node_title_rows: list[NodeTitleRow] = field(default_factory=list)
    uploads_delete: list[Path] = field(default_factory=list)
    uploads_unexpected: list[Path] = field(default_factory=list)  # 非普通文件的意外条目
    referencing_sessions: list[SessionRef] = field(default_factory=list)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (table,)
        ).fetchone()
        is not None
    )


def _refs_of(row) -> list[str]:
    try:
        value = json.loads(row[2] or "[]")
    except (TypeError, ValueError):
        value = []
    return [str(v) for v in value] if isinstance(value, list) else []


def build_plan(main: sqlite3.Connection, vec: sqlite3.Connection, uploads_dir: Path) -> Plan:
    """从两个库与上传目录读出「将删清单」；只读，不写任何东西。"""
    plan = Plan()
    plan.docs = [
        DocRow(*row)
        for row in main.execute(
            "SELECT id, filename, file_path, status FROM documents ORDER BY id"
        ).fetchall()
    ]
    doc_ids = [d.id for d in plan.docs]
    plan.node_ids = [
        row[0] for row in main.execute("SELECT id FROM knowledge_nodes ORDER BY id").fetchall()
    ]
    # IN 列表一律走 json_each(?)：SQL 固定、值全参数化，无字符串拼接进 SQL
    if plan.node_ids:
        node_marks = json.dumps(plan.node_ids)
        plan.edge_ids = [
            row[0]
            for row in main.execute(
                "SELECT id FROM knowledge_edges "
                "WHERE from_node IN (SELECT value FROM json_each(?)) "
                "OR to_node IN (SELECT value FROM json_each(?)) ORDER BY id",
                (node_marks, node_marks),
            ).fetchall()
        ]
    if doc_ids:
        doc_marks = json.dumps(doc_ids)
        plan.conflict_ids = [
            row[0]
            for row in main.execute(
                "SELECT id FROM conflicts WHERE doc_id IN "
                "(SELECT value FROM json_each(?)) ORDER BY id",
                (doc_marks,),
            ).fetchall()
        ]
        plan.chunk_rows = [
            ChunkRow(*row)
            for row in vec.execute(
                "SELECT id, doc_id, chunk_index FROM chunks WHERE doc_id IN "
                "(SELECT value FROM json_each(?)) ORDER BY id",
                (doc_marks,),
            ).fetchall()
        ] if _table_exists(vec, "chunks") else []
    if _table_exists(vec, "node_titles"):
        plan.node_title_rows = [
            NodeTitleRow(*row)
            for row in vec.execute(
                "SELECT node_id, title FROM node_titles ORDER BY node_id"
            ).fetchall()
        ]
    if uploads_dir.is_dir():
        for entry in sorted(uploads_dir.iterdir()):
            if entry.is_file():
                plan.uploads_delete.append(entry)
            else:
                plan.uploads_unexpected.append(entry)
    doc_id_set = set(doc_ids)
    for row in main.execute(
        "SELECT id, title, reference_doc_ids FROM prep_sessions ORDER BY id"
    ).fetchall():
        refs = _refs_of(row)
        hit = sorted(doc_id_set.intersection(refs))
        if hit:
            plan.referencing_sessions.append(SessionRef(row[0], row[1], hit))
    return plan


def _counts(main: sqlite3.Connection, vec: sqlite3.Connection, uploads_dir: Path) -> dict[str, int]:
    def one(conn: sqlite3.Connection, sql: str) -> int:
        return conn.execute(sql).fetchone()[0] if _table_exists(conn, _table_of(sql)) else 0

    return {
        "documents": one(main, "SELECT COUNT(*) FROM documents"),
        "knowledge_nodes": one(main, "SELECT COUNT(*) FROM knowledge_nodes"),
        "knowledge_edges": one(main, "SELECT COUNT(*) FROM knowledge_edges"),
        "conflicts": one(main, "SELECT COUNT(*) FROM conflicts"),
        "chunks": one(vec, "SELECT COUNT(*) FROM chunks"),
        "node_titles": one(vec, "SELECT COUNT(*) FROM node_titles"),
        "uploads_files": len([p for p in uploads_dir.iterdir() if p.is_file()])
        if uploads_dir.is_dir()
        else 0,
    }


def _table_of(sql: str) -> str:
    return sql.split("FROM", 1)[1].strip().split()[0]


def find_gate_problems(main: sqlite3.Connection, plan: Plan) -> list[str]:
    """门禁：现场与票面核实值逐项对账；每处不符输出一条人话问题。"""
    problems: list[str] = []
    actual = plan_actual_counts(main, plan)
    for key, expected in EXPECTED.items():
        if actual[key] != expected:
            problems.append(f"{key}: 票面核实 {expected} 行/个,现场 {actual[key]},对不上")
    for unexpected in plan.uploads_unexpected:
        problems.append(f"uploads 目录出现非文件条目 {unexpected.name},不在票面范围内")
    for ref in plan.referencing_sessions:
        problems.append(
            f"reference_doc_ids: 备课会话「{ref.title}」({ref.session_id}) 仍引用演示资料 "
            f"{','.join(ref.doc_ids)}——票面要求先报告再处理,拒绝执行"
        )
    return problems


def plan_actual_counts(main: sqlite3.Connection, plan: Plan) -> dict[str, int]:
    """计划里的数量（与 EXPECTED 同键位），供门禁与清单打印共用。"""
    return {
        "documents": len(plan.docs),
        "knowledge_nodes": len(plan.node_ids),
        "knowledge_edges": len(plan.edge_ids),
        "conflicts": len(plan.conflict_ids),
        "chunks": len(plan.chunk_rows),
        "node_titles": len(plan.node_title_rows),
        "uploads_files": len(plan.uploads_delete),
    }


def already_clean(main: sqlite3.Connection, vec: sqlite3.Connection, uploads_dir: Path) -> bool:
    counts = _counts(main, vec, uploads_dir)
    return all(v == 0 for v in counts.values())


def print_plan(plan: Plan) -> None:
    print("== 将删清单（dry-run）==")
    print(f"-- documents ({len(plan.docs)}) --")
    for d in plan.docs:
        print(f"  {d.id}  {d.filename}  [{d.status}]  {d.file_path}")
    print(f"-- knowledge_nodes ({len(plan.node_ids)}) --")
    for row in plan.node_title_rows:
        print(f"  {row.node_id}  {row.title}")
    print(f"-- knowledge_edges ({len(plan.edge_ids)}) --")
    for edge_id in plan.edge_ids:
        print(f"  {edge_id}")
    print(f"-- conflicts ({len(plan.conflict_ids)}) --")
    for conflict_id in plan.conflict_ids:
        print(f"  {conflict_id}")
    print(f"-- vectors.chunks ({len(plan.chunk_rows)}) --")
    for c in plan.chunk_rows:
        print(f"  chunk {c.id}  doc={c.doc_id}  index={c.chunk_index}")
    print(f"-- vectors.node_titles ({len(plan.node_title_rows)}) --")
    for row in plan.node_title_rows:
        print(f"  {row.node_id}  {row.title}")
    print(f"-- data/uploads ({len(plan.uploads_delete)}) --")
    for path in plan.uploads_delete:
        print(f"  {path.name}")
    if plan.referencing_sessions:
        print("-- 仍引用演示资料的备课会话（门禁）--")
        for ref in plan.referencing_sessions:
            print(f"  {ref.session_id}  {ref.title}  {','.join(ref.doc_ids)}")


def dry_run(main: sqlite3.Connection, vec: sqlite3.Connection, uploads_dir: Path) -> int:
    if already_clean(main, vec, uploads_dir):
        print("现场全零：演示数据已清理过，无事可做。")
        return 0
    plan = build_plan(main, vec, uploads_dir)
    print_plan(plan)
    problems = find_gate_problems(main, plan)
    if problems:
        print("\n== 门禁不过（拒绝执行）==")
        for p in problems:
            print(f"  ✗ {p}")
        return 2
    print("\n门禁通过：现场与票面核实值逐项相符。加 --execute 真删。")
    return 0


def backup_dbs(main_path: Path, vec_path: Path, backup_dir: Path) -> None:
    """SQLite backup API 备份两个库：在线 WAL 服务下安全（不要求先停写）。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    for src_path in (main_path, vec_path):
        src = sqlite3.connect(src_path)
        try:
            dst = sqlite3.connect(backup_dir / src_path.name)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    print(f"备份完成：{backup_dir}")


def execute_cleanup(
    main: sqlite3.Connection,
    vec: sqlite3.Connection,
    main_path: Path,
    vec_path: Path,
    uploads_dir: Path,
    backup_dir: Path,
) -> None:
    if already_clean(main, vec, uploads_dir):
        raise CleanupRefused("现场全零：演示数据已清理过，拒绝重复执行。")
    plan = build_plan(main, vec, uploads_dir)
    problems = find_gate_problems(main, plan)
    if problems:
        detail = "\n".join(f"  ✗ {p}" for p in problems)
        raise CleanupRefused(f"门禁不过，拒绝执行（零副作用）：\n{detail}")

    questions_before = main.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    backup_dbs(main_path, vec_path, backup_dir)

    # 主库：边 → 节点 → 冲突 → 资料，一条事务；questions 不在删除范围
    doc_ids = [d.id for d in plan.docs]
    node_marks = json.dumps(plan.node_ids)
    doc_marks = json.dumps(doc_ids)
    edge_marks = json.dumps(plan.edge_ids)
    conflict_marks = json.dumps(plan.conflict_ids)
    main.execute("BEGIN")
    if plan.edge_ids:
        main.execute(
            "DELETE FROM knowledge_edges WHERE id IN (SELECT value FROM json_each(?))",
            (edge_marks,),
        )
    if plan.node_ids:
        main.execute(
            "DELETE FROM knowledge_nodes WHERE id IN (SELECT value FROM json_each(?))",
            (node_marks,),
        )
    if plan.conflict_ids:
        main.execute(
            "DELETE FROM conflicts WHERE id IN (SELECT value FROM json_each(?))",
            (conflict_marks,),
        )
    if doc_ids:
        main.execute(
            "DELETE FROM documents WHERE id IN (SELECT value FROM json_each(?))",
            (doc_marks,),
        )
    main.commit()

    # 向量库：chunk 向量随 chunk 行删（vec0 虚表以 rowid 对应 chunks.id），节点标题同理
    doc_marks = json.dumps([d.id for d in plan.docs])
    title_marks = json.dumps([row.node_id for row in plan.node_title_rows])
    vec.execute("BEGIN")
    if plan.chunk_rows:
        vec.execute(
            "DELETE FROM chunk_embeddings WHERE rowid IN "
            "(SELECT id FROM chunks WHERE doc_id IN (SELECT value FROM json_each(?)))",
            (doc_marks,),
        )
        vec.execute(
            "DELETE FROM chunks WHERE doc_id IN (SELECT value FROM json_each(?))",
            (doc_marks,),
        )
    if plan.node_title_rows:
        vec.execute(
            "DELETE FROM node_title_embeddings WHERE rowid IN "
            "(SELECT rowid FROM node_titles WHERE node_id IN (SELECT value FROM json_each(?)))",
            (title_marks,),
        )
        vec.execute(
            "DELETE FROM node_titles WHERE node_id IN (SELECT value FROM json_each(?))",
            (title_marks,),
        )
    vec.commit()

    for path in plan.uploads_delete:
        path.unlink()

    # 删后自证：六个面全空、questions 分毫未动
    counts = _counts(main, vec, uploads_dir)
    questions_after = main.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if any(counts.values()) or questions_after != questions_before:
        raise RuntimeError(
            f"删除后自证失败：{counts}（期望全零）,questions {questions_before}→{questions_after}。"
            f"请从备份恢复：{backup_dir}"
        )
    print("删除完成，删后自证通过：六个面全零，questions 未动。")
    print("  documents/knowledge_nodes/knowledge_edges/conflicts/chunks/node_titles/uploads = 0")
    print(f"  questions 保持 {questions_after} 行")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="票 02：TCP 演示数据清理（默认 dry-run）")
    parser.add_argument("--execute", action="store_true", help="真删（默认只 dry-run）")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="显式声明 dry-run（默认即 dry-run，此旗标不改变行为，便于脚本化留痕）",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help=f"备份目录（默认 {VECTORS_DB.parent}/cleanup-backup-<时间戳>）",
    )
    args = parser.parse_args(argv)

    print(f"主库：{MAIN_DB}")
    print(f"向量库：{VECTORS_DB}")
    print(f"上传目录：{UPLOADS_DIR}")
    main_conn = sqlite3.connect(MAIN_DB)
    vec_conn = connect_vectors(str(VECTORS_DB))
    try:
        if not args.execute:
            return dry_run(main_conn, vec_conn, UPLOADS_DIR)
        backup_target = args.backup_dir or (
            VECTORS_DB.parent / f"cleanup-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        )
        execute_cleanup(main_conn, vec_conn, MAIN_DB, VECTORS_DB, UPLOADS_DIR, backup_target)
        return 0
    finally:
        main_conn.close()
        vec_conn.close()


if __name__ == "__main__":
    sys.exit(main())
