"""检索相关度阈值与诚实空命中（票 01，ADR-0007）：超阈值的命中一律丢弃，空命中分两口径。

四态覆盖（替身向量 = 本地确定性 HashEmbedder，离线零成本）：
- 命中：相关分块照常返回；
- 超阈值丢弃：不相关分块直接丢弃（不是降权垫底）；
- 空库：`library_empty=True`，回复沿用「知识库为空」现状文案；
- 未命中：库非空但命中的都是不相关内容，回复说「知识库未命中相关内容，由 AI 直接生成」。

外加污染场景回归：query=秦始皇 + 库内只有 TCP 向量 → 命中为空。
阈值 `retrieval_distance_threshold` 与冲突检测的 `conflict_distance_threshold`
是两条独立水位，互不共用。
"""

import asyncio
import uuid

from fastapi.testclient import TestClient

import app.core.conversation as conversation_module
import app.core.embedding.factory as embedding_factory_module
import app.generate.outline as outline_module
import app.generate.ppt as ppt_module
import app.generate.word as word_module
import app.knowledge.vector_store as vector_store_module
from app.config import settings
from app.core.embedding.hash import HashEmbedder
from app.core.intent import TeachingIntent
from app.core.llm.base import ChatResult, LLMProvider
from app.db import init_db
from app.knowledge.retrieval.factory import get_retriever
from app.knowledge.retrieval.search import library_is_empty, search_hits
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表、列与默认用户存在

# 三个生成器（PPT/Word/提纲）共用的假响应：结构可解析，渲染走默认值
_FAKE_CHAT_JSON = (
    '{"slides": [{"title": "s", "points": ["p"]}], "key_points": ["k"], '
    '"difficult_points": [], "process": [], "activities": [], "homework": []}'
)


async def _seed(store: VectorStore, doc_id: str, chunks: list[str]) -> None:
    """用 HashEmbedder 的确定性向量入库（与查询向量化同一实现，距离可预期）。"""
    store.add(doc_id, chunks, await HashEmbedder().embed(chunks))


def _uninstall_retriever_cache() -> None:
    get_retriever.cache_clear()


# ---- 态一 + 态二：命中 / 超阈值丢弃 ----


async def test_relevant_hit_kept_and_irrelevant_dropped_not_downweighted(tmp_path, monkeypatch):
    """命中与超阈值丢弃：相关分块保留，不相关分块直接丢弃（不是降权垫底）。"""
    store = VectorStore(str(tmp_path / "v.db"))
    await _seed(store, "doc_math", ["导数的定义与求导法则"])
    await _seed(store, "doc_tcp", ["TCP三次握手"])
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: HashEmbedder())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)

    hits = await search_hits("导数", top_k=5, reference_doc_ids=None)

    assert hits is not None
    # 库里的 TCP 分块与查询几乎正交（余弦距离 > 阈值）：不出现，而不是排在末位
    assert [h.content for h in hits] == ["导数的定义与求导法则"]


async def test_threshold_is_configurable(tmp_path, monkeypatch):
    """阈值取自配置：收紧后连相关命中也被丢弃；放宽后回到保留。"""
    store = VectorStore(str(tmp_path / "v.db"))
    await _seed(store, "doc_math", ["导数的定义与求导法则"])
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: HashEmbedder())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)

    monkeypatch.setattr(settings, "retrieval_distance_threshold", 0.5)  # 导数命中 ≈0.59 也超阈
    assert await search_hits("导数", top_k=5, reference_doc_ids=None) == []

    monkeypatch.setattr(settings, "retrieval_distance_threshold", 0.99)  # 放宽：命中回来
    hits = await search_hits("导数", top_k=5, reference_doc_ids=None)
    assert hits is not None
    assert [h.content for h in hits] == ["导数的定义与求导法则"]


