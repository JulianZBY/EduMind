"""文档上传接口测试（stub 隔离，不触发真实解析）。"""

from fastapi.testclient import TestClient

import app.api.v1.documents as documents_module
from app.db import init_db
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在


def test_upload_document(monkeypatch):
    async def fake_parse(doc_id: str) -> str:
        return "parsed"

    monkeypatch.setattr(documents_module, "parse_document", fake_parse)
    files = {"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")}
    r = client.post("/api/v1/documents/upload", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["filename"] == "test.pdf"
    assert data["file_type"] == "pdf"
    assert data["status"] == "处理中"
    assert data["id"]
