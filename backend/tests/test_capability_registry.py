"""能力注册统一：五项能力都是「接口 + 按配置选择的工厂」，换实现只改配置、调用方零改动。

每个用例往对应注册表加一个全新实现（注册表加一行）并只改配置名，然后从**调用方**
（HTTP 端点 / 知识库解析层 / 生成器）观察结果；再有一条不变式用例守住「调用方不
import 具体 provider 实现」。
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
import app.api.v1.knowledge as knowledge_module
import app.core.asr.factory as asr_factory_module
import app.core.embedding.factory as embedding_factory_module
import app.core.llm.factory as llm_factory_module
import app.core.parser.factory as pdf_factory_module
import app.core.search.factory as search_factory_module
from app.config import settings
from app.core.asr.base import Transcriber
from app.core.asr.factory import get_transcriber
from app.core.embedding.base import Embedder
from app.core.embedding.factory import get_embedder
from app.core.llm.base import ChatResult, LLMProvider
from app.core.llm.factory import get_llm
from app.core.parser.base import PdfParser
from app.core.parser.factory import get_pdf_parser
from app.core.search.base import WebSearch
from app.core.search.factory import get_search
from app.generate.outline import generate_outline
from app.knowledge.parsers.audio import AudioParser
from app.knowledge.parsers.pdf import PdfParser as KnowledgePdfParser
from app.knowledge.vector_store import VectorStore
from app.main import app as fastapi_app

client = TestClient(fastapi_app)

_CACHED_FACTORIES = (get_llm, get_embedder, get_search, get_pdf_parser, get_transcriber)

# 调用方（app/ 下除各能力自身包以外的模块）不得出现的具体实现 import
CONCRETE_IMPLEMENTATIONS = (
    "app.core.llm.providers",
    "app.core.embedding.stub",
    "app.core.embedding.hash",
    "app.core.embedding.openai_compat",
    "app.core.search.bocha",
    "app.core.search.stub",
    "app.core.parser.mineru",
    "app.core.parser.pypdf",
    "app.core.parser.fallback",
    "app.core.asr.paraformer",
    "app.core.asr.stub",
)
# 实现允许被 import 的位置：各能力自己的包（工厂 + 实现同处一层）
_CAPABILITY_PACKAGES = (
    "app/core/llm/",
    "app/core/embedding/",
    "app/core/search/",
    "app/core/parser/",
    "app/core/asr/",
)


@pytest.fixture(autouse=True)
def _fresh_factories():
    for cached in _CACHED_FACTORIES:
        cached.cache_clear()
    yield
    for cached in _CACHED_FACTORIES:
        cached.cache_clear()


# ---- 对话 ----


class _MarkedLLM(LLMProvider):
    name = "marked"

    async def chat(self, messages, **kwargs) -> ChatResult:
        return ChatResult(content="新增对话实现生成的提纲")


async def test_new_llm_impl_needs_no_caller_change(monkeypatch):
    monkeypatch.setitem(llm_factory_module.LLM_BUILDERS, "marked", lambda cfg: _MarkedLLM())
    monkeypatch.setattr(settings, "llm_provider", "marked")

    # 调用方：教学提纲生成（模块顶层 import get_llm，一行未改）
    assert await generate_outline({"topic": "TCP"}, "知识内容") == "新增对话实现生成的提纲"


# ---- 向量化 ----


class _MarkedEmbedder(Embedder):
    name = "marked"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return [[1.0] * 8 for _ in texts]


def test_new_embedder_impl_needs_no_caller_change(monkeypatch, tmp_path):
    embedder = _MarkedEmbedder()
    store = VectorStore(str(tmp_path / "v.db"))
    store.add("doc1", ["新增向量化实现命中的片段"], [[1.0] * 8])
    monkeypatch.setitem(
        embedding_factory_module.EMBEDDING_BUILDERS, "marked", lambda cfg: embedder
    )
    monkeypatch.setattr(settings, "embedding_provider", "marked")
    monkeypatch.setattr(knowledge_module, "VectorStore", lambda: store)

    # 调用方：检索端点（只认 Embedder 接口）
    r = client.post("/api/v1/knowledge/search", json={"query": "三次握手", "k": 1})

    assert r.status_code == 200
    assert embedder.calls == ["三次握手"]
    assert r.json()["hits"][0]["content"] == "新增向量化实现命中的片段"


# ---- 语音转写 ----


class _MarkedTranscriber(Transcriber):
    name = "marked"

    async def transcribe(self, file_path: str) -> str:
        return "新增转写实现"


async def test_new_transcriber_impl_needs_no_caller_change(monkeypatch):
    monkeypatch.setitem(
        asr_factory_module.ASR_BUILDERS, "marked", lambda cfg: _MarkedTranscriber()
    )
    monkeypatch.setattr(settings, "asr_provider", "marked")

    # 调用方：录音解析器（模块顶层 import get_transcriber，一行未改）
    assert await AudioParser().parse("讲座.wav") == "新增转写实现"


# ---- PDF 解析 ----


class _MarkedPdfParser(PdfParser):
    name = "marked"

    async def parse(self, pdf_path: str) -> str:
        return "新增 PDF 策略解析结果"


async def test_new_pdf_strategy_needs_no_caller_change(monkeypatch):
    monkeypatch.setitem(pdf_factory_module.PDF_BUILDERS, "marked", lambda cfg: _MarkedPdfParser())
    monkeypatch.setattr(settings, "pdf_strategy", "marked")

    # 调用方：知识库 PDF 解析器（只依赖 PdfParser 接口与工厂）
    assert await KnowledgePdfParser().parse("讲义.pdf") == "新增 PDF 策略解析结果"


# ---- 网络搜索 ----


class _MarkedSearch(WebSearch):
    name = "marked"

    async def search(self, query: str, count: int = 5, summary: bool = False) -> list[dict]:
        return [{"title": "新增搜索实现", "url": "https://example.com", "snippet": query}]


def test_new_search_impl_needs_no_caller_change(monkeypatch):
    monkeypatch.setitem(
        search_factory_module.SEARCH_BUILDERS, "marked", lambda cfg: _MarkedSearch()
    )
    monkeypatch.setattr(settings, "search_provider", "marked")

    # 调用方：网络搜索端点（模块顶层 import get_search，一行未改）
    r = client.post("/api/v1/knowledge/web-search", json={"query": "三次握手", "k": 1})

    assert r.status_code == 200
    assert r.json()["results"][0]["title"] == "新增搜索实现"


# ---- 注册表口径与不变式 ----


@pytest.mark.parametrize(
    ("factory", "setting_name"),
    [
        (get_llm, "llm_provider"),
        (get_embedder, "embedding_provider"),
        (get_transcriber, "asr_provider"),
        (get_pdf_parser, "pdf_strategy"),
        (get_search, "search_provider"),
    ],
)
def test_unknown_name_reports_available_implementations(factory, setting_name, monkeypatch):
    monkeypatch.setattr(settings, setting_name, "nowhere")
    with pytest.raises(ValueError, match="可选"):
        factory()


def test_callers_do_not_import_concrete_implementations():
    """不变式：调用方只依赖接口 + 工厂，具体实现只在各能力自己的包内被 import。"""
    src_root = Path(app.__file__).parent
    offenders: list[str] = []
    for path in src_root.rglob("*.py"):
        rel = path.relative_to(src_root.parent).as_posix()
        if any(rel.startswith(prefix) for prefix in _CAPABILITY_PACKAGES):
            continue
        source = path.read_text(encoding="utf-8")
        for module in CONCRETE_IMPLEMENTATIONS:
            if re.search(rf"^\s*(from|import)\s+{re.escape(module)}\b", source, re.MULTILINE):
                offenders.append(f"{rel}: {module}")
    assert offenders == [], f"调用方不得 import 具体实现：{offenders}"
