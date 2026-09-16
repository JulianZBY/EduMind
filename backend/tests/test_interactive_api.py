"""互动内容按需生成与自动触发测试（HTTP API 主接缝：stub 网关 + 直接种子数据）。

覆盖 ticket #8 验收项：
- 新的按需生成端点在 stub 模式下返回可解析的单文件 HTML
- 意图互动诉求命中时，备课流程自动附带互动内容产物（集成测试）
- 未命中互动诉求时不自动生成
"""

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

import app.core.intent as intent_module
import app.core.llm.factory as factory_module
import app.generate.creative as creative_module
import app.generate.outline as outline_module
import app.generate.ppt as ppt_module
import app.generate.word as word_module
import app.knowledge.vector_store as vector_store_module
from app.core.llm.base import ChatResult, LLMProvider
from app.core.llm.providers.stub import StubProvider
from app.db import init_db
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表、列与默认用户存在

OUTPUT_DIR = Path("data/output")

# 三大生成器（PPT/Word/提纲）共用的假响应：结构可解析，渲染走默认值
_FAKE_CHAT_JSON = (
    '{"slides": [{"title": "s", "points": ["p"]}], "key_points": ["k"], '
    '"difficult_points": [], "process": [], "activities": [], "homework": []}'
)

# 创意 prompt 命中时返回的固定单文件 HTML（内联 CSS + JS，无外部依赖）
_TEST_HTML = (
    "<!DOCTYPE html>\n"
    '<html lang="zh">\n'
    '<head><meta charset="utf-8"><title>知识点小游戏</title></head>\n'
    "<body><h1>导数小游戏</h1><script>var n = 0;</script></body>\n"
    "</html>"
)

# 创意 prompt 的识别标记（与 app.generate.creative 的提示词保持一致）
_CREATIVE_MARKER = "HTML5 互动学习小游戏"


class ScriptedProvider(LLMProvider):
    """按 prompt 分发的假网关：意图 prompt 带指定互动诉求，创意 prompt 返回固定 HTML。"""

    def __init__(self, interactivity: str) -> None:
        self.interactivity = interactivity
        self.prompts: list[str] = []

    async def chat(self, messages, **kwargs) -> ChatResult:
        prompt = messages[-1].content
        self.prompts.append(prompt)
        if _CREATIVE_MARKER in prompt:
            return ChatResult(content=_TEST_HTML)
        if "你是教学智能体的意图分析模块" in prompt:
            # 补齐标准粒度追问字段，让对话走到生成阶段
            intent = {
                "topic": "导数",
                "grade": "大二",
                "duration_minutes": 45,
                "style": "学术",
                "objectives": ["理解导数定义"],
                "key_points": ["导数与变化率"],
                "interactivity": self.interactivity,
            }
            return ChatResult(content=json.dumps(intent, ensure_ascii=False))
        return ChatResult(content=_FAKE_CHAT_JSON)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 与 stub 同构：以文本长度为特征
        return [[float(len(t))] * 8 for t in texts]


def _install(monkeypatch, provider: LLMProvider, tmp_path) -> None:
    """替换全部 get_llm 早绑定引用（意图/PPT/Word/提纲/创意）+ 空向量库。"""
    monkeypatch.setattr(factory_module, "get_llm", lambda: provider)
    monkeypatch.setattr(intent_module, "get_llm", lambda: provider)
    monkeypatch.setattr(ppt_module, "get_llm", lambda: provider)
    monkeypatch.setattr(word_module, "get_llm", lambda: provider)
    monkeypatch.setattr(outline_module, "get_llm", lambda: provider)
    monkeypatch.setattr(creative_module, "get_llm", lambda: provider)
    monkeypatch.setattr(
        vector_store_module, "VectorStore", lambda: VectorStore(str(tmp_path / "v.db"))
    )


def test_generate_endpoint_returns_parseable_single_file_html(monkeypatch, tmp_path):
    """验收 1：stub 模式下按需生成端点返回可解析的单文件 HTML，且可经文件接口取回。"""
    _install(monkeypatch, StubProvider(), tmp_path)

    r = client.post(
        "/api/v1/interactive/generate",
        json={"intent": {"topic": "TCP三次握手", "grade": "大二", "duration_minutes": 45}},
    )

    assert r.status_code == 200
    body = r.json()
    html = body["html"]
    # 单文件 HTML：文档结构完整（doctype / html / 内联脚本），无外部依赖
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "<script" in html
    assert body["filename"].endswith(".html")

    # 产物已落盘且回读一致
    path = OUTPUT_DIR / body["filename"]
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == html

    # 文件接口可取回，浏览器可直接打开互动（text/html 内联预览）
    f = client.get(f"/api/v1/files/{body['filename']}")
    assert f.status_code == 200
    assert "text/html" in f.headers["content-type"]
    assert f.text == html


def test_generate_endpoint_returns_502_when_output_not_html(monkeypatch, tmp_path):
    """LLM 输出不是单文件 HTML 时端点明确失败（502），不落盘坏产物。"""

    class BadProvider(LLMProvider):
        async def chat(self, messages, **kwargs) -> ChatResult:
            return ChatResult(content="（模型输出异常，不是 HTML）")

        async def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

    _install(monkeypatch, BadProvider(), tmp_path)
    before = {p.name for p in OUTPUT_DIR.glob("creative_*.html")} if OUTPUT_DIR.is_dir() else set()

    r = client.post(
        "/api/v1/interactive/generate",
        json={"intent": {"topic": f"TCP_{uuid.uuid4().hex[:6]}"}},
    )

    assert r.status_code == 502
    after = {p.name for p in OUTPUT_DIR.glob("creative_*.html")} if OUTPUT_DIR.is_dir() else set()
    assert after == before  # 未新增落盘互动内容


def test_chat_auto_generates_interactive_on_appeal_hit(monkeypatch, tmp_path):
    """验收 2：意图互动诉求命中（小游戏）时，备课流程自动附带互动内容产物。"""
    provider = ScriptedProvider("想要一个小游戏帮学生理解导数")
    _install(monkeypatch, provider, tmp_path)

    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "讲导数，想要个小游戏"}]},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["artifacts"] is not None
    interactive = body["artifacts"]["interactive"]
    assert interactive is not None
    assert interactive["html"].lstrip().startswith("<!DOCTYPE html>")
    assert interactive["filename"].endswith(".html")
    # 产物已落盘且回读一致
    path = OUTPUT_DIR / interactive["filename"]
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == interactive["html"]
    # 创意生成 prompt 确实发出（互动内容参与了本次备课流程）
    assert any(_CREATIVE_MARKER in p for p in provider.prompts)
    # 回复文案告知教师互动内容已自动生成
    assert "互动" in body["content"]


def test_chat_no_auto_generate_without_appeal(monkeypatch, tmp_path):
    """验收 3：未命中互动诉求（仅课堂提问类互动需求）时不自动生成。"""
    provider = ScriptedProvider("课堂提问")
    _install(monkeypatch, provider, tmp_path)

    r = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "讲导数"}]},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["artifacts"] is not None
    assert body["artifacts"]["interactive"] is None  # 未自动附带互动内容
    # 创意生成 prompt 未发出：未命中就不做生成
    assert not any(_CREATIVE_MARKER in p for p in provider.prompts)
