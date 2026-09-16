"""LLM 网关 stub 测试。"""

import pytest

from app.core.llm.base import ChatMessage
from app.core.llm.providers.stub import StubProvider


@pytest.mark.asyncio
async def test_stub_chat_echoes():
    p = StubProvider()
    r = await p.chat([ChatMessage(role="user", content="讲计算机网络")])
    assert "讲计算机网络" in r.content


@pytest.mark.asyncio
async def test_stub_embed_shape():
    p = StubProvider()
    vecs = await p.embed(["a", "bb", "ccc"])
    assert len(vecs) == 3
    assert all(len(v) == 8 for v in vecs)


@pytest.mark.asyncio
async def test_stub_creative_prompt_returns_html():
    """创意内容提示词命中时返回完整单文件 HTML（stub 模式产物可解析的前提）。"""
    p = StubProvider()
    r = await p.chat(
        [
            ChatMessage(
                role="user",
                content="你是创意内容设计师。生成一个 HTML5 互动学习小游戏或知识点动画。",
            )
        ]
    )
    assert "<html" in r.content.lower()
    assert "</html>" in r.content.lower()
