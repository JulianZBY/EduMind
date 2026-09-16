"""健康检查路由测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ping():
    r = client.get("/api/v1/ping")
    assert r.status_code == 200
    assert r.json()["message"] == "EduMind API v1"


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "EduMind"
