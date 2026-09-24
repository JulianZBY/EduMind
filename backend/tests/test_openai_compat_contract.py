"""OpenAI 兼容 provider 契约测试：三家方言各一例（httpx.MockTransport 打桩出网，不触网络）。

- dashscope：/compatible-mode/v1 上的多模态请求（payload 差异：content 为 parts 数组 + data URI）
- deepseek：api.deepseek.com 上的纯文本对话（该方言无多模态模型 → vision 抛错）
- 硅基流动：/v1/embeddings 的请求与响应（响应差异：data 乱序时按 index 还原顺序）

另证「只改配置即可切换」：同一份代码，base_url / model / key 全由配置决定。
"""

import base64
import json

import httpx
import pytest

from app.config import settings
from app.core.embedding.factory import get_embedder
from app.core.embedding.openai_compat import OpenAICompatEmbedder
from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.llm.providers.openai_compat import OpenAICompatProvider

# 官方文档口径的方言样例（独立于实现，用作断言的真值来源）
DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE = "https://api.deepseek.com"
SILICONFLOW_BASE = "https://api.siliconflow.cn/v1"

_CHAT_OK = {"choices": [{"message": {"content": "ok"}}]}


class _Recorder:
    """记录出网请求（URL / 头 / body）的 MockTransport 桩。"""

    def __init__(self, response: dict) -> None:
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict] = []
        self._response = response

    @property
    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            self.bodies.append(json.loads(request.content))
            return httpx.Response(200, json=self._response)

        return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _clear_factory_caches():
    """settings 被 monkeypatch 时绕过 lru_cache，保证工厂按当前配置装配。"""
    get_llm.cache_clear()
    get_embedder.cache_clear()
    yield
    get_llm.cache_clear()
    get_embedder.cache_clear()


async def test_dashscope_dialect_sends_multimodal_payload(tmp_path):
    """dashscope：多模态请求打在 compatible-mode 上，content 为 parts 数组。"""
    rec = _Recorder(_CHAT_OK)
    provider = OpenAICompatProvider(
        base_url=DASHSCOPE_BASE,
        model="qwen-plus",
        api_key="sk-dash",
        vision_model="qwen-vl-max",
        transport=rec.transport,
    )
    image = tmp_path / "frame.png"
    image.write_bytes(b"\x89PNG fake bytes")

    assert await provider.vision(str(image), "这是教学视频的一帧") == "ok"

    request = rec.requests[0]
    assert str(request.url) == f"{DASHSCOPE_BASE}/chat/completions"
    assert request.headers["Authorization"] == "Bearer sk-dash"
    body = rec.bodies[0]
    assert body["model"] == "qwen-vl-max"  # 多模态走 vision 模型
    parts = body["messages"][0]["content"]
    expected_b64 = base64.b64encode(image.read_bytes()).decode()
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"] == f"data:image/png;base64,{expected_b64}"
    assert parts[1] == {"type": "text", "text": "这是教学视频的一帧"}


async def test_deepseek_dialect_sends_plain_chat_payload():
    """deepseek：纯文本对话打 api.deepseek.com，且该方言没有多模态模型。"""
    rec = _Recorder(_CHAT_OK)
    provider = OpenAICompatProvider(
        base_url=DEEPSEEK_BASE, model="deepseek-chat", api_key="sk-deep", transport=rec.transport
    )

    result = await provider.chat([ChatMessage(role="user", content="hi")])

    assert result.content == "ok"
    assert result.raw == _CHAT_OK
    assert str(rec.requests[0].url) == f"{DEEPSEEK_BASE}/chat/completions"
    assert rec.bodies[0] == {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "hi"}],
    }
    with pytest.raises(NotImplementedError):
        await provider.vision("frame.png", "看这张图")


async def test_deepseek_dialect_chat_model_can_be_overridden():
    """model 可逐次覆盖（同一方言换模型不改代码）。"""
    rec = _Recorder(_CHAT_OK)
    provider = OpenAICompatProvider(
        base_url=DEEPSEEK_BASE, model="deepseek-chat", api_key="k", transport=rec.transport
    )

    await provider.chat([ChatMessage(role="user", content="hi")], model="deepseek-reasoner")

    assert rec.bodies[0]["model"] == "deepseek-reasoner"


