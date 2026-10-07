"""文档上传接口测试（替身隔离，不触发真实解析）。"""

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


def _document_ids() -> set[str]:
    return {d["id"] for d in client.get("/api/v1/documents").json()["documents"]}


def test_upload_rejects_unsupported_file_type(monkeypatch):
    """不在可解析清单内的格式入口即 415：不落盘、不建记录、不交后台解析。"""
    parsed = []

    async def fake_parse(doc_id: str) -> str:
        parsed.append(doc_id)
        return "parsed"

    monkeypatch.setattr(documents_module, "parse_document", fake_parse)
    before = _document_ids()

    for name in ("tool.exe", "notes.txt", "no_extension"):
        r = client.post(
            "/api/v1/documents/upload", files={"file": (name, b"data", "application/octet-stream")}
        )
        assert r.status_code == 415, (name, r.text)
        assert "不支持的资料格式" in r.json()["detail"]
        assert "pdf" in r.json()["detail"]  # 告诉教师可以传什么

    assert _document_ids() == before
    assert parsed == []


def test_upload_rejects_empty_file(monkeypatch):
    """空文件入口即 400，不留一条注定失败的资料。"""

    async def fake_parse(doc_id: str) -> str:
        return "parsed"

    monkeypatch.setattr(documents_module, "parse_document", fake_parse)
    before = _document_ids()

    r = client.post(
        "/api/v1/documents/upload", files={"file": ("empty.pdf", b"", "application/pdf")}
    )

    assert r.status_code == 400
    assert _document_ids() == before


def test_parse_failure_records_teacher_facing_reason():
    """解析失败时资料详情带一句给教师看的原因，且不回显内部异常文本或本机路径。"""
    r = client.post(
        "/api/v1/documents/upload",
        files={"file": ("broken.pdf", b"this is not a pdf", "application/pdf")},
    )
    assert r.status_code == 200  # TestClient 在响应返回前跑完后台解析

    detail = client.get(f"/api/v1/documents/{r.json()['id']}").json()

    assert detail["status"] == "失败"
    assert "重新上传" in detail["failure_reason"]
    assert "Traceback" not in detail["failure_reason"]
    assert "uploads" not in detail["failure_reason"]
    listed = next(
        d for d in client.get("/api/v1/documents").json()["documents"] if d["id"] == detail["id"]
    )
    assert listed["failure_reason"] == detail["failure_reason"]


def test_failure_reason_keeps_provider_guidance():
    """能力未配置导致的失败沿用引导原文（指向设置页），其余异常用通用说法。"""
    from app.core.errors import ProviderNotConfigured
    from app.knowledge.pipeline import REASON_PARSE_ERROR, failure_reason_for

    guidance = "录音转写未配置：到「设置 → 能力实现」配置后再上传。"
    assert failure_reason_for(ProviderNotConfigured(guidance)) == guidance
    assert failure_reason_for(ValueError("C:/secret/path/x.pdf broken")) == REASON_PARSE_ERROR


def test_successful_parse_has_empty_failure_reason(monkeypatch):
    async def fake_parse(doc_id: str) -> str:
        return "parsed"

    monkeypatch.setattr(documents_module, "parse_document", fake_parse)
    r = client.post(
        "/api/v1/documents/upload", files={"file": ("ok.pdf", b"%PDF-1.4 x", "application/pdf")}
    )
    assert r.json()["failure_reason"] == ""
