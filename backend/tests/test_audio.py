"""录音转写测试（HTTP API 主接缝：stub 转写器 + stub 网关，不触真实云端）。

覆盖 ticket #11 验收项：
- 音频解析接入真实 provider：paraformer 云端契约单测（MockTransport 全流程）
- stub 模式下管道单测通过：上传录音 → 文档状态完成 → 语义检索命中转写内容
- 转写失败文档状态标记为失败，且不拖垮其他格式的解析
"""

import asyncio
import json
import time

import httpx
import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient

import app.api.v1.knowledge as knowledge_module
import app.core.llm.factory as factory_module
import app.knowledge.parsers.audio as audio_module
import app.knowledge.pipeline as pipeline_module
import app.knowledge.vector_store as vector_store_module
from app.config import settings
from app.core.asr.base import Transcriber
from app.core.asr.factory import get_transcriber
from app.core.asr.paraformer import ParaformerTranscriber
from app.core.asr.stub import STUB_TRANSCRIPT, StubTranscriber
from app.core.llm.providers.stub import StubProvider
from app.db import init_db
from app.knowledge.parsers import get_parser
from app.knowledge.parsers.audio import AudioParser
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在


@pytest.fixture(autouse=True)
def _clear_transcriber_cache():
    """get_transcriber 带 lru_cache，测试间清缓存保证 monkeypatch settings 生效。"""
    get_transcriber.cache_clear()
    yield
    get_transcriber.cache_clear()


class FailingTranscriber(Transcriber):
    """恒定抛错的假转写器：模拟云端转写失败。"""

    name = "failing"

    async def transcribe(self, file_path: str) -> str:
        raise RuntimeError("转写服务不可用")


def _wait_status(doc_id: str, want: str, tries: int = 50) -> dict:
    """轮询文档列表直到到达目标状态（后台解析为请求内任务，瞬时可达）。"""
    listed: dict = {}
    for _ in range(tries):
        listed = {d["id"]: d for d in client.get("/api/v1/documents").json()["documents"]}
        if listed[doc_id]["status"] == want:
            return listed[doc_id]
        time.sleep(0.05)
    raise AssertionError(f"文档未到达状态「{want}」：{listed.get(doc_id)}")


def test_registry_maps_audio_formats():
    """常见录音格式注册到 AudioParser；未知格式维持 ValueError。"""
    for ext in ("mp3", "wav", "m4a", "aac", "flac", "ogg", "oga", "opus", "wma", "amr"):
        assert isinstance(get_parser(ext), AudioParser), ext


def test_factory_stub_default(monkeypatch):
    monkeypatch.setattr(settings, "asr_provider", "stub")
    assert isinstance(get_transcriber(), StubTranscriber)


def test_factory_paraformer_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "asr_provider", "paraformer")
    monkeypatch.setattr(settings, "dashscope_api_key", "")
    try:
        get_transcriber()
        assert False, "缺 key 应抛 ValueError"
    except ValueError:
        pass


def test_factory_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "asr_provider", "nope")
    try:
        get_transcriber()
        assert False, "未知 provider 应抛 ValueError"
    except ValueError:
        pass


def test_stub_transcriber_returns_fixed_transcript():
    text = asyncio.run(StubTranscriber().transcribe("x.wav"))
    assert text == STUB_TRANSCRIPT


def test_upload_audio_completes_and_search_hits_transcript(monkeypatch, tmp_path):
    """stub 模式管道：上传录音 → 状态已完成 → 语义检索命中转写内容。"""
    store = VectorStore(str(tmp_path / "vectors.db"))
    monkeypatch.setattr(audio_module, "get_transcriber", lambda: StubTranscriber())
    monkeypatch.setattr(pipeline_module, "get_llm", lambda: StubProvider())
    monkeypatch.setattr(factory_module, "get_llm", lambda: StubProvider())
    monkeypatch.setattr(knowledge_module, "get_llm", lambda: StubProvider())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)
    monkeypatch.setattr(knowledge_module, "VectorStore", lambda: store)

    files = {"file": ("讲座录音.wav", b"RIFF fake audio bytes", "audio/wav")}
    r = client.post("/api/v1/documents/upload", files=files)
    assert r.status_code == 200
    assert r.json()["file_type"] == "wav"
    doc_id = r.json()["id"]

    doc = _wait_status(doc_id, "已完成")
    assert doc["filename"] == "讲座录音.wav"

    sr = client.post("/api/v1/knowledge/search", json={"query": "转写文字稿", "k": 3})
    assert sr.status_code == 200
    contents = [h["content"] for h in sr.json()["hits"]]
    assert any(STUB_TRANSCRIPT[:20] in c for c in contents), contents


