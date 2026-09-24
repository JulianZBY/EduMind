"""图谱融入生成检索测试（HTTP API 主接缝：stub 网关 + 直接种子数据）。"""

import uuid

from fastapi.testclient import TestClient

import app.api.v1.chat as chat_module
import app.core.embedding.factory as embedding_factory_module
import app.core.llm.factory as factory_module
import app.core.orchestrator as orchestrator_module
import app.generate.outline as outline_module
import app.generate.ppt as ppt_module
import app.generate.word as word_module
import app.knowledge.vector_store as vector_store_module
from app.core.intent import TeachingIntent
from app.core.llm.base import ChatResult, LLMProvider
from app.core.orchestrator import CONTEXT_BUDGET_CHARS
from app.db import SessionLocal, init_db
from app.db.models import KnowledgeEdge, KnowledgeNode
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)
init_db()  # 幂等

# 三个生成器（PPT/Word/提纲）共用的假响应：结构可解析，渲染走默认值
_FAKE_CHAT_JSON = (
    '{"slides": [{"title": "s", "points": ["p"]}], "key_points": ["k"], '
    '"difficult_points": [], "process": [], "activities": [], "homework": []}'
)


class RecordingProvider(LLMProvider):
    """捕获全部 chat prompt 的假网关：可断言传给 LLM 的上下文内容。"""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.embed_fail = False

    async def chat(self, messages, **kwargs) -> ChatResult:
        self.prompts.append(messages[-1].content)
        return ChatResult(content=_FAKE_CHAT_JSON)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.embed_fail:
            raise RuntimeError("embedding 服务不可用")
        return [[float(len(t))] * 8 for t in texts]


def _install(monkeypatch, provider: RecordingProvider, store: VectorStore | None) -> None:
    """伪装意图分析 + 全部 get_llm 引用 + 向量库（orchestrator 延迟 import，逐模块替换）。"""

    async def fake_analyze(text):
        return TeachingIntent(
            topic="导数", duration_minutes=45, style="学术", objectives=["a"], key_points=["b"]
        )

    # orchestrate 内部引用自己模块的 analyze_intent（早绑定），必须一并替换，
    # 否则真实意图分析会穿透到真实 LLM 网关。
    monkeypatch.setattr(chat_module, "analyze_intent", fake_analyze)
    monkeypatch.setattr(orchestrator_module, "analyze_intent", fake_analyze)
    monkeypatch.setattr(factory_module, "get_llm", lambda: provider)
    # 检索向量化只依赖 Embedder 接口（orchestrator 晚绑定，替换工厂即可；
    # provider 同时具备 embed，用作假向量化器）
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: provider)
    monkeypatch.setattr(ppt_module, "get_llm", lambda: provider)
    monkeypatch.setattr(word_module, "get_llm", lambda: provider)
    monkeypatch.setattr(outline_module, "get_llm", lambda: provider)
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)


def _seed_graph(suffix: str, hit_doc: str, other_doc: str) -> None:
    """种子图谱：A 来自被检索命中的文档，B 来自其他文档，A —前置依赖→ B。"""
    db = SessionLocal()
    try:
        a = KnowledgeNode(
            user_id="default",
            title=f"导数定义_{suffix}",
            content=f"导数定义内容_{suffix}",
            source_docs=[hit_doc],
        )
        b = KnowledgeNode(
            user_id="default",
            title=f"求导法则_{suffix}",
            content=f"求导法则内容_{suffix}",
            source_docs=[other_doc],
        )
        db.add_all([a, b])
        db.flush()
        db.add(
            KnowledgeEdge(user_id="default", from_node=a.id, to_node=b.id, relation_type="前置依赖")
        )
        db.commit()
    finally:
        db.close()


