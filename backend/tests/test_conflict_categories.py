"""冲突三类别与差异化审核动作（ADR-0004 在其上扩展：见 ADR-0006）。

主接缝：HTTP API + 直接种子数据（冲突记录、图谱表）。只断言响应与库里的数据变迁，
不断言内部函数调用。

范围说明：结构冲突与常识存疑的**检测逻辑尚未实现**（ADR-0006），
故这两类冲突在本文件里由种子数据造出——本票交付的是数据模型与审核动作。
"""

import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.db.engine import _ensure_sqlite_columns
from app.db.models import Conflict, KnowledgeEdge, KnowledgeNode
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在


def _sfx() -> str:
    return uuid.uuid4().hex[:6]


def _seed_node(title: str, content: str = "旧描述") -> str:
    db = SessionLocal()
    try:
        node = KnowledgeNode(user_id="default", title=title, content=content)
        db.add(node)
        db.commit()
        db.refresh(node)
        return node.id
    finally:
        db.close()


def _seed_edge(from_id: str, to_id: str, relation: str = "前置依赖") -> str:
    db = SessionLocal()
    try:
        edge = KnowledgeEdge(
            user_id="default", from_node=from_id, to_node=to_id, relation_type=relation
        )
        db.add(edge)
        db.commit()
        db.refresh(edge)
        return edge.id
    finally:
        db.close()


def _seed_conflict(
    new_knowledge: dict,
    existing_knowledge: dict | None = None,
    category: str | None = None,
    diff_description: str = "新旧知识相互矛盾",
    status: str = "待审",
) -> str:
    """种一条冲突记录；`category=None` 走模型默认值（定义冲突）。"""
    db = SessionLocal()
    try:
        conflict = Conflict(
            user_id="default",
            new_knowledge=new_knowledge,
            existing_knowledge=existing_knowledge,
            diff_description=diff_description,
            status=status,
        )
        if category is not None:
            conflict.category = category
        db.add(conflict)
        db.commit()
        db.refresh(conflict)
        return conflict.id
    finally:
        db.close()


def _conflict_fields(conflict_id: str) -> dict | None:
    db: Session = SessionLocal()
    try:
        row = db.get(Conflict, conflict_id)
        if row is None:
            return None
        return {
            "category": row.category,
            "status": row.status,
            "revised_content": row.revised_content,
            "review_action": row.review_action,
            "new_knowledge": dict(row.new_knowledge or {}),
        }
    finally:
        db.close()


def _nodes_by_title(title: str) -> list[dict]:
    db: Session = SessionLocal()
    try:
        rows = db.execute(select(KnowledgeNode).where(KnowledgeNode.title == title)).scalars()
        return [{"id": node.id, "content": node.content} for node in rows]
    finally:
        db.close()


def _graph_among(titles: set[str]) -> tuple[set[str], set[tuple[str, str, str]]]:
    """给定标题集合下的实际图谱：出现的标题 + 两端都在其中的关系（按标题表达）。"""
    db: Session = SessionLocal()
    try:
        nodes = (
            db.execute(select(KnowledgeNode).where(KnowledgeNode.title.in_(sorted(titles))))
            .scalars()
            .all()
        )
        title_by_id = {node.id: node.title for node in nodes}
        if not title_by_id:
            return set(), set()
        edges = (
            db.execute(
                select(KnowledgeEdge).where(
                    KnowledgeEdge.from_node.in_(sorted(title_by_id)),
                    KnowledgeEdge.to_node.in_(sorted(title_by_id)),
                )
            )
            .scalars()
            .all()
        )
        return (
            set(title_by_id.values()),
            {(title_by_id[e.from_node], title_by_id[e.to_node], e.relation_type) for e in edges},
        )
    finally:
        db.close()


def _list_conflicts(**params) -> list[dict]:
    r = client.get("/api/v1/conflicts", params=params)
    assert r.status_code == 200
    return r.json()["conflicts"]


def _entry(conflict_id: str, category: str | None = None) -> dict:
    rows = _list_conflicts(**({"category": category} if category else {}))
    for row in rows:
        if row["id"] == conflict_id:
            return row
    raise AssertionError(f"冲突未出现在列表里: {conflict_id}")


def _promised(outcome: dict) -> tuple[set[str], set[tuple[str, str, str]]]:
    """把一张终态图（节点 + 关系）换算成「标题集合 + 按标题表达的关系集合」。"""
    title_by_id = {node["id"]: node["title"] for node in outcome["nodes"]}
    edges = {
        (title_by_id[edge["from"]], title_by_id[edge["to"]], edge["relation_type"])
        for edge in outcome["edges"]
    }
    return set(title_by_id.values()), edges