def test_transcription_failure_marks_failed_without_blocking_others(monkeypatch, tmp_path):
    """转写失败 → 文档状态失败；其他格式（docx 本地解析）不受影响照常完成。"""
    store = VectorStore(str(tmp_path / "vectors.db"))
    monkeypatch.setattr(pipeline_module, "get_llm", lambda: StubProvider())
    monkeypatch.setattr(factory_module, "get_llm", lambda: StubProvider())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)

    monkeypatch.setattr(audio_module, "get_transcriber", lambda: FailingTranscriber())
    r = client.post(
        "/api/v1/documents/upload",
        files={"file": ("坏录音.mp3", b"not really audio", "audio/mpeg")},
    )
    assert r.status_code == 200  # 上传接口本身不因转写失败而报错
    bad_id = r.json()["id"]
    _wait_status(bad_id, "失败")

    monkeypatch.setattr(audio_module, "get_transcriber", lambda: StubTranscriber())
    doc = DocxDocument()
    doc.add_paragraph("教学目标：理解录音转写管道")
    docx_path = tmp_path / "讲义.docx"
    doc.save(str(docx_path))
    r2 = client.post(
        "/api/v1/documents/upload",
        files={"file": ("讲义.docx", docx_path.read_bytes(), "application/docx")},
    )
    assert r2.status_code == 200
    _wait_status(r2.json()["id"], "已完成")


# ---- paraformer 云端契约（MockTransport 全流程，不发真实请求）----


def _paraformer_handler(httpx_state: dict):
    """按请求路径分发假 DashScope/OSS 响应；记录关键断言素材到 state。"""

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.path == "/api/v1/uploads":
            assert url.params["action"] == "getPolicy"
            assert url.params["model"] == "paraformer-v2"
            assert "bearer sk-test" == request.headers["authorization"].lower()
            return httpx.Response(
                200,
                json={
                    "request_id": "req-1",
                    "data": {
                        "policy": "POLICY_B64",
                        "signature": "SIG",
                        "upload_dir": "dashscope-instant/x/2026-01-01/abc",
                        "upload_host": "https://oss.test",
                        "oss_access_key_id": "AK",
                        "x_oss_object_acl": "private",
                        "x_oss_forbid_overwrite": "true",
                    },
                },
            )
        if url.host == "oss.test":  # 表单直传 OSS：file 字段最后，凭证字段齐全
            body = request.content
            assert b"OSSAccessKeyId" in body and b"AK" in body
            assert b"POLICY_B64" in body and b"SIG" in body
            assert b"lecture.wav" in body
            assert body.rstrip().endswith(b"--")  # 以结尾边界收尾（file 在最后一段）
            return httpx.Response(200)
        if url.path == "/api/v1/services/audio/asr/transcription":
            assert request.headers["x-dashscope-async"] == "enable"
            assert request.headers["x-dashscope-ossresourceresolve"] == "enable"
            payload = json.loads(request.content)
            assert payload["model"] == "paraformer-v2"
            assert payload["input"]["file_urls"] == [
                "oss://dashscope-instant/x/2026-01-01/abc/lecture.wav"
            ]
            return httpx.Response(200, json={"output": {"task_id": "T1", "task_status": "PENDING"}})
        if url.path == "/api/v1/tasks/T1":
            httpx_state["polls"] = httpx_state.get("polls", 0) + 1
            if httpx_state["polls"] == 1:
                return httpx.Response(
                    200, json={"output": {"task_id": "T1", "task_status": "RUNNING"}}
                )
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_id": "T1",
                        "task_status": "SUCCEEDED",
                        "results": [
                            {
                                "file_url": "oss://dashscope-instant/x/2026-01-01/abc/lecture.wav",
                                "transcription_url": "https://result.test/t.json",
                                "subtask_status": "SUCCEEDED",
                            }
                        ],
                    }
                },
            )
        if url.host == "result.test":  # 签名公开地址下载转写 JSON
            return httpx.Response(
                200,
                json={
                    "file_url": "oss://dashscope-instant/x/2026-01-01/abc/lecture.wav",
                    "transcripts": [
                        {"channel_id": 0, "text": "第一段讲解内容。"},
                        {"channel_id": 1, "text": "第二段讲解内容。"},
                    ],
                },
            )
        raise AssertionError(f"意外请求: {request.method} {url}")

    return handler


def test_paraformer_full_flow(tmp_path):
    """getPolicy → OSS 直传 → 创建任务 → 轮询 → 拼接 transcripts 文本。"""
    audio = tmp_path / "lecture.wav"
    audio.write_bytes(b"RIFF fake")
    state: dict = {}
    t = ParaformerTranscriber("sk-test", transport=httpx.MockTransport(_paraformer_handler(state)))
    text = asyncio.run(t.transcribe(str(audio), poll_interval=0))
    assert text == "第一段讲解内容。\n第二段讲解内容。"
    assert state["polls"] >= 2  # 至少轮询过一次非终态


