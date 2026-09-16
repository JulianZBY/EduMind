"""互动内容生成测试：提示词填充 + stub 模式产物可解析。"""

import app.generate.creative as creative_module
from app.core.llm.base import ChatResult
from app.core.llm.providers.stub import StubProvider


class _CapturingProvider(StubProvider):
    """记录 prompt 的假网关：返回固定文本以便断言提示词内容。"""

    def __init__(self):
        self.last_prompt = ""

    async def chat(self, messages, **kwargs):
        self.last_prompt = messages[-1].content
        return ChatResult(content="[fake]")

    async def embed(self, texts):
        return [[float(len(t))] * 8 for t in texts]


async def test_creative_prompt_fills_knowledge_once(monkeypatch):
    """占位符只填一次：知识点文本在提示词中不重复（回归：__KNOWLEDGE__ 出现两次）。"""
    provider = _CapturingProvider()
    monkeypatch.setattr(creative_module, "get_llm", lambda: provider)
    knowledge = "TCP三次握手：SYN → SYN+ACK → ACK"
    await creative_module.generate_html_creative(knowledge)
    prompt = provider.last_prompt
    assert knowledge in prompt
    assert prompt.count(knowledge) == 1


async def test_creative_stub_produces_parseable_html(monkeypatch):
    """stub 模式下产出可解析的单文件 HTML（内联样式与脚本，无外部依赖）。"""
    monkeypatch.setattr(creative_module, "get_llm", lambda: StubProvider())
    html = await creative_module.generate_html_creative("TCP三次握手")
    lowered = html.lower()
    assert "<html" in lowered
    assert "<style" in lowered and "<script" in lowered
    assert "http://" not in lowered and "https://" not in lowered