async def test_retrieval_threshold_does_not_share_conflict_watermark(tmp_path, monkeypatch):
    """与 conflict_distance_threshold 互不共用：冲突水位再紧，检索命中照常保留。"""
    store = VectorStore(str(tmp_path / "v.db"))
    await _seed(store, "doc_math", ["导数的定义与求导法则"])
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: HashEmbedder())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)
    monkeypatch.setattr(settings, "conflict_distance_threshold", 0.0001)  # 冲突近名预筛的水位

    hits = await search_hits("导数", top_k=5, reference_doc_ids=None)

    assert hits is not None
    assert [h.content for h in hits] == ["导数的定义与求导法则"]


# ---- 态三 + 态四：空库 / 未命中（检索层区分口径）----


def test_library_is_empty_distinguishes_empty_store(tmp_path, monkeypatch):
    """探测向量库是否一个分块都没有：空库 True、有内容 False。"""
    empty = VectorStore(str(tmp_path / "empty.db"))
    seeded = VectorStore(str(tmp_path / "v.db"))
    asyncio.run(_seed(seeded, "doc_tcp", ["TCP三次握手"]))
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: empty)
    assert library_is_empty() is True

    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: seeded)
    assert library_is_empty() is False


async def test_empty_library_reports_library_empty(tmp_path, monkeypatch):
    """态三（库为空）：命中为空且 library_empty=True，调用方能说「知识库为空」。"""
    store = VectorStore(str(tmp_path / "empty.db"))
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: HashEmbedder())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)
    _uninstall_retriever_cache()
    try:
        result = await get_retriever().retrieve(
            TeachingIntent(topic="导数"), reference_doc_ids=None
        )
    finally:
        _uninstall_retriever_cache()

    assert (result.context, result.sources, result.hits, result.graph_nodes) == ("", [], [], [])
    assert result.library_empty is True


async def test_no_match_reports_non_empty_library(tmp_path, monkeypatch):
    """态四（未命中）：库非空但命中全被丢弃，library_empty=False，调用方说「未命中相关内容」。"""
    store = VectorStore(str(tmp_path / "v.db"))
    await _seed(store, "doc_tcp", ["TCP三次握手", "TCP四次挥手"])
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: HashEmbedder())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)
    _uninstall_retriever_cache()
    try:
        result = await get_retriever().retrieve(
            TeachingIntent(topic="导数"), reference_doc_ids=None
        )
    finally:
        _uninstall_retriever_cache()

    assert (result.context, result.sources, result.hits) == ("", [], [])
    assert result.library_empty is False


# ---- 污染场景回归 ----


async def test_pollution_regression_qinshihuang_gets_no_tcp(tmp_path, monkeypatch):
    """回归（票 01 根因）：query=秦始皇 + 库内只有 TCP 向量 → 命中为空，上下文不带 TCP。"""
    store = VectorStore(str(tmp_path / "v.db"))
    await _seed(store, "doc_tcp", ["TCP三次握手", "TCP四次挥手"])
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: HashEmbedder())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)
    _uninstall_retriever_cache()
    try:
        result = await get_retriever().retrieve(
            TeachingIntent(topic="秦始皇统一六国"), reference_doc_ids=None
        )
    finally:
        _uninstall_retriever_cache()

    assert (result.context, result.sources, result.hits, result.graph_nodes) == ("", [], [], [])


# ---- 回复文案与 artifacts 口径 ----


def test_generate_reply_distinguishes_three_knowledge_outcomes():
    """回复文案三口径：命中 / 未命中相关内容 / 库为空，各说各话（后端语义）。"""

    def _result(**overrides) -> dict:
        base = {
            "ppt": {"slides": [1]},
            "references": [],
            "interactive": None,
            "interactive_failed": False,
            "knowledge_hits": False,
            "knowledge_empty": False,
        }
        base.update(overrides)
        return base

    hit = conversation_module._generate_reply("t", _result(knowledge_hits=True))
    miss = conversation_module._generate_reply("t", _result(knowledge_hits=False))
    no_hit = _result(knowledge_hits=False, knowledge_empty=True)
    empty = conversation_module._generate_reply("t", no_hit)

    assert "已融合本地知识库" in hit
    assert "知识库未命中相关内容，由 AI 直接生成" in miss
    assert "知识库为空，已由 AI 直接生成" in empty


