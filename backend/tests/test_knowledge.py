"""知识检索接口测试（stub + 预置向量库，不触真实 LLM）。"""

from fastapi.testclient import TestClient

import app.api.v1.knowledge as knowledge_module
from app.core.embedding.stub import StubEmbedder
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)


def test_search(monkeypatch, tmp_path):
    store = VectorStore(str(tmp_path / "v.db"))
    store.add("doc1", ["计算机网络基础内容"], [[1.0] * 8])

    # 检索只依赖 Embedder 接口（不再依赖对话 provider）
    monkeypatch.setattr(knowledge_module, "get_embedder", lambda: StubEmbedder())
    monkeypatch.setattr(knowledge_module, "VectorStore", lambda: store)

    r = client.post("/api/v1/knowledge/search", json={"query": "计算机网络", "k": 1})
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert len(hits) == 1
    assert hits[0]["content"] == "计算机网络基础内容"
