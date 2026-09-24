"""对话接口测试（无状态路径：澄清与生成两个分支）。

接缝仍是 HTTP API 与外部能力：意图分析由 LLM 能力替身注入（见 `tests/session_support.py`），
不替换内部函数；生成回复会落盘，故重定向到临时目录。
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_outputs(isolated_output_dir):
    """生成回复会产出课件 / 教案文件：落盘重定向到临时目录，不写 backend/data。"""
    return isolated_output_dir


def _chat(content: str, **payload) -> dict:
    r = client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": content}], **payload}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_chat_clarify_when_no_topic(install_semantic_llm):
    """教师没说主题时先问主题：澄清回复，不带生成物。"""
    install_semantic_llm()  # 没有可抽取的要素 → 意图里没有主题

    body = _chat("备课")

    assert body["clarifying"] is True
    assert body["artifacts"] is None
    assert "请问你要讲什么课" in body["content"]


def test_chat_clarify_when_missing_fields(install_semantic_llm):
    """有主题但标准档要素不全（缺风格 / 目标 / 重点）：继续追问。"""
    install_semantic_llm(learned={"讲TCP，45分钟": {"topic": "TCP", "duration_minutes": 45}})

    body = _chat("讲TCP，45分钟", granularity="标准")

    assert body["clarifying"] is True
    assert body["artifacts"] is None
    assert "还差一点信息" in body["content"]


def test_chat_generate_when_complete(install_semantic_llm):
    """标准档要素齐全时直出生成物：生成回复，artifacts 带上课件与教案。"""
    install_semantic_llm(
        learned={
            "讲TCP，45分钟，风格是学术，重点是三次握手": {
                "topic": "TCP",
                "duration_minutes": 45,
                "style": "学术",
                "objectives": ["理解三次握手"],
                "key_points": ["三次握手"],
            }
        }
    )

    body = _chat("讲TCP，45分钟，风格是学术，重点是三次握手")

    assert body["clarifying"] is False
    assert body["artifacts"] is not None
    assert body["artifacts"]["ppt"]["slides"]
