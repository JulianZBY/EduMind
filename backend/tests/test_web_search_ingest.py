"""联网检索并入库（票 10，CONTEXT.md §4 词条）：三态 + 与上传资料共用同一条入库管道。

口径：
- 搜索结果 → 文献笔记（来源=网页）→ 分块 → 知识点提取 → 冲突检测（待审队列），
  与上传资料同一条管道（`pipeline.parse_document` 的文本入口），不另写第二套；
- 搜索能力未配置：503 + `provider_not_configured` 引导去设置页，不返回假结果、不建资料；
- 零结果：200 + `ingested=0`，知识库没有新增。

离线确定性：搜索 / 对话替身只在 tests/support（AGENTS.md 铁律），向量化走本地 hash 兜底。
"""

import uuid

from fastapi.testclient import TestClient

import app.knowledge.web_ingest as web_ingest_module
from app.db import init_db
from app.knowledge.graph import nodes_for_docs
from app.main import app
from tests.support.fakes import FakeSearch

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在

INGEST_URL = "/api/v1/knowledge/web-search/ingest"


def _web_documents() -> list[dict]:
    """知识库里全部网页来源资料（资料来源以文献笔记的 source 为准，file_type 是入口标记）。"""
    rows = client.get("/api/v1/documents").json()["documents"]
    return [d for d in rows if d["file_type"] == "网页"]


def _fake_results(suffix: str) -> list[dict]:
    """带唯一后缀的搜索结果：替身按正文行提取知识点标题，后缀唯一才不会撞上别的用例
    已入库的同名知识点（同名会被去重拦在图外，索引断言就空了）。"""
    return [
        {
            "title": f"a{suffix} 一次函数的图象与性质",
            "url": f"https://example.com/lesson/{suffix}",
            "snippet": f"{suffix} 一次函数 y=kx+b（k≠0）的图象是一条过定点的直线，k 决定倾斜方向。",
        },
        {
            "title": f"b{suffix} 二元一次方程组的解法",
            "url": f"https://example.com/system/{suffix}",
            "snippet": f"{suffix} 代入消元与加减消元是解二元一次方程组的两条基本路径。",
        },
    ]


