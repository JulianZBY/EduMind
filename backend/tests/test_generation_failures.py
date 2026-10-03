"""必需生成失败时不落空文件、不返回成功；配置错误保持 503。"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.core.orchestrator as module
from app.core.errors import GenerationFailed, ProviderNotConfigured
from app.core.intent import TeachingIntent
from app.main import app


@pytest.mark.parametrize("failed", ["ppt", "word", "outline"])
@pytest.mark.parametrize("mode", ["exception", "empty"])
async def test_required_generation_failure_is_not_success(
    monkeypatch, isolated_output_dir, failed, mode
):
    async def retrieve(*args, **kwargs):
        return SimpleNamespace(context="", sources=[])

    async def result(kind, value):
        if kind == failed:
            if mode == "exception":
                raise ProviderNotConfigured("生成模型未配置")
            return {"ppt": [], "word": {}, "outline": ""}[kind]
        return value

    monkeypatch.setattr(module, "get_retriever", lambda: SimpleNamespace(retrieve=retrieve))
    monkeypatch.setattr(
        module,
        "generate_ppt_structure",
        lambda *a: result("ppt", [{"title": "一次函数", "points": ["定义"]}]),
    )
    monkeypatch.setattr(
        module,
        "generate_word_structure",
        lambda *a: result("word", {"process": [{"stage": "讲授", "content": "一次函数"}]}),
    )
    monkeypatch.setattr(module, "generate_outline", lambda *a: result("outline", "# 一次函数"))
    with pytest.raises(ProviderNotConfigured if mode == "exception" else GenerationFailed):
        await module.orchestrate(TeachingIntent(topic="一次函数"))
    import app.generate

    assert not list(app.generate.OUTPUT_DIR.glob("*"))


def test_upstream_connection_failure_is_readable(monkeypatch):
    import httpx

    from app.core.llm.providers.openai_compat import OpenAICompatProvider
    from app.generate import revise

    def fail(request):
        raise httpx.ConnectError("CERTIFICATE_VERIFY_FAILED secret-body", request=request)

    provider = OpenAICompatProvider(
        base_url="https://llm.example",
        model="m",
        api_key="secret-key",
        transport=httpx.MockTransport(fail),
    )
    monkeypatch.setattr(revise, "get_llm", lambda: provider)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/revise", json={"slides": [{"title": "一次函数"}], "feedback": "加一个例子"}
        )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "provider_request_failed"
    assert "secret" not in response.text


@pytest.mark.parametrize("interactive_result", ["valid", "invalid", "failure"])
async def test_interactive_generation_has_topic_without_knowledge(
    monkeypatch, isolated_output_dir, interactive_result
):
    from tests.support.fakes import FAKE_HTML, FAKE_PPT_SLIDES

    async def retrieve(*args, **kwargs):
        return SimpleNamespace(context="", sources=[])

    async def value(result):
        return result

    received = []

    async def creative(context):
        received.append(context)
        if interactive_result == "failure":
            raise ProviderNotConfigured("互动模型未配置")
        if interactive_result == "invalid":
            return "<!doctype html><html><body>未完成"
        return FAKE_HTML

    monkeypatch.setattr(module, "get_retriever", lambda: SimpleNamespace(retrieve=retrieve))
    monkeypatch.setattr(module, "generate_ppt_structure", lambda *a: value(FAKE_PPT_SLIDES))
    monkeypatch.setattr(
        module, "generate_word_structure", lambda *a: value({"key_points": ["定义"]})
    )
    monkeypatch.setattr(module, "generate_outline", lambda *a: value("# 一次函数"))
    monkeypatch.setattr(module, "generate_html_creative", creative)
    result = await module.orchestrate(
        TeachingIntent(topic="一次函数", interactivity="斜率互动小游戏")
    )
    assert "一次函数" in received[0] and "斜率" in received[0]
    if interactive_result == "valid":
        assert result["interactive"]["html"] == FAKE_HTML
    else:
        from app.core.conversation import _generate_reply

        assert result["interactive"] is None
        assert "互动内容生成失败" in _generate_reply("一次函数", result)
        import app.generate

        assert not list(app.generate.OUTPUT_DIR.glob("*.html"))
