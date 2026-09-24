"""题库查询与题目详情测试（HTTP API 主接缝：stub 网关 + 直接种子数据）。

覆盖票 12 验收项与票 01 登记的遗留：
- 按考查知识点筛选，经 HTTP 缝断言
- 试卷生成入库的题目即时出现在列表（同一轮请求里生成后即查）
- 题目详情呈现题型 / 答案 / 来源 / 考查知识点
- OpenAPI「题库」tag 分组已声明且有描述（此前只有试卷生成入口、没有查题入口）
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.core.embedding.factory as embedding_factory_module
import app.generate.exam as exam_module
import app.knowledge.vector_store as vector_store_module
from app.core.embedding.stub import StubEmbedder
from app.core.llm.providers.stub import StubProvider
from app.db import SessionLocal, init_db
from app.db.models import KnowledgeNode, Question
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表、列与默认用户存在

# StubProvider 固定试卷中题目考查的知识点（与 test_exam_api.py 同一份约定）
STUB_KNOWLEDGE_POINTS = ["TCP三次握手", "TCP四次挥手", "TCP滑动窗口"]


def _install_stub(monkeypatch, tmp_path) -> None:
    """stub 网关 + 空向量库：生成与查询都不触外部服务，检索降级为空上下文。"""
    monkeypatch.setattr(exam_module, "get_llm", lambda: StubProvider())
    monkeypatch.setattr(embedding_factory_module, "get_embedder", lambda: StubEmbedder())
    monkeypatch.setattr(
        vector_store_module, "VectorStore", lambda: VectorStore(str(tmp_path / "v.db"))
    )


def _seed_node(title: str) -> str:
    """直接种子 KnowledgeNode，让生成题目的考查知识点能挂上图谱节点。"""
    db = SessionLocal()
    try:
        node = KnowledgeNode(user_id="default", title=title, content=f"{title}的完整描述")
        db.add(node)
        db.commit()
        return node.id
    finally:
        db.close()


def _seed_all_knowledge_points() -> dict[str, str]:
    return {title: _seed_node(title) for title in STUB_KNOWLEDGE_POINTS}


def _bank_ids() -> set[str]:
    """题库现有的题目 id。

    只用来圈出「本轮新入库」的行：同文件前序用例会写出同一份 stub 题目（内容一模一样），
    不按 id 区分就会把没有考查知识点关联的存量行当成新行（顺序无关、可重复跑）。
    """
    db = SessionLocal()
    try:
        return {row.id for row in db.execute(select(Question)).scalars().all()}
    finally:
        db.close()


def _generate() -> dict:
    """一键生成试卷：题目同侧入库（来源=自编）。"""
    r = client.post(
        "/api/v1/exam/generate",
        json={"intent": {"topic": "TCP", "grade": "大二"}, "n": 3},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _list(**params) -> dict:
    r = client.get("/api/v1/questions", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_list_narrows_to_the_examined_knowledge_point(monkeypatch, tmp_path):
    """验收 1：按考查知识点筛选经 HTTP 缝成立——筛出来的题都考这个知识点，别的题被排除。"""
    _install_stub(monkeypatch, tmp_path)
    _seed_all_knowledge_points()
    generated = _generate()
    # stub 里「TCP滑动窗口」只被其中一道题主考（另两题考三次握手/四次挥手）
    target = [q for q in generated["questions"] if q["knowledge_point"] == "TCP滑动窗口"]
    assert target, "stub 题目里应有以 TCP滑动窗口 为考查知识点的题"

    body = _list(knowledge_point="TCP滑动窗口", limit=100)

    assert body["knowledge_points"], "列表要回带全部筛选项（全量考查知识点 + 题目数）"
    assert {"TCP三次握手", "TCP四次挥手", "TCP滑动窗口"} <= {
        item["title"] for item in body["knowledge_points"]
    }
    assert body["items"], "筛出来的题目不应为空"
    for item in body["items"]:
        titles = {point["title"] for point in item["knowledge_points"]}
        assert titles == {"TCP滑动窗口"}, f"筛选项外的知识点混进来了：{titles}"
        assert item["content"] == target[0]["content"]
    assert body["total"] == len(body["items"])

    # 同一批题目里，考别的知识点的题被这次筛选排除（证明是收窄而不是全量返回）
    unfiltered = {item["content"] for item in _list(limit=100)["items"]}
    assert unfiltered - {item["content"] for item in body["items"]}


def test_list_returns_empty_for_knowledge_point_without_questions(monkeypatch, tmp_path):
    """筛了没人考的知识点就返回空列表（不是全量、也不是报错）。"""
    _install_stub(monkeypatch, tmp_path)
    _generate()

    body = _list(knowledge_point=f"没有题目的知识点-{uuid.uuid4().hex[:6]}")

    assert body["items"] == []
    assert body["total"] == 0


def test_generated_questions_are_listable_immediately(monkeypatch, tmp_path):
    """验收 2：试卷生成入库的题目立即出现在列表，且排在最新一页（入库时间倒序）。"""
    _install_stub(monkeypatch, tmp_path)
    _seed_all_knowledge_points()
    before = _bank_ids()
    generated = _generate()
    contents = {q["content"] for q in generated["questions"]}

    body = _list(limit=100)
    fresh = [item for item in body["items"] if item["id"] not in before]

    assert {item["content"] for item in fresh} == contents, "刚入库的题目必须立刻可查"
    assert body["items"][0]["id"] not in before, "最新入库的题目排在第一页首位"
    for item in fresh:
        assert item["source_type"] == "自编"  # 来源：试卷生成
        assert item["type"] in {"选择", "填空", "简答", "综合"}
        assert item["knowledge_points"], "每道生成题目都带考查知识点"


def test_list_paginates_and_caps_page_size(monkeypatch, tmp_path):
    """分页与上限：limit 决定本页条数，offset 跳过已看过的题，越界参数由框架拦下。"""
    _install_stub(monkeypatch, tmp_path)
    _generate()
    total = _list(limit=1)["total"]
    assert total >= 1

    first = _list(limit=1)
    assert len(first["items"]) == 1
    assert first["limit"] == 1 and first["offset"] == 0
    assert first["total"] == total

    second = _list(limit=1, offset=1)
    assert len(second["items"]) == 1
    assert second["items"][0]["id"] != first["items"][0]["id"]

    assert _list(offset=total)["items"] == []  # 翻过头是空页，不是报错

    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert client.get("/api/v1/questions", params=bad).status_code == 422


def test_detail_shows_type_answer_source_and_knowledge_points(monkeypatch, tmp_path):
    """验收 3：详情呈现题型 / 答案 / 来源 / 考查知识点。"""
    _install_stub(monkeypatch, tmp_path)
    _seed_all_knowledge_points()
    before = _bank_ids()
    generated = _generate()
    contents = {q["content"] for q in generated["questions"]}
    item = next(x for x in _list(limit=100)["items"] if x["id"] not in before)

    r = client.get(f"/api/v1/questions/{item['id']}")

    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["id"] == item["id"]
    assert detail["type"] in {"选择", "填空", "简答", "综合"}
    assert detail["content"] in contents
    assert detail["answer"], "详情必须给出答案"
    assert detail["source_type"] == "自编"  # 来源
    assert detail["created_at"]  # 入库时间
    assert detail["knowledge_points"], "详情必须给出考查知识点"
    for point in detail["knowledge_points"]:
        assert point["title"] in STUB_KNOWLEDGE_POINTS
        assert point["weight"] in {"主考", "涉及"}


def test_detail_returns_404_for_unknown_question():
    """题目不存在时 404（不是空对象）：前端据此区分「题目没了」与「题目是空的」。"""
    r = client.get(f"/api/v1/questions/{uuid.uuid4()}")

    assert r.status_code == 404
    assert r.json()["detail"] == "题目不存在"


def test_question_bank_group_is_declared_and_used():
    """票 01 遗留：OpenAPI「题库」分组此前缺席，现在既被声明也被端点使用且有描述。"""
    schema = app.openapi()
    declared = {tag["name"]: tag for tag in schema.get("tags") or []}

    assert "题库" in declared
    assert (declared["题库"].get("description") or "").strip()

    tagged = [
        (path, method)
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if "题库" in (operation.get("tags") or [])
    ]
    assert {"/api/v1/questions", "/api/v1/questions/{question_id}"} <= {
        path for path, _ in tagged
    }
    for path, item in schema["paths"].items():
        for operation in item.values():
            if "题库" in (operation.get("tags") or []):
                assert operation.get("response_model") or operation.get("responses")
                assert operation.get("responses", {}).get("422"), f"{path} 缺 422 说明"


def test_list_rows_do_not_carry_the_answer(monkeypatch, tmp_path):
    """列表是工作台密度的题目行（不含答案）；答案只在详情里给出。"""
    _install_stub(monkeypatch, tmp_path)
    generated = _generate()
    contents = {q["content"] for q in generated["questions"]}
    item = next(x for x in _list(limit=100)["items"] if x["content"] in contents)

    assert "answer" not in item
    assert client.get(f"/api/v1/questions/{item['id']}").json()["answer"]
