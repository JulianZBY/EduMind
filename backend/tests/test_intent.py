"""意图分析测试（fake LLM，不触真实 API）。"""

import asyncio
import json

import app.core.intent as intent_module
from app.core.llm.base import ChatResult


class _FakeLLM:
    async def chat(self, messages, **kwargs):
        return ChatResult(
            content=json.dumps(
                {
                    "topic": "计算机网络",
                    "grade": "大二",
                    "duration_minutes": 45,
                    "objectives": ["理解网络分层"],
                    "knowledge_points": ["OSI七层模型", "TCP/IP"],
                    "key_points": ["三次握手"],
                    "difficult_points": ["拥塞控制"],
                    "style": "学术",
                    "teaching_methods": ["讲授", "案例"],
                    "interactivity": "课堂提问",
                }
            )
        )


def test_analyze_intent(monkeypatch):
    monkeypatch.setattr(intent_module, "get_llm", lambda: _FakeLLM())
    intent = asyncio.run(intent_module.analyze_intent("讲计算机网络，大二，45分钟"))
    assert intent.topic == "计算机网络"
    assert intent.duration_minutes == 45
    assert "OSI七层模型" in intent.knowledge_points
    assert intent.key_points == ["三次握手"]


class _RecordingLLM:
    """记录收到的 prompt，供网关断言。"""

    def __init__(self):
        self.prompts: list[str] = []

    async def chat(self, messages, **kwargs):
        self.prompts.append(messages[-1].content)
        return ChatResult(content="{}")


def test_analyze_intent_latest_expression_wins(monkeypatch):
    """累积表述前后矛盾时，意图以教师最新表述为准（stub 网关断言）。"""
    llm = _RecordingLLM()
    monkeypatch.setattr(intent_module, "get_llm", lambda: llm)
    accumulated = "讲导数，45分钟。算了，改成 90 分钟，加两个课堂练习。"
    asyncio.run(intent_module.analyze_intent(accumulated))
    prompt = llm.prompts[-1]
    # 完整累积文本进入网关：早的与最新的表述都在（时序可判）
    assert "45分钟" in prompt
    assert "90 分钟" in prompt
    # 明示时序规则：前后矛盾以最新为准
    assert "最新" in prompt and "为准" in prompt