def test_ingest_stores_results_as_web_notes_through_shared_pipeline(monkeypatch):
    """成功态：每条搜索结果一份网页资料，走与上传同一条管道落到终态。

    - 响应即时返回（status=处理中），入库在后台与上传解析同一套状态机里推进；
    - 文献笔记来源=网页，资料概要与知识点索引照常生成（对话替身在场）；
    - 标题 / URL / 摘要留痕：分块正文能回溯到来源网页。
    """
    suffix = uuid.uuid4().hex[:8]
    results = _fake_results(suffix)
    monkeypatch.setattr(web_ingest_module, "get_search", lambda: FakeSearch(results))

    r = client.post(INGEST_URL, json={"query": "一次函数", "k": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"] == "一次函数"
    assert body["ingested"] == 2
    assert [d["status"] for d in body["documents"]] == ["处理中", "处理中"]

    # TestClient 在响应返回前跑完后台入库：资料已按解析状态口径落到终态
    listing = {d["id"]: d for d in _web_documents()}
    for view in body["documents"]:
        row = listing[view["id"]]
        assert row["filename"] == view["filename"]
        detail = client.get(f"/api/v1/documents/{view['id']}").json()
        assert detail["status"] in ("已完成", "有冲突")
        assert detail["chunk_count"] >= 1
        note = detail["literature_note"]
        assert note["source"] == "网页"
        assert note["status"] == "已生成"
        assert note["summary"].strip(), "文献笔记的资料概要在对话替身在场时必须非空"
        assert note["knowledge_index"], "网页资料提取的知识点应与上传资料一样进索引"

    # 标题 / URL / 摘要三样都进了入库正文（分块与文献笔记共享同一份文本）
    first = client.get(f"/api/v1/documents/{body['documents'][0]['id']}").json()
    chunk_text = "".join(c["content"] for c in first["chunks"])
    for field in ("title", "url", "snippet"):
        assert results[0][field] in chunk_text


def test_zero_results_ingests_nothing(monkeypatch):
    """零结果态：200 + ingested=0，知识库没有新增（不是错误，也不放假资料）。"""
    monkeypatch.setattr(web_ingest_module, "get_search", lambda: FakeSearch([]))

    before = len(_web_documents())
    r = client.post(INGEST_URL, json={"query": "查不到的主题", "k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "查不到的主题"
    assert body["ingested"] == 0
    assert body["documents"] == []
    assert len(_web_documents()) == before


def test_unconfigured_search_returns_503_without_documents(monkeypatch):
    """未配置态：503 + provider_not_configured + 去设置页引导；不建任何资料。"""
    from app.config import settings
    from app.core.search.factory import get_search

    monkeypatch.setattr(settings, "search_provider", "")
    monkeypatch.setattr(settings, "bocha_api_key", "")
    get_search.cache_clear()
    before = len(_web_documents())
    try:
        r = client.post(INGEST_URL, json={"query": "一次函数", "k": 2})
    finally:
        get_search.cache_clear()

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "provider_not_configured"
    assert "设置" in detail["message"]
    assert len(_web_documents()) == before


def test_web_knowledge_goes_through_conflict_review(monkeypatch, _default_fake_llm):
    """冲突联动走既有替身接缝：网页知识点与库内旧知矛盾时进待审队列，不入图谱（ADR-0006）。"""
    suffix = uuid.uuid4().hex[:8]
    results = _fake_results(suffix)
    monkeypatch.setattr(web_ingest_module, "get_search", lambda: FakeSearch(results))

    # 首次入库：后缀唯一、无旧知可比，节点直接入图
    first = client.post(INGEST_URL, json={"query": "一次函数", "k": 2}).json()
    assert first["ingested"] == 2
    first_detail = client.get(f"/api/v1/documents/{first['documents'][0]['id']}").json()
    assert first_detail["status"] == "已完成"

    # 同一批结果再次入库：命中同名旧知且比对判矛盾 → 冲突待审，资料状态「有冲突」
    _default_fake_llm.conflict = True
    second = client.post(INGEST_URL, json={"query": "一次函数", "k": 2}).json()
    assert second["ingested"] == 2
    pending = client.get("/api/v1/conflicts", params={"status": "待审"}).json()["conflicts"]
    for view in second["documents"]:
        detail = client.get(f"/api/v1/documents/{view['id']}").json()
        assert detail["status"] == "有冲突"
        assert detail["conflict_count"] >= 1
        assert any(c["doc_id"] == view["id"] for c in pending), "网页资料的冲突要进待审队列"

        assert nodes_for_docs([view["id"]]) == [], "待审知识点不能进入图谱"
        assert detail["literature_note"]["knowledge_index"] == []


def test_explicit_bocha_without_key_also_returns_503(monkeypatch):
    from app.config import settings
    from app.core.search.factory import get_search

    monkeypatch.setattr(settings, "search_provider", "bocha")
    monkeypatch.setattr(settings, "bocha_api_key", "")
    get_search.cache_clear()
    try:
        response = client.post(INGEST_URL, json={"query": "一次函数"})
    finally:
        get_search.cache_clear()
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_not_configured"


def test_web_note_source_survives_unconfigured_llm(monkeypatch):
    from app.config import settings
    from app.core.llm.factory import get_llm

    monkeypatch.setattr(
        web_ingest_module, "get_search", lambda: FakeSearch(_fake_results("no-llm"))
    )
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "default_provider_instance", "")
    get_llm.cache_clear()
    try:
        response = client.post(INGEST_URL, json={"query": "一次函数"})
    finally:
        get_llm.cache_clear()
    assert response.status_code == 200
    for doc in response.json()["documents"]:
        detail = client.get(f"/api/v1/documents/{doc['id']}").json()
        assert detail["status"] == "已完成"
        assert detail["chunk_count"] > 0
        assert detail["literature_note"]["source"] == "网页"
        assert detail["literature_note"]["status"] == "未配置"
        assert detail["literature_note"]["summary"] == ""


def test_ingest_validates_query_and_count_before_search(monkeypatch):
    search = FakeSearch([])
    monkeypatch.setattr(web_ingest_module, "get_search", lambda: search)
    for body in ({"query": "  "}, {"query": "主题", "k": 0}, {"query": "主题", "k": 6}):
        assert client.post(INGEST_URL, json=body).status_code == 422
    assert search.queries == []
    assert client.post(INGEST_URL, json={"query": "  主题  "}).json()["query"] == "主题"
    assert search.queries == ["主题"]


def test_background_failure_remains_observable_in_knowledge_library(monkeypatch):
    """接收并非处理成功：同管道失败状态与原因在资料详情可见，网页来源不丢。"""
    from app.config import settings

    monkeypatch.setattr(
        web_ingest_module, "get_search", lambda: FakeSearch(_fake_results("failure"))
    )
    from app.knowledge.chunking.factory import get_chunker

    monkeypatch.setattr(settings, "chunk_strategy", "unknown-test-strategy")
    get_chunker.cache_clear()
    try:
        response = client.post(INGEST_URL, json={"query": "一次函数", "k": 1})
    finally:
        get_chunker.cache_clear()
    assert response.status_code == 200
    assert response.json()["documents"][0]["status"] == "处理中"
    doc_id = response.json()["documents"][0]["id"]
    detail = client.get(f"/api/v1/documents/{doc_id}").json()
    assert detail["status"] == "失败"
    assert detail["failure_reason"]
    assert detail["literature_note"]["source"] == "网页"
    assert detail["literature_note"]["status"] == "未生成"


def test_manual_ingest_does_not_modify_sessions_or_generated_artifacts(monkeypatch):
    """入库动作无会话／生成物副作用，查询知识库也不会自动联网。"""
    search = FakeSearch(_fake_results("isolation"))
    monkeypatch.setattr(web_ingest_module, "get_search", lambda: search)
    prep = client.post("/api/v1/sessions", json={}).json()
    before = client.get(f"/api/v1/sessions/{prep['id']}").json()
    artifacts_before = client.get("/api/v1/artifacts").json()
    client.get("/api/v1/documents")
    assert search.queries == []
    response = client.post(INGEST_URL, json={"query": "隔离检索", "k": 1})
    assert response.status_code == 200
    assert search.queries == ["隔离检索"]
    assert client.get(f"/api/v1/sessions/{prep['id']}").json() == before
    assert client.get("/api/v1/artifacts").json() == artifacts_before
