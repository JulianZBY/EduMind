"""五类生成物的「修改意见」路径（票 08）：提纲 / 试卷 / 互动内容的修改与版本留痕。

只经 HTTP 缝断言**响应与数据变迁**（不断言任何内部函数调用），全链路走无 Key 的 stub 兜底
（`StubProvider`），因此本文件在无 `.env` 的环境下同样全绿。落盘经 conftest 的
`isolated_output_dir` 重定向到临时目录，不写 `backend/data/output`。

覆盖：
- 修改意见只作用于**所选生成物**，其余类别一个版本都不多（不推翻全局）；
- 带 `base_version_id` 的修改产出**版本号更高**的新版本，基线版本内容与文件都保持可取回；
- 「版本数据只有一个事实源」：修改响应回的版本 id 就是版本列表里的那一条（会话工作台与生成物区同源）；
- 试卷改后的题目仍入题库，可按考查知识点查到（复用题库查询，不另造一套）。
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.db.models import KnowledgeNode, Question
from app.main import app

client = TestClient(app)
init_db()  # 幂等：版本表 / 题库表在临时库里就位

# stub 兜底对话的固定意图（见 core/llm/providers/stub.py），每次生成都能走完「检索 → 生成」
TURN = "讲 TCP 三次握手，45 分钟，风格学术"
# StubProvider 固定试卷中题目考查的知识点（与 test_question_bank_api.py 同一份约定）
STUB_KNOWLEDGE_POINTS = ["TCP三次握手", "TCP四次挥手", "TCP滑动窗口"]


@pytest.fixture(autouse=True)
def _isolated_outputs(isolated_output_dir):
    """每条用例都会产出落盘文件：重定向到临时目录（不写 backend/data/output）。"""
    return isolated_output_dir


# ---- HTTP 助手 ----


def _create() -> str:
    r = client.post("/api/v1/sessions", json={"granularity": "快速"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _chat(session_id: str) -> None:
    payload = {"session_id": session_id, "messages": [{"role": "user", "content": TURN}]}
    r = client.post("/api/v1/chat", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["clarifying"] is False


def _groups(session_id: str) -> dict[str, dict]:
    r = client.get(f"/api/v1/sessions/{session_id}/artifacts")
    assert r.status_code == 200, r.text
    return {group["artifact_type"]: group for group in r.json()["groups"]}


def _detail(version_id: str) -> dict:
    r = client.get(f"/api/v1/artifacts/{version_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _download(version_id: str, **params) -> bytes:
    r = client.get(f"/api/v1/artifacts/{version_id}/download", params=params)
    assert r.status_code == 200, r.text
    return r.content


def _seed_all_knowledge_points() -> None:
    """种子 stub 试卷里出现的三个考查知识点对应的图谱节点（已存在则不重复加）。"""
    db = SessionLocal()
    try:
        titles = {row.title for row in db.execute(select(KnowledgeNode)).scalars().all()}
        for title in STUB_KNOWLEDGE_POINTS:
            if title not in titles:
                db.add(KnowledgeNode(user_id="default", title=title, content=f"{title}的完整描述"))
        db.commit()
    finally:
        db.close()


def _bank_ids() -> set[str]:
    """题库现有的题目 id：只用来圈出「本次改后新入库」的行（存量行内容一模一样）。"""
    db = SessionLocal()
    try:
        return {row.id for row in db.execute(select(Question)).scalars().all()}
    finally:
        db.close()


def _revise(session_id: str, base_version_id: str, path: str, body: dict) -> dict:
    """按修改意见重做所选生成物（以某一历史版本为基线），返回新版本信息。"""
    payload = {
        **body,
        "feedback": "按教师意见局部调整，别推翻其它内容",
        "session_id": session_id,
        "base_version_id": base_version_id,
    }
    r = client.post(f"/api/v1{path}", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ---- 提纲 ----


def test_revise_outline_from_a_historical_version_keeps_the_baseline_and_others():
    """以第 1 版提纲为基线修改：产出第 3 版（origin=修改、parent=第 1 版），其余类别一个版本都不多。"""
    session_id = _create()
    _chat(session_id)
    _chat(session_id)

    groups = _groups(session_id)
    assert [v["version"] for v in groups["提纲"]["versions"]] == [1, 2]
    baseline = groups["提纲"]["versions"][0]
    baseline_content = _detail(baseline["id"])["content"]
    baseline_bytes = _download(baseline["id"])
    assert baseline_content["text"], "第 1 版提纲要有正文快照"

    body = _revise(
        session_id,
        baseline["id"],
        "/revise/outline",
        {"text": baseline_content["text"]},
    )

    assert body["version"] == 3 and body["session_id"] == session_id
    assert body["filename"].endswith(".docx")
    assert body["filename"] != baseline["filename"]
    # 同一事实源：修改响应回的版本 id 就是版本列表里的那一条（生成物区据此画时间线）
    after = _groups(session_id)
    outline_versions = after["提纲"]["versions"]
    assert [v["version"] for v in outline_versions] == [1, 2, 3]
    assert after["提纲"]["current_version_id"] == body["version_id"]
    new_version = next(v for v in outline_versions if v["id"] == body["version_id"])
    assert new_version["origin"] == "修改"
    assert new_version["parent_id"] == baseline["id"]  # 由哪一版衍生而来
    # 修改意见只作用于所选生成物：课件 / 教案的版本列表没变
    assert [v["version"] for v in after["课件"]["versions"]] == [1, 2]
    assert [v["version"] for v in after["教案"]["versions"]] == [1, 2]
    # 基线版本保持可回看、可下载：内容快照与文件字节都没变
    assert _detail(baseline["id"])["content"] == baseline_content
    assert _download(baseline["id"]) == baseline_bytes
    # 新版本是独立的一份产出（各自一个落盘文件），内容回读得到
    assert _detail(body["version_id"])["content"]["text"] == body["text"]


# ---- 试卷 ----


def test_revise_exam_records_a_version_and_the_revised_questions_enter_the_bank():
    """试卷改后仍是可取的版本，且改后的题目入题库、可按考查知识点查到。"""
    _seed_all_knowledge_points()

    session_id = _create()
    for _ in range(2):
        r = client.post(
            "/api/v1/exam/generate",
            json={"intent": {"topic": "TCP"}, "n": 3, "session_id": session_id},
        )
        assert r.status_code == 200, r.text

    groups = _groups(session_id)
    assert [v["version"] for v in groups["试卷"]["versions"]] == [1, 2]
    baseline = groups["试卷"]["versions"][0]
    baseline_questions = _detail(baseline["id"])["content"]["questions"]
    baseline_bytes = _download(baseline["id"])
    assert baseline_questions, "第 1 版试卷要有题目快照"

    existing = _bank_ids()
    body = _revise(
        session_id,
        baseline["id"],
        "/revise/exam",
        {"questions": baseline_questions},
    )

    assert body["version"] == 3
    assert body["questions"], "改后仍要有题目"
    assert body["bank_saved"] == len(body["questions"])
    assert body["filename"].endswith(".docx")
    # 改后的题目确实入了题库，且带考查知识点（主考 / 涉及）
    new_ids = _bank_ids() - existing
    assert len(new_ids) == len(body["questions"]), "改后的题目应全部新入库"
    details = [
        client.get(f"/api/v1/questions/{question_id}").json() for question_id in sorted(new_ids)
    ]
    assert all(detail["source_type"] == "自编" for detail in details)
    assert all(detail["knowledge_points"] for detail in details)
    # 按考查知识点能查到（复用题库查询入口）
    listed = client.get(
        "/api/v1/questions", params={"knowledge_point": "TCP滑动窗口", "limit": 100}
    ).json()
    assert {item["id"] for item in listed["items"]} & new_ids
    # 版本树：第 1 版保持可取回（题目快照与文件都没变），新版本由它衍生
    after = _groups(session_id)
    assert after["试卷"]["current_version_id"] == body["version_id"]
    assert _detail(baseline["id"])["content"]["questions"] == baseline_questions
    assert _download(baseline["id"]) == baseline_bytes


# ---- 互动内容 ----


def test_revise_interactive_records_a_version_and_opens_inline():
    """互动内容改后产出新版本，且新版本可 inline 打开（新标签页试用同一份数据）。"""
    session_id = _create()
    for _ in range(2):
        r = client.post(
            "/api/v1/interactive/generate",
            json={"intent": {"topic": "TCP"}, "session_id": session_id},
        )
        assert r.status_code == 200, r.text

    groups = _groups(session_id)
    assert [v["version"] for v in groups["互动内容"]["versions"]] == [1, 2]
    baseline = groups["互动内容"]["versions"][0]
    baseline_html = _detail(baseline["id"])["content"]["html"]
    assert baseline_html.strip().lower().startswith("<!doctype")

    body = _revise(
        session_id,
        baseline["id"],
        "/revise/interactive",
        {"html": baseline_html},
    )

    assert body["version"] == 3 and body["filename"].endswith(".html")
    inline = client.get(
        f"/api/v1/artifacts/{body['version_id']}/download", params={"inline": True}
    )
    assert inline.status_code == 200, inline.text
    assert "attachment" not in inline.headers.get("content-disposition", "")
    assert inline.text.strip().lower().startswith("<!doctype")
    # 基线版本仍可取回（同一份 HTML，独立文件）
    assert _detail(baseline["id"])["content"]["html"] == baseline_html
    assert baseline["filename"] != body["filename"]


# ---- 边界：基线校验与「不带会话」的既有语义 ----


def test_revision_rejects_unknown_or_mismatched_baseline():
    """基线校验：未知版本 / 未知会话 404，拿别的类别的版本当基线 422。"""
    session_id = _create()
    _chat(session_id)
    word_version = _groups(session_id)["教案"]["versions"][0]

    unknown = client.post(
        "/api/v1/revise/outline",
        json={
            "text": "# 提纲",
            "feedback": "再细一点",
            "session_id": session_id,
            "base_version_id": str(uuid.uuid4()),
        },
    )
    assert unknown.status_code == 404, unknown.text

    no_session = client.post(
        "/api/v1/revise/outline",
        json={"text": "# 提纲", "feedback": "再细一点", "session_id": str(uuid.uuid4())},
    )
    assert no_session.status_code == 404, no_session.text

    mismatched = client.post(
        "/api/v1/revise/outline",
        json={
            "text": "# 提纲",
            "feedback": "再细一点",
            "session_id": session_id,
            "base_version_id": word_version["id"],
        },
    )
    assert mismatched.status_code == 422, mismatched.text


def test_revision_without_session_keeps_existing_behaviour():
    """不带会话标识时保持既有语义：只回新文件名与内容，不落版本记录。"""
    session_id = _create()
    _chat(session_id)

    body = client.post(
        "/api/v1/revise/interactive",
        json={"html": "<!doctype html><html><body>原互动内容</body></html>", "feedback": "换题型"},
    )
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["version_id"] is None
    assert payload["version"] is None
    assert payload["session_id"] is None
    # 该会话一个互动内容版本都不多（无会话即无归属）
    assert "互动内容" not in _groups(session_id)
