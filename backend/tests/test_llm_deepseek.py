"""DeepSeek provider 测试：兜底向量确定性 / chat 请求结构（httpx 打桩）/ 工厂装配。"""

import pytest

import app.core.llm.factory as factory_module
import app.core.llm.providers.deepseek as deepseek_module
from app.config import settings
from app.core.llm.base import ChatMessage
from app.core.llm.providers.deepseek import DeepSeekProvider


def test_fallback_embed_deterministic_and_normalized():
    """兜底向量：跨实例确定（crc32，非带随机种子的内置 hash）、定长、L2 归一化。"""
    a = DeepSeekProvider(api_key="k")._fallback_embed("TCP 三次握手")
    b = DeepSeekProvider(api_key="k")._fallback_embed("TCP 三次握手")
    assert a == b
    assert len(a) == 64
    assert abs(sum(v * v for v in a) - 1.0) < 1e-9
    assert a != DeepSeekProvider(api_key="k")._fallback_embed("TCP 四次挥手")


def test_fallback_embed_empty_text_safe():
    vec = DeepSeekProvider(api_key="k")._fallback_embed("")
    assert len(vec) == 64
    assert abs(sum(v * v for v in vec) - 1.0) < 1e-9  # 不除零


class _FakeResp:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "ok"}}]}


@pytest.mark.asyncio
async def test_chat_posts_openai_compatible_payload(monkeypatch):
    """chat 走 OpenAI 兼容结构：Bearer 鉴权 + messages 数组 + 默认模型。"""
    captured: dict = {}

    class _Client:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            captured.update(url=url, headers=headers, json=json)
            return _FakeResp()

    monkeypatch.setattr(deepseek_module.httpx, "AsyncClient", _Client)
    p = DeepSeekProvider(api_key="sk-test")
    r = await p.chat([ChatMessage(role="user", content="hi")])

    assert r.content == "ok"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "deepseek-chat"
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_embed_without_siliconflow_key_uses_fallback():
    p = DeepSeekProvider(api_key="k", embed_api_key="")
    vecs = await p.embed(["甲", "乙"])
    assert vecs[0] == p._fallback_embed("甲")
    assert vecs[0] != vecs[1]


def test_factory_deepseek_branch(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        factory_module.get_llm.__wrapped__()  # 绕过 lru_cache 直测分支

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-x")
    monkeypatch.setattr(settings, "siliconflow_api_key", "sf-y")
    p = factory_module.get_llm.__wrapped__()
    assert isinstance(p, DeepSeekProvider)
    assert p.api_key == "sk-x"
    assert p.embed_api_key == "sf-y"
