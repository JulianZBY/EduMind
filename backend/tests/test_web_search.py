"""网络搜索接口测试（stub 隔离）。"""

from fastapi.testclient import TestClient

import app.api.v1.knowledge as knowledge_module
from app.main import app

client = TestClient(app)


class _FakeSearch:
    async def search(self, query, count=5, summary=False):
        return [{"title": "结果1", "url": "https://example.com", "snippet": "摘要"}]


def test_web_search(monkeypatch):
    monkeypatch.setattr(knowledge_module, "BochaSearchClient", lambda: _FakeSearch())
    r = client.post("/api/v1/knowledge/web-search", json={"query": "计算机网络", "k": 2})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "结果1"
