"""向量存储测试（假 embedding，不依赖真实 LLM）。"""

import pytest

from app.knowledge.vector_store import VectorStore


def test_add_and_search(tmp_path):
    store = VectorStore(str(tmp_path / "test.db"))
    chunks = ["计算机网络基础", "操作系统原理", "数据库系统"]
    embs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    n = store.add("doc1", chunks, embs)
    assert n == 3

    results = store.search([1.0, 0.0, 0.0], k=1)
    assert results[0]["content"] == "计算机网络基础"
    assert results[0]["doc_id"] == "doc1"
    assert results[0]["distance"] == 0.0


def test_search_returns_k_results(tmp_path):
    store = VectorStore(str(tmp_path / "test.db"))
    chunks = [f"知识点{i}" for i in range(10)]
    embs = [[1.0] + [0.0] * 7 for _ in range(10)]  # 全相同向量
    store.add("doc1", chunks, embs)
    results = store.search([1.0] + [0.0] * 7, k=4)
    assert len(results) == 4


# ---- 维度冲突（切换 embedding provider 后）人话报错 ----


def test_add_dimension_mismatch_friendly_error(tmp_path):
    store = VectorStore(str(tmp_path / "mix.db"))
    store.add("doc1", ["甲"], [[1.0, 0.0]])
    with pytest.raises(RuntimeError, match="维度"):
        store.add("doc2", ["乙"], [[1.0, 0.0, 0.0]])
    with pytest.raises(RuntimeError, match="维度"):
        store.search([1.0, 0.0, 0.0])


def test_node_title_dimension_mismatch_friendly_error(tmp_path):
    store = VectorStore(str(tmp_path / "t.db"))
    store.add_node_title("n1", "甲", [1.0, 0.0])
    with pytest.raises(RuntimeError, match="维度"):
        store.add_node_title("n2", "乙", [1.0, 0.0, 0.0])
    with pytest.raises(RuntimeError, match="维度"):
        store.search_node_titles([1.0, 0.0, 0.0, 0.0])


def test_node_title_search_ranks_by_cosine_distance(tmp_path):
    store = VectorStore(str(tmp_path / "titles.db"))
    store.add_node_title("n1", "TCP三次握手", [1.0, 0.0, 0.0, 0.0])
    store.add_node_title("n2", "UDP协议", [0.0, 1.0, 0.0, 0.0])

    hits = store.search_node_titles([0.99, 0.14, 0.0, 0.0], k=2)
    assert [h["node_id"] for h in hits] == ["n1", "n2"]
    assert hits[0]["title"] == "TCP三次握手"
    assert hits[0]["distance"] < 0.1
    assert hits[1]["distance"] > 0.8


def test_node_title_upsert_replaces_old_vector(tmp_path):
    store = VectorStore(str(tmp_path / "titles.db"))
    store.add_node_title("n1", "TCP三次握手", [1.0, 0.0, 0.0, 0.0])
    store.add_node_title("n1", "传输层概述", [0.0, 0.0, 1.0, 0.0])  # 同 node_id 幂等覆盖

    hits = store.search_node_titles([0.0, 0.0, 1.0, 0.0], k=3)
    assert hits[0]["node_id"] == "n1"
    assert hits[0]["title"] == "传输层概述"
    # 旧向量已不在索引中：查询旧向量时 n1 不再出现近距命中
    stale = store.search_node_titles([1.0, 0.0, 0.0, 0.0], k=3)
    assert all(h["distance"] > 0.5 for h in stale if h["node_id"] == "n1")


def test_node_title_remove(tmp_path):
    store = VectorStore(str(tmp_path / "titles.db"))
    store.add_node_title("n1", "TCP三次握手", [1.0, 0.0, 0.0, 0.0])
    store.remove_node_title("n1")
    assert store.search_node_titles([1.0, 0.0, 0.0, 0.0], k=3) == []
    store.remove_node_title("missing")  # 不存在时静默


def test_node_title_search_empty_store(tmp_path):
    store = VectorStore(str(tmp_path / "empty.db"))
    assert store.search_node_titles([1.0, 0.0, 0.0], k=3) == []
