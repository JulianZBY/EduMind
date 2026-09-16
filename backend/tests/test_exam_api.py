"""试卷按需生成与题库入库测试（HTTP API 主接缝：stub 网关 + 直接种子数据）。

覆盖 ticket #7 验收项：
- 按需生成端点在 stub 模式下返回可解析的题目数组（题型覆盖选择/填空/简答）
- 每题含考查知识点标注；产物回读含试题与答案解析两部分
- 生成题目写入题库（来源=自编）并关联知识点（数据库状态断言）
"""

import uuid
from pathlib import Path

from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.core.llm.factory as factory_module
import app.generate.exam as exam_module
import app.knowledge.vector_store as vector_store_module
from app.core.llm.base import ChatResult, LLMProvider
from app.core.llm.providers.stub import StubProvider
from app.db import SessionLocal, init_db
from app.db.models import KnowledgeNode, Question, QuestionKnowledge
from app.knowledge.vector_store import VectorStore
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表、列与默认用户存在

OUTPUT_DIR = Path("data/output")

# StubProvider 固定试卷中题目考查的知识点（与 stub 响应约定一致，供种子节点对齐）
STUB_KNOWLEDGE_POINTS = ["TCP三次握手", "TCP四次挥手", "TCP滑动窗口"]


def _install_stub(monkeypatch, tmp_path) -> None:
    """stub 网关 + 空向量库：端点全链路不触外部服务，检索降级为空上下文。"""
    # exam.py 顶层绑定 get_llm（早绑定），factory 引用需逐模块替换
    monkeypatch.setattr(exam_module, "get_llm", lambda: StubProvider())
    # retrieve_knowledge 延迟 import factory.get_llm（晚绑定），替换工厂模块即可
    monkeypatch.setattr(factory_module, "get_llm", lambda: StubProvider())
    monkeypatch.setattr(
        vector_store_module, "VectorStore", lambda: VectorStore(str(tmp_path / "v.db"))
    )


def _seed_node(title: str) -> str:
    """直接种子 KnowledgeNode，返回节点 id（供题目-知识点关联断言）。"""
    db = SessionLocal()
    try:
        node = KnowledgeNode(user_id="default", title=title, content=f"{title}的完整描述")
        db.add(node)
        db.commit()
        return node.id
    finally:
        db.close()


def _generate(**overrides):
    payload = {"intent": {"topic": "TCP", "grade": "大二", "duration_minutes": 45}, **overrides}
    return client.post("/api/v1/exam/generate", json=payload)


def test_generate_returns_parseable_questions_in_stub_mode(monkeypatch, tmp_path):
    """验收 1：stub 模式下按需生成端点返回可解析题目数组，题型覆盖选择/填空/简答。"""
    _install_stub(monkeypatch, tmp_path)
    r = _generate()

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["questions"], list) and len(body["questions"]) >= 3
    for q in body["questions"]:
        assert q["type"] in {"选择", "填空", "简答"}
        assert q["content"]
        assert q["answer"]
        assert q["knowledge_point"]  # 每题含考查知识点标注
    assert {"选择", "填空", "简答"} <= {q["type"] for q in body["questions"]}
    assert body["filename"].endswith(".docx")
    assert body["bank_saved"] == len(body["questions"])


def test_exam_docx_readback_has_questions_and_analysis_parts(monkeypatch, tmp_path):
    """验收 2：产物回读含试题与答案解析两部分，试题行带考查知识点标注。"""
    _install_stub(monkeypatch, tmp_path)
    body = _generate().json()

    texts = [p.text for p in DocxDocument(OUTPUT_DIR / body["filename"]).paragraphs]
    assert texts[0] == "试卷"
    q_idx, a_idx = texts.index("试题"), texts.index("答案解析")
    assert q_idx < a_idx  # 试题在前，答案解析在后
    question_block = "\n".join(texts[q_idx + 1 : a_idx])
    analysis_block = "\n".join(texts[a_idx + 1 :])
    for q in body["questions"]:
        assert q["content"] in question_block
        assert q["knowledge_point"] in question_block  # 知识点标注进试卷
        assert q["answer"] in analysis_block


def test_questions_saved_to_bank_and_linked_to_knowledge(monkeypatch, tmp_path):
    """验收 3：生成题目写入题库（来源=自编）并关联知识点（数据库状态断言）。"""
    _install_stub(monkeypatch, tmp_path)
    seeded = {title: _seed_node(title) for title in STUB_KNOWLEDGE_POINTS}

    # 断言只针对本轮新生成的题目：同文件前序用例已往同一题库写过同 content 的行，
    # 按题目 id 排除存量行，测试不依赖库内历史状态（顺序无关、可重复跑）。
    db = SessionLocal()
    try:
        before_ids = {
            q.id
            for q in db.execute(select(Question).where(Question.source_type == "自编"))
            .scalars()
            .all()
        }
    finally:
        db.close()

    body = _generate().json()
    contents = {q["content"] for q in body["questions"]}

    db = SessionLocal()
    try:
        # 题库规模为演示级（小表）：ORM 取回后 Python 过滤，查询全部参数化
        rows = db.execute(select(Question).where(Question.source_type == "自编")).scalars().all()
        saved = [q for q in rows if q.content in contents and q.id not in before_ids]
        assert {q.content for q in saved} == contents  # 每道生成题目都入了题库

        question_ids = {q.id for q in saved}
        all_links = db.execute(select(QuestionKnowledge)).scalars().all()
        links = [link for link in all_links if link.question_id in question_ids]
        by_question: dict[str, set[str]] = {}
        for link in links:
            by_question.setdefault(link.question_id, set()).add(link.knowledge_id)
        for q in saved:
            linked = by_question.get(q.id, set())
            assert linked, f"题目「{q.content[:20]}…」未关联任何知识点"
        for title, node_id in seeded.items():
            assert node_id in {l.knowledge_id for l in links}, f"知识点「{title}」未被任何题目关联"
    finally:
        db.close()


def test_generate_returns_502_when_llm_output_unparseable(monkeypatch, tmp_path):
    """LLM 输出不可解析时端点明确失败（502），不落盘空试卷、不入库。"""

    class BadProvider(LLMProvider):
        async def chat(self, messages, **kwargs) -> ChatResult:
            return ChatResult(content="（模型输出异常）")

        async def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

    monkeypatch.setattr(factory_module, "get_llm", lambda: BadProvider())
    monkeypatch.setattr(
        vector_store_module, "VectorStore", lambda: VectorStore(str(tmp_path / "v.db"))
    )
    before = {p.name for p in OUTPUT_DIR.glob("exam_*.docx")} if OUTPUT_DIR.is_dir() else set()

    r = _generate(intent={"topic": f"TCP_{uuid.uuid4().hex[:6]}"})

    assert r.status_code == 502
    after = {p.name for p in OUTPUT_DIR.glob("exam_*.docx")} if OUTPUT_DIR.is_dir() else set()
    assert after == before  # 未新增落盘试卷
