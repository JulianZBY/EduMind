"""对话接口测试（stub 隔离：追问 + 生成两个分支）。"""

from fastapi.testclient import TestClient

import app.api.v1.chat as chat_module
from app.core.intent import TeachingIntent
from app.main import app

client = TestClient(app)


def test_chat_clarify_when_no_topic(monkeypatch):
    async def fake_analyze(text):
        return TeachingIntent(topic="")

    monkeypatch.setattr(chat_module, "analyze_intent", fake_analyze)
    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "备课"}]})
    assert r.status_code == 200
    assert r.json()["clarifying"] is True


def test_chat_clarify_when_missing_fields(monkeypatch):
    async def fake_analyze(text):
        return TeachingIntent(topic="TCP", duration_minutes=45)  # 缺 style/objectives 等

    monkeypatch.setattr(chat_module, "analyze_intent", fake_analyze)
    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "讲TCP，45分钟"}], "granularity": "标准"},
    )
    assert r.status_code == 200
    assert r.json()["clarifying"] is True


def test_chat_generate_when_complete(monkeypatch):
    async def fake_analyze(text):
        return TeachingIntent(
            topic="TCP", duration_minutes=45, style="学术", objectives=["a"], key_points=["b"]
        )

    async def fake_orchestrate(message, reference_doc_ids=None):
        return {
            "intent": {"topic": "TCP"},
            "knowledge_hits": False,
            "ppt": {"slides": [{"title": "t", "points": []}], "path": "x"},
            "word": {"path": "y"},
            "outline": "z",
        }

    monkeypatch.setattr(chat_module, "analyze_intent", fake_analyze)
    monkeypatch.setattr(chat_module, "orchestrate", fake_orchestrate)
    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "讲TCP"}]})
    assert r.status_code == 200
    assert r.json()["artifacts"] is not None
