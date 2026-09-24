"""RAG 策略收编测试（票 03）：分块与检索都是「接口 + 工厂 + 按配置名切换」（ADR-0003）。

覆盖：
- 分块策略按配置选择，调用方（解析管道）零改动；默认档仍是收编前的切法；
- 两种检索策略按配置切换，默认档 = 收编前行为（逐字段黄金比对）；
- 编排器内不再有检索细节，调用方只依赖接口 + 工厂；
- 两档策略的行为差异经 HTTP 可观测（`POST /api/v1/knowledge/retrieve`）。
"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.core.embedding.factory as embedding_factory_module
import app.core.orchestrator as orchestrator_module
import app.knowledge.parsers as parsers_module
import app.knowledge.pipeline as pipeline_module
import app.knowledge.vector_store as vector_store_module
from app.config import settings
from app.core.intent import TeachingIntent
from app.core.registry import build
from app.db import SessionLocal, init_db
from app.db.models import Document, KnowledgeEdge, KnowledgeNode
from app.knowledge.chunking.base import Chunker
from app.knowledge.chunking.factory import CHUNKER_BUILDERS, get_chunker
from app.knowledge.chunking.paragraph import chunk_text
from app.knowledge.retrieval.base import Retriever
from app.knowledge.retrieval.factory import RETRIEVER_BUILDERS, get_retriever
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)

# ---- 收编前黄金值 ----
# 票 03 之前（commit ab39adf）的 retrieve_knowledge 在同一份种子数据上的输出，
# 逐字段抄录为黄金值：默认档必须与它完全一致。
GOLDEN_CONTEXT = (
    "=== 知识片段 ===\n参考片段\n\n片段二\n\n片段一\n\n"
    "=== 图谱关联知识点（按知识递进） ===\n【求导法则】求导法则内容"
)
GOLDEN_CHUNKS_ONLY_CONTEXT = "参考片段\n\n片段二\n\n片段一"
GOLDEN_SOURCES = ["参考.pdf", "讲义.pdf"]
# 参考片段原始距离最大（10.748 > 11.031 > 11.314），参考资料加权后仍排首
GOLDEN_HITS = [(3, "doc_ref", "参考片段"), (2, "doc_hit", "片段二"), (1, "doc_hit", "片段一")]
GOLDEN_DISTANCES = [10.748, 11.031, 11.314]
GOLDEN_GRAPH_NODES = [{"id": "node_b", "title": "求导法则", "content": "求导法则内容"}]

_CONCRETE_STRATEGY_IMPORTS = (
    "app.knowledge.chunking.paragraph",
    "app.knowledge.retrieval.vector",
    "app.knowledge.retrieval.search",
    "app.knowledge.retrieval.context",
)
_STRATEGY_PACKAGES = ("app/knowledge/chunking/", "app/knowledge/retrieval/")


class _FixedEmbedder:
    """确定性向量（以文本长度为特征，与 stub 同构）：排名完全可预期。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] * 8 for t in texts]


def _seed_rows() -> None:
    """资料行 + 知识点与关系边（幂等）：资料名可溯源，图谱邻接有内容可融合。"""
    init_db()
    db = SessionLocal()
    try:
        if db.get(Document, "doc_hit") is None:
            db.add_all(
                [
                    Document(
                        id="doc_hit",
                        user_id="default",
                        filename="讲义.pdf",
                        file_path="data/uploads/讲义.pdf",
                        file_type="pdf",
                        status="已完成",
                    ),
                    Document(
                        id="doc_ref",
                        user_id="default",
                        filename="参考.pdf",
                        file_path="data/uploads/参考.pdf",
                        file_type="pdf",
                        status="已完成",
                        is_reference=True,
                    ),
                ]
            )
        if db.get(KnowledgeNode, "node_a") is None:
            db.add_all(
                [
                    KnowledgeNode(
                        id="node_a",
                        user_id="default",
                        title="导数定义",
                        content="导数定义内容",
                        source_docs=["doc_hit"],
                    ),
                    KnowledgeNode(
                        id="node_b",
                        user_id="default",
                        title="求导法则",
                        content="求导法则内容",
                        source_docs=["doc_other"],
                    ),
                ]
            )
            db.flush()
            db.add(
                KnowledgeEdge(
                    user_id="default",
                    from_node="node_a",
                    to_node="node_b",
                    relation_type="前置依赖",
                )
            )
        db.commit()
    finally:
        db.close()


@pytest.fixture
def store(tmp_path) -> VectorStore:
    """同一份向量库种子：参考资料片段原始距离最大但被加权置首。"""
    vec_store = VectorStore(str(tmp_path / "v.db"))
    vec_store.add("doc_hit", ["片段一", "片段二"], [[1.0] * 8, [1.1] * 8])
    vec_store.add("doc_ref", ["参考片段"], [[1.2] * 8])
    return vec_store


