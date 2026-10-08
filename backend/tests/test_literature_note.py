"""文献笔记契约测试（CONTEXT.md「文献笔记」，ADR-0007）：入库管道生成 + 资料详情呈现。

口径（票 06）：
- 解析完成后自动生成文献笔记（资料概要 + 由该资料提取的知识点索引），与教学资料 1:1；
- 对话模型未配置时：分块与解析照常入库，文献笔记不生成——详情如实报「未配置」，
  不返回假摘要（AGENTS.md 铁律：产品里没有假数据兜底）。

离线确定性：对话 / 转写替身只在 tests/support（AGENTS.md 铁律），向量化走本地 hash 兜底。
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.knowledge.graph import nodes_for_docs
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在

# 唯一正文前缀：替身提取的知识点标题来自正文首行，正文唯一才能避免与同场测试
# 早已入库的同名知识点相撞（同名去重会把节点留在库外，索引随之为空）。
_UNIQUE = uuid4().hex[:8]
# 多段正文：分块出多块，替身按行提取出多个知识点，索引与分块都有内容可断言。
_TRANSCRIPT = "\n\n".join(
    [
        f"{_UNIQUE} 勾股定理：直角三角形两直角边的平方和等于斜边的平方。",
        f"{_UNIQUE} 勾股定理的常见证明依赖面积拼接与相似三角形。",
        f"{_UNIQUE} 应用勾股定理可以在已知两边时求出直角三角形的第三边。",
    ]
)


@pytest.fixture(autouse=True)
def _fake_transcriber(monkeypatch):
    """录音解析挂替身转写器：本文件的上传用例离线跑通完整入库管道。"""
    import app.core.asr.factory as asr_factory_module
    import app.knowledge.parsers.audio as audio_module
    from tests.support.fakes import FakeTranscriber

    transcriber = FakeTranscriber(transcript=_TRANSCRIPT)
    monkeypatch.setattr(audio_module, "get_transcriber", lambda: transcriber)
    monkeypatch.setattr(asr_factory_module, "get_transcriber", lambda: transcriber)


def _upload_and_get_detail(filename: str) -> dict:
    """上传一份录音资料并等到终态，返回资料详情（TestClient 在响应前跑完后台解析）。"""
    created = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, b"fake audio bytes", "application/octet-stream")},
    )
    assert created.status_code == 200, created.text
    detail = client.get(f"/api/v1/documents/{created.json()['id']}")
    assert detail.status_code == 200, detail.text
    return detail.json()


def test_pipeline_generates_note_with_summary_and_knowledge_index():
    """有对话模型替身：解析完成后文献笔记完整——资料概要 + 本资料的知识点索引。"""
    detail = _upload_and_get_detail("gougu-lecture.mp3")

    assert detail["status"] == "已完成"
    note = detail["literature_note"]
    assert note["status"] == "已生成"
    assert note["source"] == "教学资料"
    assert note["summary"].strip(), "资料概要是文献笔记的主体，替身在场时必须非空"

    # 索引可点到知识点：条目与「这份资料提取出的全部入库知识点」一一对应——
    # 既是真实节点 id（nodes_for_docs 只回已入库节点），也不漏不多（覆盖全量）。
    entries = note["knowledge_index"]
    sourced = nodes_for_docs([detail["id"]])
    assert sourced, "替身提取的知识点应已入库"
    assert {entry["id"] for entry in entries} == {node["id"] for node in sourced}
    assert {entry["title"] for entry in entries} == {node["title"] for node in sourced}


def test_unconfigured_llm_keeps_chunks_and_reports_guidance(monkeypatch):
    """对话模型未配置：分块与解析照常入库（资料仍「已完成」），文献笔记不生成。

    详情如实报「未配置」且概要与索引为空——不返回假摘要（AGENTS.md 铁律）。
    """
    from app.config import settings
    from app.core.llm.factory import get_llm

    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "default_provider_instance", "")
    get_llm.cache_clear()
    try:
        detail = _upload_and_get_detail("no-model-lecture.mp3")
    finally:
        get_llm.cache_clear()

    assert detail["status"] == "已完成"  # 解析主流程不受对话模型缺位影响
    assert detail["chunk_count"] >= 1  # 分块照常入库，可检索
    note = detail["literature_note"]
    assert note["status"] == "未配置"
    assert note["summary"] == ""
    assert note["knowledge_index"] == []


def test_failed_parse_has_no_note():
    """解析失败的资料没有文献笔记：详情如实报「未生成」，不编造内容。"""
    created = client.post(
        "/api/v1/documents/upload",
        files={"file": ("broken.pdf", b"this is not a pdf", "application/pdf")},
    )
    assert created.status_code == 200
    detail = client.get(f"/api/v1/documents/{created.json()['id']}").json()

    assert detail["status"] == "失败"
    assert detail["literature_note"]["status"] == "未生成"
    assert detail["literature_note"]["summary"] == ""