# ---- 验收项 1：category 落库 + 存量数据回填 ----


def test_legacy_conflict_rows_are_backfilled_to_definition_category(tmp_path):
    """存量库（conflicts 表没有 category 列）迁移后：补列 + 老数据回填为定义冲突，且幂等。"""
    db_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE conflicts (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36),"
        " status VARCHAR(20), new_knowledge JSON)"
    )
    legacy.execute(
        "INSERT INTO conflicts (id, user_id, status, new_knowledge)"
        " VALUES ('c-legacy', 'default', '待审', '{\"title\": \"遗留冲突\"}')"
    )
    legacy.commit()
    legacy.close()

    legacy_engine = create_engine(f"sqlite:///{db_path}")
    try:
        _ensure_sqlite_columns(legacy_engine)
        _ensure_sqlite_columns(legacy_engine)  # 幂等：再跑一次不报错、结果不变
        with legacy_engine.connect() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(conflicts)")}
            assert {"category", "revised_content", "review_action"} <= columns
            row = conn.exec_driver_sql(
                "SELECT category, revised_content FROM conflicts WHERE id = 'c-legacy'"
            ).one()
        assert row[0] == "定义冲突", "存量冲突数据回填为定义冲突"
        assert row[1] is None
    finally:
        legacy_engine.dispose()


def test_new_conflict_rows_default_to_definition_category_and_list_exposes_it():
    """新库：检测产出的冲突落「定义冲突」；列表带 category 且可按类别过滤。"""
    title = f"默认类别_{_sfx()}"
    old_id = _seed_node(title)
    conflict_id = _seed_conflict(
        {"title": title, "content": "新描述"},
        {"id": old_id, "title": title, "content": "旧描述"},
    )
    row = _entry(conflict_id)
    assert row["category"] == "定义冲突"
    assert row["status"] == "待审"

    structure_id = _seed_conflict(
        {"title": f"结构_{_sfx()}", "content": "新描述"}, category="结构冲突"
    )
    common_id = _seed_conflict(
        {"title": f"常识_{_sfx()}", "content": "新描述"}, category="常识存疑"
    )
    filtered = _list_conflicts(category="结构冲突")
    assert {c["id"] for c in filtered} == {structure_id}
    assert all(c["category"] == "常识存疑" for c in _list_conflicts(category="常识存疑"))
    assert common_id in {c["id"] for c in _list_conflicts(category="常识存疑")}
    assert structure_id not in {c["id"] for c in _list_conflicts(category="定义冲突")}


# ---- 验收项 2：三类别的审核动作各有行为测试 ----


@pytest.mark.parametrize(
    ("action", "status"),
    [("接受新", "已接受"), ("保留旧", "已拒绝"), ("并存", "并存")],
)
def test_definition_conflict_three_choices_keep_existing_semantics(action, status):
    """定义冲突：三选一，终态一一对应，且记录下教师选的动作。"""
    title = f"定义冲突_{action}_{_sfx()}"
    old_id = _seed_node(title, "旧描述")
    conflict_id = _seed_conflict(
        {"title": title, "content": "新描述"},
        {"id": old_id, "title": title, "content": "旧描述"},
    )

    r = client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": action})
    assert r.status_code == 200
    assert r.json() == {
        "id": conflict_id,
        "category": "定义冲突",
        "status": status,
        "action": action,
    }

    rows = _nodes_by_title(title)
    if action == "接受新":
        assert len(rows) == 1 and rows[0]["content"] == "新描述" and rows[0]["id"] != old_id
    elif action == "保留旧":
        assert len(rows) == 1 and rows[0]["id"] == old_id and rows[0]["content"] == "旧描述"
    else:
        assert {row["content"] for row in rows} == {"旧描述", "新描述"}

    stored = _conflict_fields(conflict_id)
    assert stored is not None
    assert stored["status"] == status
    assert stored["review_action"] == action


def test_structure_conflict_accepts_three_choices():
    """结构冲突同样三选一：新知入图 / 丢弃 / 双留，动作集合与定义冲突一致。"""
    sfx = _sfx()
    old_title = f"结构冲突_{sfx}"
    new_title = f"结构冲突·新_{sfx}"
    old_id = _seed_node(old_title, "图谱现状里的旧知识点")
    conflict_id = _seed_conflict(
        {"title": new_title, "content": "新知识点"},
        {"id": old_id, "title": old_title, "content": "图谱现状里的旧知识点"},
        category="结构冲突",
    )

    r = client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": "并存"})
    assert r.status_code == 200
    assert r.json()["status"] == "并存"
    assert len(_nodes_by_title(old_title)) == 1
    assert [row["content"] for row in _nodes_by_title(new_title)] == ["新知识点"]


