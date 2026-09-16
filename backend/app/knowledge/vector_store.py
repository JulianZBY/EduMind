"""向量存储：sqlite-vec 封装（chunk 文本 + embedding）。

独立文件 data/vectors.db，原生 sqlite3 连接（sqlite-vec 需扩展加载），
避免与 SQLAlchemy 主库的锁冲突。每次操作独立连接，线程安全。
"""

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import sqlite_vec

# 参考文档片段的距离折扣：等效排名加权（0.5 = 同距离下优先参考文档，可反超近一倍的非参考片段）
REFERENCE_DISTANCE_FACTOR = 0.5


class VectorStore:
    def __init__(self, db_path: str = "data/vectors.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return conn

    def add(self, doc_id: str, chunks: list[str], embeddings: list[list[float]]) -> int:
        """入库 chunk + embedding，返回入库数量。"""
        if not chunks:
            return 0
        if len(chunks) != len(embeddings):
            raise ValueError("chunks 与 embeddings 数量不一致")
        conn = self._connect()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS chunks ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT, "
                "content TEXT, chunk_index INTEGER)"
            )
            dim = len(embeddings[0])
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings "
                f"USING vec0(embedding float[{dim}])"
            )
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                cur = conn.execute(
                    "INSERT INTO chunks(doc_id, content, chunk_index) VALUES (?, ?, ?)",
                    (doc_id, chunk, i),
                )
                conn.execute(
                    "INSERT INTO chunk_embeddings(rowid, embedding) VALUES (?, ?)",
                    (cur.lastrowid, json.dumps(emb)),
                )
            conn.commit()
            return len(chunks)
        finally:
            conn.close()

    def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        boost_doc_ids: Iterable[str] | None = None,
    ) -> list[dict]:
        """KNN 检索，返回 [{chunk_id, distance, doc_id, content}]。空库返回 []。

        boost_doc_ids：参考文档 id 集合。命中这些文档的片段距离按
        REFERENCE_DISTANCE_FACTOR 折扣后参与排名（等效加权置顶）；
        返回的 distance 仍为原始值。为避免加权后排序失真，候选多取 4 倍。
        """
        boost = set(boost_doc_ids) if boost_doc_ids else None
        fetch_k = k * 4 if boost else k
        conn = self._connect()
        try:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_embeddings'"
            ).fetchone()
            if not exists:
                return []
            rows = conn.execute(
                "SELECT v.rowid, v.distance, c.doc_id, c.content "
                "FROM chunk_embeddings v JOIN chunks c ON v.rowid = c.id "
                "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
                (json.dumps(query_embedding), fetch_k),
            ).fetchall()
            hits = [
                {"chunk_id": r[0], "distance": r[1], "doc_id": r[2], "content": r[3]} for r in rows
            ]
            if boost:
                # 稳定排序：同折扣键下保持原始距离序；返回原始 distance，仅排名生效
                hits.sort(
                    key=lambda h: (
                        h["distance"] * (REFERENCE_DISTANCE_FACTOR if h["doc_id"] in boost else 1.0)
                    )
                )
            return hits[:k]
        finally:
            conn.close()

    # ---- 知识点标题索引（冲突检测近名预筛用，ADR-0001，余弦距离）----

    def add_node_title(self, node_id: str, title: str, embedding: list[float]) -> None:
        """入库/更新知识点标题向量（同 node_id 幂等覆盖）。"""
        conn = self._connect()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS node_titles (node_id TEXT PRIMARY KEY, title TEXT)"
            )
            old = conn.execute(
                "SELECT rowid FROM node_titles WHERE node_id = ?", (node_id,)
            ).fetchone()
            if old:
                conn.execute("DELETE FROM node_title_embeddings WHERE rowid = ?", (old[0],))
                conn.execute("DELETE FROM node_titles WHERE node_id = ?", (node_id,))
            dim = len(embedding)
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS node_title_embeddings "
                f"USING vec0(embedding float[{dim}] distance_metric=cosine)"
            )
            cur = conn.execute(
                "INSERT INTO node_titles(node_id, title) VALUES (?, ?)", (node_id, title)
            )
            conn.execute(
                "INSERT INTO node_title_embeddings(rowid, embedding) VALUES (?, ?)",
                (cur.lastrowid, json.dumps(embedding)),
            )
            conn.commit()
        finally:
            conn.close()

    def search_node_titles(self, embedding: list[float], k: int = 5) -> list[dict]:
        """KNN 检索标题（余弦距离），返回 [{node_id, title, distance}]。空表返回 []。"""
        conn = self._connect()
        try:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='node_title_embeddings'"
            ).fetchone()
            if not exists:
                return []
            rows = conn.execute(
                "SELECT t.node_id, t.title, v.distance "
                "FROM node_title_embeddings v JOIN node_titles t ON t.rowid = v.rowid "
                "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
                (json.dumps(embedding), k),
            ).fetchall()
            return [{"node_id": r[0], "title": r[1], "distance": r[2]} for r in rows]
        finally:
            conn.close()

    def remove_node_title(self, node_id: str) -> None:
        """移除知识点标题向量（不存在时静默）。"""
        conn = self._connect()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS node_titles (node_id TEXT PRIMARY KEY, title TEXT)"
            )
            old = conn.execute(
                "SELECT rowid FROM node_titles WHERE node_id = ?", (node_id,)
            ).fetchone()
            if old:
                conn.execute("DELETE FROM node_title_embeddings WHERE rowid = ?", (old[0],))
                conn.execute("DELETE FROM node_titles WHERE node_id = ?", (node_id,))
                conn.commit()
        finally:
            conn.close()