@pytest.fixture(autouse=True)
def _strategy_seams(monkeypatch, store):
    """统一接缝：确定性向量化 + 本用例向量库 + 种子数据 + 策略工厂缓存清零。"""
    _seed_rows()
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: _FixedEmbedder())
    monkeypatch.setattr(vector_store_module, "VectorStore", lambda: store)
    get_chunker.cache_clear()
    get_retriever.cache_clear()
    yield
    get_chunker.cache_clear()
    get_retriever.cache_clear()


def _intent() -> TeachingIntent:
    return TeachingIntent(topic="导数", knowledge_points=["极限"])


def _retrieve_payload() -> dict:
    return {
        "intent": {"topic": "导数", "knowledge_points": ["极限"]},
        "k": 5,
        "reference_doc_ids": ["doc_ref"],
    }


def _retrieve_with(monkeypatch, strategy: str) -> dict:
    """按指定配置请求一次观测端点（改配置后清工厂缓存，与票 02 的工厂同一口径）。"""
    monkeypatch.setattr(settings, "retrieval_strategy", strategy)
    get_retriever.cache_clear()
    return client.post("/api/v1/knowledge/retrieve", json=_retrieve_payload()).json()


# ---- 分块策略 ----


class _MarkedChunker(Chunker):
    name = "marked"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def chunk(self, text: str) -> list[str]:
        self.seen.append(text)
        return ["新增分块实现切出的分块"]


async def test_new_chunker_impl_reaches_parse_pipeline(monkeypatch, store):
    """注册新分块实现 + 改配置：调用方（文档解析管道）一行未改，入库的就是新实现的切法。"""
    marked = _MarkedChunker()
    monkeypatch.setitem(CHUNKER_BUILDERS, "marked", lambda cfg: marked)
    monkeypatch.setattr(settings, "chunk_strategy", "marked")

    class _FakeParser:
        async def parse(self, path: str) -> str:
            return "解析出来的教学正文"

    async def _no_conflict(doc_id: str, text: str) -> int:
        return 0

    monkeypatch.setattr(parsers_module, "get_parser", lambda file_type: _FakeParser())
    monkeypatch.setattr(pipeline_module, "extract_and_save_knowledge", _no_conflict)

    db = SessionLocal()
    try:
        doc = Document(
            user_id="default",
            filename=f"待解析_{uuid.uuid4().hex[:6]}.pdf",
            file_path="data/uploads/x.pdf",
            file_type="pdf",
            status="处理中",
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    await pipeline_module.parse_document(doc_id)

    assert marked.seen == ["解析出来的教学正文"]  # 管道把解析正文交给了配置的分块策略
    indexed = [h["content"] for h in store.search([0.0] * 8, k=10)]
    assert "新增分块实现切出的分块" in indexed  # 新实现的切法直接入库，管道零改动


def test_default_chunker_is_legacy_chunking():
    """默认档 = 收编前的分块逻辑（逐字符一致），接口化的 Chunker 与纯函数同源。"""
    text = "\n\n".join(f"第{i}段：这是一段用于测试分段逻辑的教学内容文字" for i in range(30))

    assert settings.chunk_strategy == "paragraph"
    assert get_chunker().name == "paragraph"
    assert get_chunker().chunk(text) == chunk_text(text)


# ---- 检索策略：默认档与收编前一致 ----


async def test_default_retrieval_matches_pre_refactor_golden():
    """默认档与收编前逐字段一致：上下文、来源资料名、命中明细、融合知识点全部对齐黄金值。"""
    retriever = get_retriever()

    assert retriever.name == "vector_graph"  # 默认档 = 收编前的向量 + 图谱融合
    result = await retriever.retrieve(_intent(), reference_doc_ids=["doc_ref"])

    assert result.context == GOLDEN_CONTEXT
    assert result.sources == GOLDEN_SOURCES
    assert [(h.chunk_id, h.doc_id, h.content) for h in result.hits] == GOLDEN_HITS
    assert [round(h.distance, 3) for h in result.hits] == GOLDEN_DISTANCES
    assert result.graph_nodes == GOLDEN_GRAPH_NODES


async def test_default_retrieval_degrades_to_empty_without_embeddings(monkeypatch):
    """向量化失败时降级为空结果（既有行为）：不抛异常，也不残留半截上下文。"""

    class _BrokenEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embedding 服务不可用")

    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: _BrokenEmbedder())

    result = await get_retriever().retrieve(_intent(), reference_doc_ids=["doc_ref"])

    assert (result.context, result.sources, result.hits, result.graph_nodes) == ("", [], [], [])


# ---- 检索策略：纯向量档 ----


