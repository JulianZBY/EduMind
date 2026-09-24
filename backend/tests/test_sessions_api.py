"""备课会话 API（票 05）：创建 / 列表 / 历史 / 重命名 / 删除，全部经 HTTP 缝。

事实源在服务端（ADR-0002）：这里只断言 HTTP 响应与库里的数据变迁，不断言内部函数调用。
落盘隔离沿用 conftest（DATABASE_URL / VECTORS_DB_PATH / UPLOAD_DIR 均指向临时目录）。
"""

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.db.models import PrepSession, SessionMessage
from app.main import app

client = TestClient(app)
init_db()  # 幂等：会话与消息表在临时库里就位


def _create(**payload) -> dict:
    r = client.post("/api/v1/sessions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _session_row(session_id: str) -> PrepSession | None:
    db = SessionLocal()
    try:
        return db.get(PrepSession, session_id)
    finally:
        db.close()


def _message_rows(session_id: str) -> list[SessionMessage]:
    db = SessionLocal()
    try:
        return (
            db.query(SessionMessage)
            .filter(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.seq)
            .all()
        )
    finally:
        db.close()


# ---- 创建 ----


def test_create_session_returns_teacher_facing_summary():
    """新建备课会话：标题、追问粒度、参考资料与创建时间都由服务端落库后回显。"""
    created = _create(
        title="一次函数（初二）",
        granularity="精细",
        reference_doc_ids=["doc-1", "doc-2"],
    )

    assert created["id"]
    assert created["title"] == "一次函数（初二）"
    assert created["granularity"] == "精细"
    assert created["reference_doc_ids"] == ["doc-1", "doc-2"]
    assert created["message_count"] == 0
    assert created["created_at"] and created["updated_at"]
    row = _session_row(created["id"])
    assert row is not None and row.title == "一次函数（初二）"


def test_create_session_defaults_title_and_granularity():
    """不传字段时给出可用默认：标题先占位，追问粒度为标准，参考资料为空。"""
    created = _create()

    assert created["title"] == "新的备课会话"
    assert created["granularity"] == "标准"
    assert created["reference_doc_ids"] == []


def test_create_session_rejects_unknown_granularity():
    """追问粒度只有三档（CONTEXT.md「追问粒度」），其余取值被拒。"""
    r = client.post("/api/v1/sessions", json={"granularity": "超精细"})
    assert r.status_code == 422


# ---- 列表 ----


def test_list_sessions_orders_recent_first_and_filters_by_keyword():
    """列表按最近使用倒序；携带关键词时按标题过滤，供会话列表检索使用。"""
    older = _create(title="三角函数入门")
    newer = _create(title="立体几何投影")

    listed = client.get("/api/v1/sessions").json()["sessions"]
    ids = [s["id"] for s in listed]
    assert ids.index(newer["id"]) < ids.index(older["id"])  # 新会话在前

    # 改名 = 最近使用：改过名的旧会话回到列表首位
    renamed = client.patch(f"/api/v1/sessions/{older['id']}", json={"title": "三角函数（修订）"})
    assert renamed.status_code == 200
    listed = client.get("/api/v1/sessions").json()["sessions"]
    assert listed[0]["id"] == older["id"]

    filtered = client.get("/api/v1/sessions", params={"q": "三角"}).json()["sessions"]
    assert [s["id"] for s in filtered] == [older["id"]]


# ---- 历史 ----


def test_history_returns_session_with_messages_in_order():
    """历史 = 会话本身 + 按序号排好的消息列表，教师换设备后据此完整回看。"""
    created = _create(title="一次函数")
    db = SessionLocal()
    try:
        prep = db.get(PrepSession, created["id"])
        assert prep is not None
        db.add_all(
            [
                SessionMessage(
                    session_id=prep.id,
                    user_id="default",
                    seq=1,
                    role="user",
                    content="给初二讲一次函数",
                ),
                SessionMessage(
                    session_id=prep.id,
                    user_id="default",
                    seq=2,
                    role="assistant",
                    content="还差一点信息：希望课件是什么风格？",
                    kind="澄清回复",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    body = client.get(f"/api/v1/sessions/{created['id']}").json()

    assert body["session"]["id"] == created["id"]
    assert body["session"]["message_count"] == 2
    assert [m["seq"] for m in body["messages"]] == [1, 2]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][1]["kind"] == "澄清回复"


def test_history_of_unknown_session_returns_404():
    """未知会话不静默返回空历史，而是 404（前端据此提示会话已不存在）。"""
    r = client.get("/api/v1/sessions/not-a-session")
    assert r.status_code == 404
    assert "会话不存在" in r.json()["detail"]


# ---- 重命名 ----


def test_rename_session_updates_title_and_settings():
    """重命名会话；同一端点也可改追问粒度与参考资料（会话设置）。"""
    created = _create(title="旧标题")

    renamed = client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={"title": "新标题", "granularity": "快速", "reference_doc_ids": ["doc-9"]},
    )

    assert renamed.status_code == 200
    body = renamed.json()
    assert (body["title"], body["granularity"], body["reference_doc_ids"]) == (
        "新标题",
        "快速",
        ["doc-9"],
    )
    row = _session_row(created["id"])
    assert row is not None and row.granularity == "快速"
    assert client.get(f"/api/v1/sessions/{created['id']}").json()["session"]["title"] == "新标题"


def test_rename_unknown_session_returns_404():
    r = client.patch("/api/v1/sessions/not-a-session", json={"title": "随便"})
    assert r.status_code == 404


def test_update_without_any_field_is_rejected():
    """空更新视为调用方出错：既不重命名也不改设置（422）。"""
    created = _create(title="保持不动")

    r = client.patch(f"/api/v1/sessions/{created['id']}", json={})

    assert r.status_code == 422
    row = _session_row(created["id"])
    assert row is not None and row.title == "保持不动"


def test_rename_to_blank_title_is_rejected():
    """标题不能改成空或全空白：会话列表里不该出现无名会话（422）。"""
    created = _create(title="有标题")

    r = client.patch(f"/api/v1/sessions/{created['id']}", json={"title": "   "})

    assert r.status_code == 422
    row = _session_row(created["id"])
    assert row is not None and row.title == "有标题"


# ---- 删除 ----


def test_delete_session_removes_session_and_messages():
    """删除会话后其消息一并消失，历史接口随之 404（不留孤儿消息）。"""
    created = _create(title="待删除")
    db = SessionLocal()
    try:
        db.add(
            SessionMessage(
                session_id=created["id"],
                user_id="default",
                seq=1,
                role="user",
                content="给初二讲一次函数",
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.delete(f"/api/v1/sessions/{created['id']}")

    assert r.status_code == 200
    assert r.json() == {"id": created["id"], "deleted": True}
    assert _session_row(created["id"]) is None
    assert _message_rows(created["id"]) == []
    assert client.get(f"/api/v1/sessions/{created['id']}").status_code == 404
    assert created["id"] not in [s["id"] for s in client.get("/api/v1/sessions").json()["sessions"]]


def test_delete_unknown_session_returns_404():
    r = client.delete("/api/v1/sessions/not-a-session")
    assert r.status_code == 404
