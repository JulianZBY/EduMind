"""OpenAI 兼容 provider 契约测试：三家方言各一例（httpx.MockTransport 打桩出网，不触网络）。

- qwen：/compatible-mode/v1 上的多模态请求（payload 差异：content 为 parts 数组 + data URI）
- deepseek：api.deepseek.com 上的纯文本对话 + 多模态请求（新版模型 deepseek-flash / deepseek-v4-pro 支持视觉）
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
QWEN_BASE = "https://maas.qianwenaiapi.com/compatible-mode/v1"
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


async def test_qwen_dialect_sends_multimodal_payload(tmp_path):
    """qwen（千问）：多模态请求打在 compatible-mode 上，content 为 parts 数组。"""
    rec = _Recorder(_CHAT_OK)
    provider = OpenAICompatProvider(
        base_url=QWEN_BASE,
        model="qwen-plus",
        api_key="sk-dash",
        vision_model="qwen-vl-max",
        transport=rec.transport,
    )
    image = tmp_path / "frame.png"
    image.write_bytes(b"\x89PNG fake bytes")

    assert await provider.vision(str(image), "这是教学视频的一帧") == "ok"

    request = rec.requests[0]
    assert str(request.url) == f"{QWEN_BASE}/chat/completions"
    assert request.headers["Authorization"] == "Bearer sk-dash"
    body = rec.bodies[0]
    assert body["model"] == "qwen-vl-max"  # 多模态走 vision 模型
    parts = body["messages"][0]["content"]
    expected_b64 = base64.b64encode(image.read_bytes()).decode()
    assert parts[0]["type"] == "image_url"
    assert parts[0]["image_url"]["url"] == f"data:image/png;base64,{expected_b64}"
    assert parts[1] == {"type": "text", "text": "这是教学视频的一帧"}


async def test_deepseek_dialect_sends_chat_and_vision_payloads(tmp_path):
    """deepseek：纯文本与多模态都打 api.deepseek.com，vision 走专用模型。"""
    rec = _Recorder(_CHAT_OK)
    provider = OpenAICompatProvider(
        base_url=DEEPSEEK_BASE,
        model="deepseek-flash",
        api_key="sk-deep",
        vision_model="deepseek-v4-pro",
        transport=rec.transport,
    )

    result = await provider.chat([ChatMessage(role="user", content="hi")])

    assert result.content == "ok"
    assert result.raw == _CHAT_OK
    assert str(rec.requests[0].url) == f"{DEEPSEEK_BASE}/chat/completions"
    assert rec.bodies[0]["model"] == "deepseek-flash"
    image = tmp_path / "frame.png"
    image.write_bytes(b"\x89PNG fake bytes")
    assert await provider.vision(str(image), "看这张图") == "ok"
    assert rec.bodies[1]["model"] == "deepseek-v4-pro"
    parts = rec.bodies[1]["messages"][0]["content"]
    assert parts[0]["type"] == "image_url"


async def test_deepseek_dialect_chat_model_can_be_overridden():
    """model 可逐次覆盖（同一方言换模型不改代码）。"""
    rec = _Recorder(_CHAT_OK)
    provider = OpenAICompatProvider(
        base_url=DEEPSEEK_BASE, model="deepseek-flash", api_key="k", transport=rec.transport
    )

    await provider.chat([ChatMessage(role="user", content="hi")], model="deepseek-v4-pro")

    assert rec.bodies[0]["model"] == "deepseek-v4-pro"


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


async def test_qwen_dialect_embeddings_carry_dimensions():
    """千问的 embedding 方言差异：请求携带 dimensions（text-embedding-v3 支持）。"""
    rec = _Recorder({"data": [{"index": 0, "embedding": [0.5] * 1024}]})
    embedder = OpenAICompatEmbedder(
        base_url=QWEN_BASE,
        model="text-embedding-v3",
        api_key="sk-dash",
        dimensions=1024,
        transport=rec.transport,
    )

    vectors = await embedder.embed(["三次握手"])

    assert rec.bodies[0]["dimensions"] == 1024
    assert len(vectors[0]) == 1024


class _EchoEmbedRecorder:
    """按每次请求的 input 长度回同等条数向量的桩（分批测试用：每批响应匹配该批输入）。"""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    @property
    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            inputs = body["input"]
            self.batches.append(inputs)
            data = [{"index": i, "embedding": [float(i)]} for i in range(len(inputs))]
            return httpx.Response(200, json={"data": data})

        return httpx.MockTransport(handler)


async def test_embedder_splits_batches_at_ten():
    """分批契约：单请求 input 不超过 10 条（千问 MaaS 实测上限，11 条即 400），
    超出自动拆批串行请求，向量按原顺序拼接——大文档几百块不再整批被拒。"""
    rec = _EchoEmbedRecorder()
    embedder = OpenAICompatEmbedder(
        base_url=QWEN_BASE,
        model="text-embedding-v3",
        api_key="sk-dash",
        transport=rec.transport,
    )

    vectors = await embedder.embed([f"第{i}块" for i in range(25)])

    assert [len(b) for b in rec.batches] == [10, 10, 5]  # 25 块拆三批，无一批超限
    assert len(vectors) == 25
    assert vectors[9] == [9.0] and vectors[10] == [0.0]  # 批界处顺序仍正确（第 10/11 块来自不同批）


async def test_embedder_within_limit_stays_single_request():
    """恰在上限内不浪费请求：10 条输入仍是一个请求。"""
    rec = _EchoEmbedRecorder()
    embedder = OpenAICompatEmbedder(
        base_url=SILICONFLOW_BASE,
        model="BAAI/bge-large-zh-v1.5",
        api_key="sk-sf",
        transport=rec.transport,
    )

    vectors = await embedder.embed([f"块{i}" for i in range(10)])

    assert len(rec.batches) == 1
    assert len(vectors) == 10


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
        ("qwen", "qwen_api_key", "sk-d", QWEN_BASE, "qwen-plus", "qwen-vl-max"),
        ("deepseek", "deepseek_api_key", "sk-x", DEEPSEEK_BASE, "deepseek-flash", "deepseek-v4-pro"),
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
    monkeypatch.setattr(settings, "llm_provider", "qwen")
    monkeypatch.setattr(settings, "qwen_api_key", "")
    monkeypatch.setattr(settings, "llm_api_key", "")
    get_llm.cache_clear()

    with pytest.raises(ValueError, match="QWEN_API_KEY"):
        get_llm()


def test_unknown_provider_lists_available(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "nowhere")
    get_llm.cache_clear()

    with pytest.raises(ValueError, match="可选"):
        get_llm()
