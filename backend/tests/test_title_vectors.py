"""标题向量的空间隔离、幂等迁移及底层失败回滚。"""

import sqlite3

import pytest

from app.knowledge.title_vectors import title_vector_space
from app.knowledge.vector_store import TitleIndexDimensionMismatch, VectorStore
from tests.support.fakes import TitleVectorEmbedder


def test_space_filter_precedes_knn_limit_and_exclusion(tmp_path):
    store = VectorStore(str(tmp_path / "titles.db"))
    for i in range(8):
        store.add_node_title(f"foreign{i}", "外空间", [1.0, 0.0], space="foreign")
    store.add_node_title("unknown", "旧未知", [1.0, 0.0])
    store.add_node_title("self", "本条", [1.0, 0.0], space="compatible")
    store.add_node_title("compatible", "同空间", [0.9, 0.1], space="compatible")
    hits = store.search_node_titles([1.0, 0.0], k=5, space="compatible", excluded_ids=("self",))
    assert [h["node_id"] for h in hits] == ["compatible"]
    assert [h["node_id"] for h in store.search_node_titles([1.0, 0.0], k=5)] == ["unknown"]


def test_space_migration_idempotent_preserves_unknown_and_vectors(tmp_path):
    store = VectorStore(str(tmp_path / "titles.db"))
    store.add_node_title("old", "旧", [1.0, 0.0])
    conn = store._connect()
    conn.execute("ALTER TABLE node_titles DROP COLUMN space")
    before = conn.execute("SELECT rowid,embedding FROM node_title_embeddings").fetchall()
    conn.commit()
    conn.close()
    store.migrate_title_spaces()
    store.migrate_title_spaces()
    conn = store._connect()
    try:
        assert conn.execute("SELECT node_id,title,space FROM node_titles").fetchall() == [
            ("old", "旧", None)
        ]
        assert (
            conn.execute("SELECT rowid,embedding FROM node_title_embeddings").fetchall() == before
        )
    finally:
        conn.close()
    assert store.search_node_titles([1.0, 0.0], space="current") == []
    assert store.title_space_complete("current", 2) is False


def test_space_identity_changes_without_storing_url_credentials():
    e = TitleVectorEmbedder()
    e.base_url = "https://alice:secret@example.test/v1?key=secret#secret"
    space = title_vector_space(e, 8)
    e.base_url = "https://bob:other@example.test/v1?token=other"
    assert title_vector_space(e, 8) == space
    e.model = "another-model"
    assert title_vector_space(e, 8) != space
    e.model = "model-a"
    e.dimensions = 3
    assert title_vector_space(e, 8) != space
    e.dimensions = 8
    assert title_vector_space(e, 3) != space
    e.base_url = "https://another.test/v1"
    assert title_vector_space(e, 8) != space


def test_failed_upsert_rolls_back_deleted_title_and_embedding(tmp_path):
    store = VectorStore(str(tmp_path / "titles.db"))
    store.add_node_title("node", "旧", [1.0, 0.0], space="space")
    conn = store._connect()
    before = (
        conn.execute("SELECT * FROM node_titles").fetchall(),
        conn.execute("SELECT rowid,embedding FROM node_title_embeddings").fetchall(),
    )
    # 写入新标题失败时旧标题及 vec0 行已删除，两者必须随事务一起恢复。
    conn.execute(
        "CREATE TRIGGER reject_title BEFORE INSERT ON node_titles "
        "BEGIN SELECT RAISE(ABORT, '拒绝新标题'); END"
    )
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.IntegrityError):
        store.add_node_title("node", "新", [0.0, 1.0], space="space")
    conn = store._connect()
    try:
        assert (
            conn.execute("SELECT * FROM node_titles").fetchall(),
            conn.execute("SELECT rowid,embedding FROM node_title_embeddings").fetchall(),
        ) == before
    finally:
        conn.close()
    with pytest.raises(TitleIndexDimensionMismatch):
        store.add_node_title("node", "新", [1.0, 0.0, 0.0])
    store.remove_node_title("node")
    with pytest.raises(TitleIndexDimensionMismatch):
        store.check_title_dimension(3)