def test_common_sense_conflict_two_choices_and_reject():
    """常识存疑：照常入库 / 拒绝 两条出路，终态是 已接受 / 已拒绝。"""
    sfx = _sfx()
    accept_title = f"常识存疑·照常_{sfx}"
    reject_title = f"常识存疑·拒绝_{sfx}"
    accept_id = _seed_conflict(
        {"title": accept_title, "content": "可疑的原文"}, category="常识存疑"
    )
    reject_id = _seed_conflict(
        {"title": reject_title, "content": "可疑的原文"}, category="常识存疑"
    )

    r = client.post(f"/api/v1/conflicts/{accept_id}/review", json={"action": "照常入库"})
    assert r.status_code == 200
    assert r.json()["status"] == "已接受"
    assert [row["content"] for row in _nodes_by_title(accept_title)] == ["可疑的原文"]

    r = client.post(f"/api/v1/conflicts/{reject_id}/review", json={"action": "拒绝"})
    assert r.status_code == 200
    assert r.json()["status"] == "已拒绝"
    assert _nodes_by_title(reject_title) == [], "拒绝即不入库"

    stored = _conflict_fields(reject_id)
    assert stored is not None and stored["review_action"] == "拒绝"


# ---- 验收项 3：编辑修正后入库落的是修正后的内容 ----


def test_corrected_content_lands_in_graph_and_original_stays_on_record():
    """编辑修正后入库：入库正文 = 修正后的内容，原文留在冲突记录里（两条都可追溯）。"""
    sfx = _sfx()
    title = f"常识存疑·修正_{sfx}"
    original = "地球是宇宙的中心。"
    corrected = "太阳是太阳系的中心，地球绕太阳公转。"
    conflict_id = _seed_conflict({"title": title, "content": original}, category="常识存疑")

    r = client.post(
        f"/api/v1/conflicts/{conflict_id}/review",
        json={"action": "编辑修正后入库", "revised_content": corrected},
    )
    assert r.status_code == 200
    assert r.json() == {
        "id": conflict_id,
        "category": "常识存疑",
        "status": "已接受",
        "action": "编辑修正后入库",
    }
    assert [row["content"] for row in _nodes_by_title(title)] == [corrected], (
        "落库的是修正后的内容"
    )

    stored = _conflict_fields(conflict_id)
    assert stored is not None
    assert stored["revised_content"] == corrected, "修正后的内容也留在审核痕迹里"
    assert stored["new_knowledge"]["content"] == original, "原文留在冲突记录里"
    entry = _entry(conflict_id)
    assert entry["revised_content"] == corrected
    assert entry["review_action"] == "编辑修正后入库", "终态都是已接受，靠 review_action 分辨出路"


# ---- 验收项 4：结构冲突的三个终态图与实际裁决后的图谱变化一致 ----


@pytest.mark.parametrize(
    ("action", "status"),
    [("接受新", "已接受"), ("保留旧", "已拒绝"), ("并存", "并存")],
)
def test_structure_outcome_graph_matches_graph_after_review(action, status):
    """终态图承诺什么，裁决后图谱就变成什么样（邻域子图逐点逐边比对）。"""
    sfx = _sfx()
    old_title = f"结构冲突·旧_{sfx}"
    new_title = f"结构冲突·新_{sfx}"
    up_title = f"结构冲突·上游_{sfx}"
    down_title = f"结构冲突·下游_{sfx}"
    old_id = _seed_node(old_title, "图谱现状里的旧知识点")
    up_id = _seed_node(up_title, "上游知识点")
    down_id = _seed_node(down_title, "下游知识点")
    _seed_edge(up_id, old_id, "前置依赖")
    _seed_edge(old_id, down_id, "父子包含")
    conflict_id = _seed_conflict(
        {
            "title": new_title,
            "content": "新知识点",
            "relations": [
                {"from_title": new_title, "to_title": down_title, "relation": "推导关系"}
            ],
        },
        {"id": old_id, "title": old_title, "content": "图谱现状里的旧知识点"},
        category="结构冲突",
    )

    entry = _entry(conflict_id, category="结构冲突")
    preview = entry["structure_preview"]
    assert preview is not None, "结构冲突必须带「图谱现状 vs 三种终态」的图示数据"
    current_titles, current_edges = _promised(preview["current"])
    assert current_titles == {old_title, up_title, down_title}
    assert current_edges == {
        (up_title, old_title, "前置依赖"),
        (old_title, down_title, "父子包含"),
    }
    assert [outcome["action"] for outcome in preview["outcomes"]] == ["接受新", "保留旧", "并存"]
    outcome = next(item for item in preview["outcomes"] if item["action"] == action)
    assert outcome["status"] == status
    promised_titles, promised_edges = _promised(outcome)

    # 裁决前新知不入图谱（「待审」的意义）
    assert _nodes_by_title(new_title) == []

    r = client.post(f"/api/v1/conflicts/{conflict_id}/review", json={"action": action})
    assert r.status_code == 200
    assert r.json()["status"] == status

    actual_titles, actual_edges = _graph_among(promised_titles)
    assert actual_titles == promised_titles, "终态图上的节点 = 裁决后图谱里真的有的节点"
    assert actual_edges == promised_edges, "终态图上的关系 = 裁决后图谱里真的有的关系"


