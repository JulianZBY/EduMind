"""上传大小上限（M4）：超过 max_upload_bytes 直接 413，不落盘、不建记录。"""

from fastapi.testclient import TestClient

import app.api.v1.documents as documents_module
from app.db import init_db
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表与默认用户存在


def test_oversize_upload_rejected(monkeypatch):
    monkeypatch.setattr(documents_module.settings, "max_upload_bytes", 8)
    files = {"file": ("big.bin", b"0123456789", "application/octet-stream")}
    r = client.post("/api/v1/documents/upload", files=files)
    assert r.status_code == 413
    assert "过大" in r.json()["detail"]


def test_under_limit_still_accepted(monkeypatch):
    """正常大小不受影响（回归：上限不能误伤）。"""

    async def fake_parse(doc_id: str) -> str:
        return "parsed"

    monkeypatch.setattr(documents_module, "parse_document", fake_parse)
    monkeypatch.setattr(documents_module.settings, "max_upload_bytes", 1024)
    files = {"file": ("small.pdf", b"hello", "application/pdf")}
    r = client.post("/api/v1/documents/upload", files=files)
    assert r.status_code == 200
    assert r.json()["status"] == "处理中"