def test_empty_vector_store_degrades_to_empty_context(monkeypatch, tmp_path):
    """向量库为空时降级为空上下文，图谱不再独立检索，请求不报错。"""
    suffix = uuid.uuid4().hex[:6]
    _seed_graph(
        suffix, hit_doc=f"hit_{suffix}", other_doc=f"other_{suffix}"
    )  # 图谱有数据但不该被单独拉取
    store = VectorStore(str(tmp_path / "empty.db"))
    provider = RecordingProvider()
    _install(monkeypatch, provider, store)

    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "讲导数"}]})

    assert r.status_code == 200
    assert r.json()["artifacts"] is not None
    joined = "\n".join(provider.prompts)
    assert "知识片段" not in joined  # 无命中片段
    assert "图谱关联知识点" not in joined  # 无片段锚点则不拉图谱
    assert f"求导法则内容_{suffix}" not in joined


def test_embed_failure_degrades_to_empty_context(monkeypatch, tmp_path):
    """检索失败（embedding 异常）时降级为空上下文，请求不报错（既有行为保持）。"""
    suffix = uuid.uuid4().hex[:6]
    store = VectorStore(str(tmp_path / "v.db"))
    store.add(f"hit_{suffix}", [f"导数概念讲解chunk_{suffix}"], [[1.0] * 8])
    provider = RecordingProvider()
    provider.embed_fail = True
    _install(monkeypatch, provider, store)

    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "讲导数"}]})

    assert r.status_code == 200
    assert r.json()["artifacts"] is not None
    assert f"导数概念讲解chunk_{suffix}" not in "\n".join(provider.prompts)


def test_context_respects_budget_chunks_first_nodes_truncated(monkeypatch, tmp_path):
    """上下文总量受预算约束：片段优先完整保留，图谱节点内容被截断。"""
    suffix = uuid.uuid4().hex[:6]
    chunks = [f"chunk{i}_{suffix}" + "片段" * 995 for i in range(2)]  # 2 × ~2000 字符
    store = VectorStore(str(tmp_path / "v.db"))
    store.add(f"hit_{suffix}", chunks, [[float(1 + i)] * 8 for i in range(2)])

    node_content = f"头_{suffix}" + "知" * 2900 + f"尾_{suffix}"
    db = SessionLocal()
    try:
        a = KnowledgeNode(
            user_id="default",
            title=f"导数定义_{suffix}",
            content="种子节点",
            source_docs=[f"hit_{suffix}"],
        )
        b = KnowledgeNode(
            user_id="default",
            title=f"求导法则_{suffix}",
            content=node_content,
            source_docs=[f"other_{suffix}"],
        )
        db.add_all([a, b])
        db.flush()
        db.add(
            KnowledgeEdge(user_id="default", from_node=a.id, to_node=b.id, relation_type="前置依赖")
        )
        db.commit()
    finally:
        db.close()

    provider = RecordingProvider()
    _install(monkeypatch, provider, store)

    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "讲导数"}]})

    assert r.status_code == 200
    ppt_prompt = next(p for p in provider.prompts if "课件设计师" in p)
    context = ppt_prompt[ppt_prompt.index("=== 知识片段 ===") :].rstrip()  # 去掉模板尾部换行
    assert len(context) <= CONTEXT_BUDGET_CHARS  # 总量受预算约束
    for i in range(2):  # 片段优先：全部完整保留
        assert f"chunk{i}_{suffix}" in context and ("片段" * 995) in context
    assert f"头_{suffix}" in context  # 邻接节点进入上下文
    assert f"尾_{suffix}" not in context  # 节点内容被预算截断


def test_adjacent_node_content_reaches_llm_gateway(monkeypatch, tmp_path):
    """命中片段经来源文档定位知识点，邻接节点内容沿图谱边进入生成上下文。"""
    suffix = uuid.uuid4().hex[:6]
    store = VectorStore(str(tmp_path / "v.db"))
    store.add(f"hit_{suffix}", [f"导数概念讲解chunk_{suffix}"], [[1.0] * 8])
    _seed_graph(suffix, hit_doc=f"hit_{suffix}", other_doc=f"other_{suffix}")
    provider = RecordingProvider()
    _install(monkeypatch, provider, store)

    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "讲导数"}]})

    assert r.status_code == 200
    assert r.json()["artifacts"] is not None
    joined = "\n".join(provider.prompts)
    assert f"导数概念讲解chunk_{suffix}" in joined  # 命中片段仍进入上下文
    assert f"求导法则内容_{suffix}" in joined  # 邻接知识点内容进入上下文（图谱参与生成）