def test_paraformer_task_failed_raises(tmp_path):
    """任务级 FAILED（含 message）→ RuntimeError。"""
    audio = tmp_path / "lecture.wav"
    audio.write_bytes(b"RIFF fake")

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.path == "/api/v1/uploads":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "policy": "P",
                        "signature": "S",
                        "upload_dir": "dir",
                        "upload_host": "https://oss.test",
                        "oss_access_key_id": "AK",
                        "x_oss_object_acl": "private",
                        "x_oss_forbid_overwrite": "true",
                    }
                },
            )
        if url.host == "oss.test":
            return httpx.Response(200)
        if url.path == "/api/v1/services/audio/asr/transcription":
            return httpx.Response(200, json={"output": {"task_id": "T9", "task_status": "PENDING"}})
        if url.path == "/api/v1/tasks/T9":
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_id": "T9",
                        "task_status": "FAILED",
                        "message": "AUDIO_FILE_NOT_FOUND",
                    }
                },
            )
        raise AssertionError(f"意外请求: {url}")

    t = ParaformerTranscriber("sk-test", transport=httpx.MockTransport(handler))
    try:
        asyncio.run(t.transcribe(str(audio), poll_interval=0))
        assert False, "任务失败应抛 RuntimeError"
    except RuntimeError as e:
        assert "AUDIO_FILE_NOT_FOUND" in str(e)


def test_paraformer_subtask_failed_raises(tmp_path):
    """任务 SUCCEEDED 但子任务失败（无 transcription_url）→ RuntimeError。"""
    audio = tmp_path / "lecture.wav"
    audio.write_bytes(b"RIFF fake")

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.path == "/api/v1/uploads":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "policy": "P",
                        "signature": "S",
                        "upload_dir": "dir",
                        "upload_host": "https://oss.test",
                        "oss_access_key_id": "AK",
                        "x_oss_object_acl": "private",
                        "x_oss_forbid_overwrite": "true",
                    }
                },
            )
        if url.host == "oss.test":
            return httpx.Response(200)
        if url.path == "/api/v1/services/audio/asr/transcription":
            return httpx.Response(200, json={"output": {"task_id": "T2", "task_status": "PENDING"}})
        if url.path == "/api/v1/tasks/T2":
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_id": "T2",
                        "task_status": "SUCCEEDED",
                        "results": [
                            {"file_url": "oss://x", "subtask_status": "FAILED", "code": "E1"}
                        ],
                    }
                },
            )
        raise AssertionError(f"意外请求: {url}")

    t = ParaformerTranscriber("sk-test", transport=httpx.MockTransport(handler))
    try:
        asyncio.run(t.transcribe(str(audio), poll_interval=0))
        assert False, "子任务失败应抛 RuntimeError"
    except RuntimeError as e:
        assert "E1" in str(e)


def test_paraformer_empty_transcript_raises(tmp_path):
    """转写 JSON 无有效文本 → RuntimeError（空文字稿进管道无意义，标记失败）。"""
    audio = tmp_path / "lecture.wav"
    audio.write_bytes(b"RIFF fake")

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.path == "/api/v1/uploads":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "policy": "P",
                        "signature": "S",
                        "upload_dir": "dir",
                        "upload_host": "https://oss.test",
                        "oss_access_key_id": "AK",
                        "x_oss_object_acl": "private",
                        "x_oss_forbid_overwrite": "true",
                    }
                },
            )
        if url.host == "oss.test":
            return httpx.Response(200)
        if url.path == "/api/v1/services/audio/asr/transcription":
            return httpx.Response(200, json={"output": {"task_id": "T3", "task_status": "PENDING"}})
        if url.path == "/api/v1/tasks/T3":
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_id": "T3",
                        "task_status": "SUCCEEDED",
                        "results": [{"transcription_url": "https://result.test/t.json"}],
                    }
                },
            )
        if url.host == "result.test":
            return httpx.Response(200, json={"transcripts": [{"text": ""}]})
        raise AssertionError(f"意外请求: {url}")

    t = ParaformerTranscriber("sk-test", transport=httpx.MockTransport(handler))
    try:
        asyncio.run(t.transcribe(str(audio), poll_interval=0))
        assert False, "空转写应抛 RuntimeError"
    except RuntimeError as e:
        assert "空" in str(e)


def test_paraformer_requires_key(tmp_path):
    audio = tmp_path / "lecture.wav"
    audio.write_bytes(b"RIFF fake")
    t = ParaformerTranscriber("")
    try:
        asyncio.run(t.transcribe(str(audio)))
        assert False, "缺 key 应抛 ValueError"
    except ValueError:
        pass
