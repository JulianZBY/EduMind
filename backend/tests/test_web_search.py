"""网络搜索接口测试：端点只依赖 WebSearch 接口（stub 为无 Key 底线）。"""

from fastapi.testclient import TestClient

import app.api.v1.knowledge as knowledge_module
from app.config import settings
from app.core.search.base import WebSearch
from app.core.search.factory import get_search
from app.core.search.stub import STUB_MARK
from app.main import app

client = TestClient(app)


class _FakeSearch(WebSearch):
    name = "fake"

    async def search(self, query, count=5, summary=False):
        return [{"title": "结果1", "url": "https://example.com", "snippet": "摘要"}]


def test_web_search_uses_configured_impl(monkeypatch):
    """换实现只换工厂返回值：端点代码与响应结构不变。"""
    monkeypatch.setattr(knowledge_module, "get_search", lambda: _FakeSearch())
    r = client.post("/api/v1/knowledge/web-search", json={"query": "计算机网络", "k": 2})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "结果1"


def test_web_search_stub_is_bottom_line(monkeypatch):
    """无 Key 底线：默认 stub 实现同构返回占位结果（此前是直接报错）。"""
    monkeypatch.setattr(settings, "search_provider", "stub")
    get_search.cache_clear()
    r = client.post("/api/v1/knowledge/web-search", json={"query": "计算机网络", "k": 2})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 2  # k 生效
    assert all(STUB_MARK in item["title"] for item in results)
