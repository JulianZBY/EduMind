"""向量化能力：独立接口 + 工厂 + 配置名选择（stub 底线 / hash 兜底 / openai 与方言）。"""

import httpx
import pytest

from app.config import settings
from app.core.embedding.base import Embedder
from app.core.embedding.factory import get_embedder
from app.core.embedding.hash import HashEmbedder
from app.core.embedding.openai_compat import OpenAICompatEmbedder
from app.core.embedding.stub import StubEmbedder

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
SILICONFLOW_BASE = "https://api.siliconflow.cn/v1"


@pytest.fixture(autouse=True)
def _reset_embedding_config(monkeypatch):
    """每个用例从干净的配置口径出发（工厂带缓存，改配置即重建）。"""
    get_embedder.cache_clear()
    monkeypatch.setattr(settings, "embedding_provider", "")
    monkeypatch.setattr(settings, "embedding_base_url", "")
    monkeypatch.setattr(settings, "embedding_model", "")
    monkeypatch.setattr(settings, "embedding_api_key", "")
    monkeypatch.setattr(settings, "embedding_dimensions", 0)
    yield
    get_embedder.cache_clear()


async def test_stub_embedder_shape_and_determinism():
    """stub：8 维、以文本长度为特征、确定性（无 Key 底线）。"""
    embedder = StubEmbedder()
    assert isinstance(embedder, Embedder)
    vectors = await embedder.embed(["a", "bb", "ccc"])
    assert vectors == [[1.0] * 8, [2.0] * 8, [3.0] * 8]


async def test_hash_embedder_is_stable_normalized_and_dimension_fixed():
    """hash 兜底：64 维、L2 归一化、跨实例确定（crc32 而非带随机种子的 hash）。"""
    a = await HashEmbedder().embed(["TCP 三次握手"])
    b = await HashEmbedder().embed(["TCP 三次握手"])
    c = await HashEmbedder().embed(["TCP 四次挥手"])
    assert a == b
    assert len(a[0]) == 64
    assert abs(sum(v * v for v in a[0]) - 1.0) < 1e-9
    assert a != c


async def test_hash_embedder_empty_text_does_not_divide_by_zero():
    vec = (await HashEmbedder().embed([""]))[0]
    assert len(vec) == 64
    assert abs(sum(v * v for v in vec) - 1.0) < 1e-9


def test_factory_follows_chat_dialect_when_unset(monkeypatch):
    """未显式配置时跟随对话方言（保持既有 .env 行为）。"""
    monkeypatch.setattr(settings, "llm_provider", "stub")
    get_embedder.cache_clear()
    assert isinstance(get_embedder(), StubEmbedder)

    monkeypatch.setattr(settings, "llm_provider", "dashscope")
    monkeypatch.setattr(settings, "dashscope_api_key", "sk-d")
    get_embedder.cache_clear()
    embedder = get_embedder()
    assert isinstance(embedder, OpenAICompatEmbedder)
    assert (embedder.base_url, embedder.model, embedder.dimensions) == (
        DASHSCOPE_BASE,
        "text-embedding-v3",
        1024,
    )

    # deepseek 官方不提供 embedding：有硅基流动 Key 走它
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "siliconflow_api_key", "sk-s")
    get_embedder.cache_clear()
    embedder = get_embedder()
    assert isinstance(embedder, OpenAICompatEmbedder)
    assert (embedder.base_url, embedder.model) == (SILICONFLOW_BASE, "BAAI/bge-large-zh-v1.5")

    # 没有硅基流动 Key 时退本地 hash（可跑通、质量降级）
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
    get_embedder.cache_clear()
    assert isinstance(get_embedder(), HashEmbedder)


def test_explicit_provider_overrides_dialect(monkeypatch):
    """显式配置优先：向量化与对话可以是不同服务商、不同 Key。"""
    monkeypatch.setattr(settings, "llm_provider", "dashscope")
    monkeypatch.setattr(settings, "dashscope_api_key", "sk-d")
    monkeypatch.setattr(settings, "embedding_provider", "hash")
    get_embedder.cache_clear()
    assert isinstance(get_embedder(), HashEmbedder)


def test_explicit_openai_provider_needs_base_url_model_key(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "embedding_base_url", "https://llm.example.edu/v1")
    monkeypatch.setattr(settings, "embedding_model", "edu-embed")
    get_embedder.cache_clear()
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        get_embedder()

    monkeypatch.setattr(settings, "embedding_api_key", "sk-e")
    monkeypatch.setattr(settings, "embedding_dimensions", 512)
    get_embedder.cache_clear()
    embedder = get_embedder()
    assert isinstance(embedder, OpenAICompatEmbedder)
    assert (embedder.base_url, embedder.model, embedder.dimensions) == (
        "https://llm.example.edu/v1",
        "edu-embed",
        512,
    )


def test_unknown_embedding_provider_lists_available(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "nowhere")
    get_embedder.cache_clear()
    with pytest.raises(ValueError, match="可选"):
        get_embedder()


async def test_empty_input_makes_no_request():
    """空输入直接返回空结果（不发无意义请求）。"""

    def fail(request: httpx.Request) -> httpx.Response:  # pragma: no cover - 不应被调用
        raise AssertionError("空输入不应发起请求")

    embedder = OpenAICompatEmbedder(
        base_url=SILICONFLOW_BASE, model="m", api_key="k", transport=httpx.MockTransport(fail)
    )
    assert await embedder.embed([]) == []


async def test_response_count_mismatch_is_reported():
    """响应条数与输入不符时报错，避免静默错位入库。"""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})
    )
    embedder = OpenAICompatEmbedder(
        base_url=SILICONFLOW_BASE, model="m", api_key="k", transport=transport
    )
    with pytest.raises(RuntimeError, match="条数不符"):
        await embedder.embed(["甲", "乙"])
