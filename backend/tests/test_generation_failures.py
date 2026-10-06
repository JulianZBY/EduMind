"""生成失败显式化（H1）与启动清扫（H2）的回归测试。

产品原则：不返回「看起来像真结果的占位内容」。生成失败必须被教师看见并可重试，
而不是落一份空课件 / 空教案冒充成功；进程重启后残留的「处理中」资料必须被清扫，
否则前端会永远轮询。

失败注入打在最靠近用户的那条接缝上（`orchestrator` 里被导入的生成器），
其余三路走替身的正常输出，从而验证「单路失败不再被静默吞掉」。
"""

import pytest
from fastapi.testclient import TestClient

import app.core.orchestrator as orchestrator_module
from app.core.errors import ProviderNotConfigured
from app.db import SessionLocal, init_db
from app.db.models import ArtifactVersion, Document, SessionMessage
from app.knowledge.pipeline import fail_stuck_documents
from app.main import app

client = TestClient(app)
init_db()  # 幂等：会话 / 生成物 / 资料表在临时库里就位


@pytest.fixture(autouse=True)
def _isolated_outputs(isolated_output_dir):
    """本模块可能落盘：重定向到临时目录（不写 backend/data/output）。"""
    return isolated_output_dir


# 一句话同时满足「标准」粒度要确认的四个要素，直达生成阶段（不触发追问）
UTTERANCE = "给初二讲一次函数，40 分钟，风格是情境导入"
LEARNED = {
    UTTERANCE: {
        "topic": "一次函数",
        "grade": "初二",
        "duration_minutes": 40,
        "style": "情境导入",
        "objectives": ["理解一次函数的图象"],
        "key_points": ["斜率与图象"],
    }
}


def _chat(**payload):
    return client.post("/api/v1/chat", json=payload)


def test_core_generation_failure_is_explicit_not_empty_success(monkeypatch, install_semantic_llm):
    """任一路核心生成失败 → 502 generation_failed，而不是 200 + 空课件冒充成功。"""
    install_semantic_llm(learned=LEARNED)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("模型返回了无法解析的内容")

    monkeypatch.setattr(orchestrator_module, "generate_ppt_structure", boom)
    r = _chat(messages=[{"role": "user", "content": UTTERANCE}])

    assert r.status_code == 502, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "generation_failed"
    assert "课件" in detail["message"]


def test_unconfigured_provider_during_generation_keeps_503_semantics(
    monkeypatch, install_semantic_llm
):
    """生成阶段才发现未配置 → 仍走 503 引导（设置页），不降级为普通生成失败。"""
    install_semantic_llm(learned=LEARNED)

    async def nope(*_args, **_kwargs):
        raise ProviderNotConfigured("对话模型未配置：请到「设置」页配置供应商与 Key。")

    monkeypatch.setattr(orchestrator_module, "generate_word_structure", nope)
    r = _chat(messages=[{"role": "user", "content": UTTERANCE}])

    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "provider_not_configured"
    assert "设置" in detail["message"]


def test_failed_turn_leaves_no_trace_in_transcript(monkeypatch, install_semantic_llm):
    """会话模式生成失败：不落版本记录、不追加助手消息，也不留下未作答的教师消息。

    前端在发送失败时会回滚乐观气泡并让教师重发；服务端若留着这条，重发成功后
    同一句话会出现两条。本轮失败在库里同样不留痕。
    """
    install_semantic_llm(learned=LEARNED)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("模型挂了")

    monkeypatch.setattr(orchestrator_module, "generate_outline", boom)
    created = client.post("/api/v1/sessions", json={}).json()
    r = _chat(session_id=created["id"], messages=[{"role": "user", "content": UTTERANCE}])

    assert r.status_code == 502, r.text
    db = SessionLocal()
    try:
        versions = (
            db.query(ArtifactVersion)
            .filter(ArtifactVersion.session_id == created["id"])
            .count()
        )
        roles = [
            m.role
            for m in db.query(SessionMessage)
            .filter(SessionMessage.session_id == created["id"])
            .all()
        ]
    finally:
        db.close()
    assert versions == 0
    assert roles == []


    # 失败后重发：库里只应有一对（教师 + 助手），不是两条一样的教师消息
    monkeypatch.undo()
    again = _chat(session_id=created["id"], messages=[{"role": "user", "content": UTTERANCE}])
    assert again.status_code == 200, again.text

    db = SessionLocal()
    try:
        roles = [
            m.role
            for m in db.query(SessionMessage)
            .filter(SessionMessage.session_id == created["id"])
            .order_by(SessionMessage.seq)
            .all()
        ]
    finally:
        db.close()
    assert roles == ["user", "assistant"]


def test_successful_turn_still_produces_artifacts(install_semantic_llm):
    """回归：失败显式化不误伤正常路径——正常一轮备课仍返回课件 slides 并落版本记录。"""
    install_semantic_llm(learned=LEARNED)
    created = client.post("/api/v1/sessions", json={}).json()
    r = _chat(session_id=created["id"], messages=[{"role": "user", "content": UTTERANCE}])

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["clarifying"] is False
    assert body["artifacts"]["ppt"]["slides"]


def test_stuck_processing_documents_are_failed_on_startup():
    """启动清扫：残留的「处理中」资料被标记为「失败」，不再永久卡在「处理中」。"""
    db = SessionLocal()
    try:
        doc = Document(
            user_id="default",
            filename="stuck.pdf",
            file_path="data/uploads/stuck.pdf",
            file_type="pdf",
            status="处理中",
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    assert fail_stuck_documents() >= 1

    db = SessionLocal()
    try:
        assert db.get(Document, doc_id).status == "失败"
    finally:
        db.close()


def test_lifespan_startup_sweeps_stuck_documents():
    """接线验证：应用启动（lifespan）确实执行清扫，而不只是函数本身可用。"""
    db = SessionLocal()
    try:
        doc = Document(
            user_id="default",
            filename="stuck-on-boot.pdf",
            file_path="data/uploads/stuck-on-boot.pdf",
            file_type="pdf",
            status="处理中",
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    with TestClient(app):
        pass  # 进入即触发 lifespan：init_db() + fail_stuck_documents()

    db = SessionLocal()
    try:
        assert db.get(Document, doc_id).status == "失败"
    finally:
        db.close()
