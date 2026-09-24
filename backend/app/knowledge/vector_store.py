"""向量存储：sqlite-vec 封装（chunk 文本 + embedding）。

独立文件 data/vectors.db，原生 sqlite3 连接（sqlite-vec 需扩展加载），
避免与 SQLAlchemy 主库的锁冲突。每次操作独立连接，线程安全。
"""

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import sqlite_vec

from app.config import settings

# 参考文档片段的距离折扣：等效排名加权（0.5 = 同距离下优先参考文档，可反超近一倍的非参考片段）
REFERENCE_DISTANCE_FACTOR = 0.5


def _dim_mismatch(path: str, exc: sqlite3.OperationalError) -> None:
    """维度冲突转译为人话：切换 embedding provider 后新旧向量维度不一致。"""
    raise RuntimeError(
        f"向量维度与已有索引不一致（{exc}）：疑似切换过 embedding provider，"
        f"删除 {path} 重建索引即可"
    ) from exc


class VectorStore:
    def __init__(self, db_path: str | None = None):
        # 未显式指定时读配置：测试通过 VECTORS_DB_PATH 环境变量隔离，不污染开发库
        self.db_path = db_path or settings.vectors_db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

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
        except sqlite3.OperationalError as e:
            if "Dimension mismatch" in str(e):
                _dim_mismatch(self.db_path, e)
            raise
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
        except sqlite3.OperationalError as e:
            if "Dimension mismatch" in str(e):
                _dim_mismatch(self.db_path, e)
            raise
        finally:
            conn.close()

    def list_doc_chunks(self, doc_id: str, limit: int = 200) -> tuple[int, list[dict]]:
        """按次序取某份资料的分块：返回 (分块总数, 至多 limit 条分块)。

        知识库详情的只读入口：`chunk_index` 是分块在原文中的次序，`chunk_id` 是全局唯一
        编号（检索命中与来源引用都用它回溯）。`limit` 只截断返回条数，总数照实回；
        空库 / 该资料无分块时返回 `(0, [])`，不抛错。
        """
        conn = self._connect()
        try:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'"
            ).fetchone()
            if not exists:
                return 0, []
            total = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT id, chunk_index, content FROM chunks WHERE doc_id = ? "
                "ORDER BY chunk_index LIMIT ?",
                (doc_id, limit),
            ).fetchall()
            return total, [
                {"chunk_id": r[0], "chunk_index": int(r[1] or 0), "content": r[2]} for r in rows
            ]
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
        except sqlite3.OperationalError as e:
            if "Dimension mismatch" in str(e):
                _dim_mismatch(self.db_path, e)
            raise
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
        except sqlite3.OperationalError as e:
            if "Dimension mismatch" in str(e):
                _dim_mismatch(self.db_path, e)
            raise
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