async def test_siliconflow_dialect_embeddings_payload_and_index_order():
    """硅基流动：/v1/embeddings 的 payload 与响应（data 乱序时按 index 还原）。"""
    response = {
        "data": [
            {"index": 1, "embedding": [0.2, 0.2]},
            {"index": 0, "embedding": [0.1, 0.1]},
        ]
    }
    rec = _Recorder(response)
    embedder = OpenAICompatEmbedder(
        base_url=SILICONFLOW_BASE,
        model="BAAI/bge-large-zh-v1.5",
        api_key="sk-sf",
        transport=rec.transport,
    )

    vectors = await embedder.embed(["甲", "乙"])

    request = rec.requests[0]
    assert str(request.url) == f"{SILICONFLOW_BASE}/embeddings"
    assert request.headers["Authorization"] == "Bearer sk-sf"
    assert rec.bodies[0] == {"model": "BAAI/bge-large-zh-v1.5", "input": ["甲", "乙"]}
    assert vectors == [[0.1, 0.1], [0.2, 0.2]]  # 按 index 还原为输入顺序


async def test_dashscope_dialect_embeddings_carry_dimensions():
    """dashscope 的 embedding 方言差异：请求携带 dimensions（text-embedding-v3 支持）。"""
    rec = _Recorder({"data": [{"index": 0, "embedding": [0.5] * 1024}]})
    embedder = OpenAICompatEmbedder(
        base_url=DASHSCOPE_BASE,
        model="text-embedding-v3",
        api_key="sk-dash",
        dimensions=1024,
        transport=rec.transport,
    )

    vectors = await embedder.embed(["三次握手"])

    assert rec.bodies[0]["dimensions"] == 1024
    assert len(vectors[0]) == 1024


async def test_content_parts_response_is_joined():
    """响应差异：部分兼容服务把 content 返回为 parts 数组，按文本部分拼接。"""
    rec = _Recorder(
        {"choices": [{"message": {"content": [{"type": "text", "text": "分段"}, {"text": "回复"}]}}]}
    )
    provider = OpenAICompatProvider(
        base_url=SILICONFLOW_BASE, model="m", api_key="k", transport=rec.transport
    )

    assert (await provider.chat([ChatMessage(role="user", content="hi")])).content == "分段回复"


def test_factory_switches_dialect_from_config_only(monkeypatch):
    """三家方言只改配置即可切换：同一份工厂代码，base_url / model / key 全部来自配置。"""
    expectations = [
        ("dashscope", "dashscope_api_key", "sk-d", DASHSCOPE_BASE, "qwen-plus", "qwen-vl-max"),
        ("deepseek", "deepseek_api_key", "sk-x", DEEPSEEK_BASE, "deepseek-chat", ""),
        (
            "siliconflow",
            "siliconflow_api_key",
            "sk-s",
            SILICONFLOW_BASE,
            "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen2.5-VL-72B-Instruct",
        ),
    ]
    for name, key_field, key, base_url, model, vision_model in expectations:
        monkeypatch.setattr(settings, "llm_provider", name)
        monkeypatch.setattr(settings, key_field, key)
        get_llm.cache_clear()
        provider = get_llm()
        assert isinstance(provider, OpenAICompatProvider)
        assert (provider.base_url, provider.model, provider.api_key) == (base_url, model, key)
        assert provider.vision_model == vision_model


def test_config_override_reaches_any_openai_compatible_server(monkeypatch):
    """未收录的服务商也只改配置：base_url / model / key / 多模态模型全部可覆盖。"""
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-x")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.example.edu/v1")
    monkeypatch.setattr(settings, "llm_model", "edu-chat-32b")
    monkeypatch.setattr(settings, "llm_api_key", "sk-override")
    monkeypatch.setattr(settings, "llm_vision_model", "edu-vl-8b")
    get_llm.cache_clear()

    provider = get_llm()

    assert isinstance(provider, OpenAICompatProvider)
    assert provider.base_url == "https://llm.example.edu/v1"
    assert provider.model == "edu-chat-32b"
    assert provider.api_key == "sk-override"
    assert provider.vision_model == "edu-vl-8b"


def test_missing_api_key_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "dashscope")
    monkeypatch.setattr(settings, "dashscope_api_key", "")
    monkeypatch.setattr(settings, "llm_api_key", "")
    get_llm.cache_clear()

    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        get_llm()


def test_unknown_provider_lists_available(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "nowhere")
    get_llm.cache_clear()

    with pytest.raises(ValueError, match="可选"):
        get_llm()