async def test_vector_strategy_drops_graph_keeps_sources_and_reference_boost(monkeypatch):
    """向量档：上下文只有命中分块；来源溯源与参考资料加权与默认档一致。"""
    monkeypatch.setattr(settings, "retrieval_strategy", "vector")
    retriever = get_retriever()

    assert retriever.name == "vector"
    result = await retriever.retrieve(_intent(), reference_doc_ids=["doc_ref"])

    assert result.context == GOLDEN_CHUNKS_ONLY_CONTEXT  # 无图谱段
    assert result.graph_nodes == []
    assert result.sources == GOLDEN_SOURCES  # 溯源不受策略影响
    assert [h.doc_id for h in result.hits] == ["doc_ref", "doc_hit", "doc_hit"]  # 加权仍生效


# ---- 两档差异经 HTTP 可观测 ----


def test_retrieve_endpoint_reports_what_was_hit():
    """只读观测端点回显本次命中：策略名 + 来源资料名 + 命中明细 + 融合知识点。"""
    r = client.post("/api/v1/knowledge/retrieve", json=_retrieve_payload())

    assert r.status_code == 200
    body = r.json()
    assert body["strategy"] == "vector_graph"
    assert body["sources"] == GOLDEN_SOURCES
    assert [h["content"] for h in body["hits"]] == ["参考片段", "片段二", "片段一"]
    assert body["graph_nodes"] == GOLDEN_GRAPH_NODES
    assert body["context"] == GOLDEN_CONTEXT


def test_two_strategies_differ_over_http(monkeypatch):
    """两次不同配置下的响应差异（默认档 vs `RETRIEVAL_STRATEGY=vector`）。"""
    fusion = _retrieve_with(monkeypatch, "vector_graph")
    vector = _retrieve_with(monkeypatch, "vector")
    print("vector_graph:", json.dumps(fusion, ensure_ascii=False))
    print("vector      :", json.dumps(vector, ensure_ascii=False))

    assert (fusion["strategy"], vector["strategy"]) == ("vector_graph", "vector")
    assert fusion["graph_nodes"] == GOLDEN_GRAPH_NODES and vector["graph_nodes"] == []
    assert "图谱关联知识点" in fusion["context"] and "图谱关联知识点" not in vector["context"]
    assert fusion["context"] != vector["context"]
    assert fusion["hits"] == vector["hits"]  # 命中分块与排名两档一致，差异只在图谱融合
    assert fusion["sources"] == vector["sources"]


# ---- 口径与不变式 ----


@pytest.mark.parametrize(
    ("factory", "setting_name", "available"),
    [
        (get_chunker, "chunk_strategy", "paragraph"),
        (get_retriever, "retrieval_strategy", "vector, vector_graph"),
    ],
)
def test_unknown_name_reports_available_implementations(
    factory, setting_name, available, monkeypatch
):
    monkeypatch.setattr(settings, setting_name, "nowhere")

    with pytest.raises(ValueError) as excinfo:
        factory()

    assert "nowhere" in str(excinfo.value)
    assert available in str(excinfo.value)


@pytest.mark.parametrize("name", ["vector", "vector_graph"])
def test_registered_retrievers_implement_the_interface(name):
    assert isinstance(build(RETRIEVER_BUILDERS, name, settings, "检索策略"), Retriever)


def test_registered_chunkers_implement_the_interface():
    assert all(
        isinstance(build(CHUNKER_BUILDERS, n, settings, "分块策略"), Chunker)
        for n in CHUNKER_BUILDERS
    )


def test_orchestrator_has_no_retrieval_details():
    """编排器不再持有检索细节：不碰向量库、图谱邻接、加权、溯源与上下文组装。"""
    source = Path(orchestrator_module.__file__).read_text(encoding="utf-8")

    for token in (
        "vector_store",
        "knowledge.graph",
        "assemble_context",
        "CONTEXT_BUDGET",
        "REFERENCE_DISTANCE",
        "_source_names",
    ):
        assert token not in source
    assert "get_retriever()" in source  # 只经工厂拿策略


def test_callers_only_depend_on_interface_and_factory():
    """调用方（策略包以外）只 import 接口与工厂，不 import 任何具体策略实现。"""
    backend = Path(orchestrator_module.__file__).resolve().parents[2]
    offenders: list[tuple[str, str]] = []
    for path in (backend / "app").rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if rel.startswith(_STRATEGY_PACKAGES):
            continue
        text = path.read_text(encoding="utf-8")
        offenders += [
            (rel, impl) for impl in _CONCRETE_STRATEGY_IMPORTS if f"import {impl}" in text
        ]
    assert offenders == []


def test_parse_pipeline_takes_chunker_from_factory():
    """分块调用点收编：解析管道不再直接调纯函数，只经工厂取策略。"""
    source = Path(pipeline_module.__file__).read_text(encoding="utf-8")

    assert "from app.knowledge.chunking.factory import get_chunker" in source
    assert "chunk_text" not in source