class _RecordingLLM(LLMProvider):
    """捕获全部 chat prompt 的假网关：供 /chat 全链路测试断言上下文内容。"""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def chat(self, messages, **kwargs) -> ChatResult:
        self.prompts.append(messages[-1].content)
        return ChatResult(content=_FAKE_CHAT_JSON)


def _install(monkeypatch, store: VectorStore, embedder) -> _RecordingLLM:
    """伪装意图分析 + 全部 get_llm 引用 + 向量库与向量化（/chat 全链路离线）。返回假网关供断言。"""

    async def fake_analyze(text):
        return TeachingIntent(
            topic="导数", duration_minutes=45, style="学术", objectives=["a"], key_points=["b"]
        )

    llm = _RecordingLLM()
    monkeypatch.setattr(conversation_module, "analyze_intent", fake_analyze)
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: embedder)
    monkeypatch.setattr(ppt_module, "get_llm", lambda: llm)
    monkeypatch.setattr(word_module, "get_llm", lambda: llm)
    monkeypatch.setattr(outline_module, "get_llm", lambda: llm)
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)
    return llm


def test_chat_reply_on_empty_library_keeps_legacy_copy(monkeypatch, tmp_path):
    """/chat 全链路（库为空）：回复沿用「知识库为空」，artifacts 标 knowledge_empty=True。"""
    store = VectorStore(str(tmp_path / "empty.db"))
    _install(monkeypatch, store, HashEmbedder())

    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "讲导数"}]})

    assert r.status_code == 200
    body = r.json()
    assert "知识库为空，已由 AI 直接生成" in body["content"]
    assert "已融合本地知识库" not in body["content"]
    assert body["artifacts"]["knowledge_hits"] is False
    assert body["artifacts"]["knowledge_empty"] is True


def test_chat_reply_on_no_match_honest_miss_copy(monkeypatch, tmp_path):
    """/chat 全链路（库非空但只有 TCP）：不再谎报融合，明确说「未命中相关内容」。"""
    suffix = uuid.uuid4().hex[:6]
    store = VectorStore(str(tmp_path / "v.db"))
    asyncio.run(_seed(store, f"doc_tcp_{suffix}", ["TCP三次握手", "TCP四次挥手"]))
    llm = _install(monkeypatch, store, HashEmbedder())

    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "讲导数"}]})

    assert r.status_code == 200
    body = r.json()
    assert "知识库未命中相关内容，由 AI 直接生成" in body["content"]
    assert "已融合本地知识库" not in body["content"]
    assert body["artifacts"]["knowledge_hits"] is False
    assert body["artifacts"]["knowledge_empty"] is False
    # 污染根子（票 01）：TCP 分块不再进入生成上下文
    joined = "\n".join(llm.prompts)
    assert "TCP三次握手" not in joined and "TCP四次挥手" not in joined


def test_hit_chunks_enter_context_but_irrelevant_do_not(monkeypatch, tmp_path):
    """命中进入生成上下文；超阈值分块既不垫底也不进上下文。"""
    suffix = uuid.uuid4().hex[:6]
    store = VectorStore(str(tmp_path / "v.db"))
    asyncio.run(_seed(store, f"doc_math_{suffix}", ["导数的定义与求导法则"]))
    asyncio.run(_seed(store, f"doc_tcp_{suffix}", ["TCP三次握手"]))
    llm = _install(monkeypatch, store, HashEmbedder())

    r = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "讲导数"}]})

    assert r.status_code == 200
    joined = "\n".join(llm.prompts)
    assert "导数的定义与求导法则" in joined  # 相关命中照常融合
    assert "TCP三次握手" not in joined  # 不相关分块不进上下文
    assert "已融合本地知识库" in r.json()["content"]  # 真有命中时才说融合
