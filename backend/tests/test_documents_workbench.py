"""知识库工作台的 HTTP 契约测试：上传 → 解析状态落终态 / 资料详情 / 参考资料标记切换。

只断言**响应与数据变迁**（不探内部函数调用）：解析全程走 stub 能力
（`asr_provider=stub`，无任何云端 Key），因此本文件在 stub 模式下必须全绿
（见 `docs/architecture.md` 的 stub 底线）。

穷举的状态口径来自 CONTEXT.md 第 4 节：处理中 → 已完成 / 有冲突 / 失败。
"""

from fastapi.testclient import TestClient

import app.api.v1.documents as documents_module
from app.db import init_db
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在


def _upload(filename: str, content: bytes, is_reference: bool = False) -> dict:
    """上传一份资料，返回上传响应体（断言上传本身成功）。"""
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, content, "application/octet-stream")},
        data={"is_reference": "true" if is_reference else "false"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _detail(doc_id: str) -> dict:
    response = client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _listed(doc_id: str) -> dict:
    response = client.get("/api/v1/documents")
    assert response.status_code == 200, response.text
    return next(d for d in response.json()["documents"] if d["id"] == doc_id)


def test_upload_returns_processing_then_reaches_completed_without_manual_refresh():
    """上传立即返回「处理中」，后台解析结束后同一份资料已是终态「已完成」。"""
    created = _upload("lesson-recording.mp3", b"stub audio bytes")

    assert created["status"] == "处理中"  # 立即返回，不等解析
    # 上传请求返回即代表后台解析任务已跑完：再读一次就是终态，教师无需任何手动刷新动作
    assert _detail(created["id"])["status"] == "已完成"
    assert _listed(created["id"])["status"] == "已完成"


def test_parse_failure_is_reported_as_terminal_state_and_keeps_no_chunks():
    """解析失败也落终态「失败」，且不留下任何分块（教师可按原文重新上传）。"""
    created = _upload("broken-lesson.pdf", b"%PDF-1.4 not a real pdf body")

    assert created["status"] == "处理中"
    detail = _detail(created["id"])
    assert detail["status"] == "失败"
    assert detail["chunks"] == []
    assert detail["chunk_count"] == 0


def test_document_detail_exposes_status_reference_and_chunks():
    """详情页要的东西一次给全：状态、参考资料标记、冲突数、分块（含内容可回溯）。"""
    created = _upload("lecture.mp3", b"stub audio bytes")

    detail = _detail(created["id"])
    assert detail["filename"] == "lecture.mp3"
    assert detail["file_type"] == "mp3"
    assert detail["status"] == "已完成"
    assert detail["is_reference"] is False
    assert detail["conflict_count"] == 0
    assert detail["parsed_at"]  # 解析完成时间：终态才写
    assert detail["chunk_count"] == len(detail["chunks"]) >= 1
    # stub 转写器返回固定文字稿 → 分块内容与来源资料一一对应
    assert any("stub 录音转写" in chunk["content"] for chunk in detail["chunks"])
    assert [chunk["chunk_index"] for chunk in detail["chunks"]] == list(
        range(len(detail["chunks"]))
    )


def test_processing_document_is_visible_in_list_and_detail(monkeypatch):
    """解析未结束时，列表与详情都如实报「处理中」——前端轮询要观察的就是这个形态。

    这里把解析入口换成不做事（与 `test_documents.py` 同一缝），是为了让「处理中」
    这个中间态可以被稳定观察到；真实解析的速度不由本票保证。
    """

    async def noop_parse(doc_id: str) -> str:
        return ""

    monkeypatch.setattr(documents_module, "parse_document", noop_parse)
    created = _upload("still-parsing.mp3", b"stub audio bytes", is_reference=True)

    assert created["status"] == "处理中"
    assert _listed(created["id"])["status"] == "处理中"
    detail = _detail(created["id"])
    assert detail["status"] == "处理中"
    assert detail["parsed_at"] is None  # 完成时间只在落终态时写
    assert detail["chunks"] == []
    # 处理中也能切换参考资料标记（标记不依赖解析结果）
    toggled = client.patch(
        f"/api/v1/documents/{created['id']}/reference", json={"is_reference": False}
    )
    assert toggled.status_code == 200
    assert toggled.json()["is_reference"] is False


def test_unknown_document_detail_is_404():
    """不存在的资料 id：404 + 明确文案，不落 500。"""
    response = client.get("/api/v1/documents/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert "不存在" in response.json()["detail"]


def test_reference_mark_toggle_takes_effect_immediately():
    """参考资料标记切换即刻生效：切换响应、列表与详情三处口径一致。"""
    created = _upload("notes.mp3", b"stub audio bytes")
    doc_id = created["id"]
    assert created["is_reference"] is False

    marked = client.patch(f"/api/v1/documents/{doc_id}/reference", json={"is_reference": True})
    assert marked.status_code == 200, marked.text
    assert marked.json()["is_reference"] is True
    assert _listed(doc_id)["is_reference"] is True
    assert _detail(doc_id)["is_reference"] is True

    unmarked = client.patch(f"/api/v1/documents/{doc_id}/reference", json={"is_reference": False})
    assert unmarked.status_code == 200, unmarked.text
    assert unmarked.json()["is_reference"] is False
    assert _listed(doc_id)["is_reference"] is False
    assert _detail(doc_id)["is_reference"] is False


def test_reference_mark_toggle_rejects_unknown_document_and_bad_body():
    """错误码：未知资料 404；请求体缺字段 422。"""
    missing = client.patch(
        "/api/v1/documents/00000000-0000-4000-8000-000000000000/reference",
        json={"is_reference": True},
    )
    assert missing.status_code == 404

    doc_id = _upload("body-check.mp3", b"stub audio bytes")["id"]
    assert client.patch(f"/api/v1/documents/{doc_id}/reference", json={}).status_code == 422


def test_upload_and_list_expose_the_same_document_shape():
    """上传响应与列表项同形（同一份 response_model），前端不必为两处各推断一次。"""
    created = _upload("shape.mp3", b"stub audio bytes")

    assert set(created) == set(_listed(created["id"]))
