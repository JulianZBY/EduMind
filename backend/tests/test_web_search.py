"""网络搜索接口测试：端点只依赖 WebSearch 接口（未配置时 503 引导，无假结果兜底）。"""

from fastapi.testclient import TestClient

import app.api.v1.knowledge as knowledge_module
from app.config import settings
from app.core.search.base import WebSearch
from app.core.search.factory import get_search
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


def test_web_search_unconfigured_returns_503_with_guidance(monkeypatch):
    """无 Key 底线：未配置时 503 + provider_not_configured + 面向教师的引导（不再返回占位假结果）。"""
    monkeypatch.setattr(settings, "search_provider", "")
    monkeypatch.setattr(settings, "bocha_api_key", "")
    get_search.cache_clear()
    r = client.post("/api/v1/knowledge/web-search", json={"query": "计算机网络", "k": 2})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "provider_not_configured"
    assert "设置" in detail["message"]