def test_structure_preview_is_absent_for_other_categories_and_after_review():
    """图示只对「待审的结构冲突」有意义：其它类别与已裁决的冲突不带它。"""
    definition_id = _seed_conflict(
        {"title": f"无图示_{_sfx()}", "content": "新描述"}, category="定义冲突"
    )
    assert _entry(definition_id)["structure_preview"] is None

    sfx = _sfx()
    old_title = f"结构冲突·已裁决_{sfx}"
    old_id = _seed_node(old_title)
    structure_id = _seed_conflict(
        {"title": f"结构冲突·已裁决新_{sfx}", "content": "新描述"},
        {"id": old_id, "title": old_title, "content": "旧描述"},
        category="结构冲突",
    )
    r = client.post(f"/api/v1/conflicts/{structure_id}/review", json={"action": "保留旧"})
    assert r.status_code == 200
    assert _entry(structure_id, category="结构冲突")["structure_preview"] is None


# ---- 动作集合按类别收窄 + 状态边界 ----


def test_action_not_in_category_keeps_conflict_pending():
    """动作不适用于该类别 = 422（请求语义错误），且冲突与图谱都保持原样。"""
    sfx = _sfx()
    title = f"动作收窄_{sfx}"
    old_id = _seed_node(title, "旧描述")
    definition_id = _seed_conflict(
        {"title": title, "content": "新描述"},
        {"id": old_id, "title": title, "content": "旧描述"},
    )
    r = client.post(f"/api/v1/conflicts/{definition_id}/review", json={"action": "照常入库"})
    assert r.status_code == 422
    assert "接受新" in str(r.json()["detail"])
    assert _nodes_by_title(title) == [{"id": old_id, "content": "旧描述"}]
    stored = _conflict_fields(definition_id)
    assert stored is not None and stored["status"] == "待审"

    common_id = _seed_conflict(
        {"title": f"动作收窄·常识_{sfx}", "content": "新描述"}, category="常识存疑"
    )
    r = client.post(f"/api/v1/conflicts/{common_id}/review", json={"action": "并存"})
    assert r.status_code == 422
    r = client.post(
        f"/api/v1/conflicts/{common_id}/review", json={"action": "编辑修正后入库"}
    )
    assert r.status_code == 422, "编辑修正后入库缺修正后的内容 = 请求体校验失败"
    stored = _conflict_fields(common_id)
    assert stored is not None and stored["status"] == "待审"


def test_review_is_idempotent_boundary_for_every_category():
    """裁决是幂等边界：同一冲突第二次提交 = 409，不同动作也不能绕过。"""
    common_id = _seed_conflict(
        {"title": f"重复裁决_{_sfx()}", "content": "新描述"}, category="常识存疑"
    )
    r = client.post(f"/api/v1/conflicts/{common_id}/review", json={"action": "照常入库"})
    assert r.status_code == 200
    r = client.post(f"/api/v1/conflicts/{common_id}/review", json={"action": "拒绝"})
    assert r.status_code == 409

    unknown = client.post(
        f"/api/v1/conflicts/{uuid.uuid4()}/review", json={"action": "照常入库"}
    )
    assert unknown.status_code == 404
    bad_action = client.post("/api/v1/conflicts/" + common_id + "/review", json={"action": "覆盖"})
    assert bad_action.status_code == 422
