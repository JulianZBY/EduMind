"""知识冲突检测与教师审核（ADR-0006 自述本轮范围，在其上扩展见 ADR-0004）：

冲突分三类别（CONTEXT.md 第 6 节）：定义冲突 / 结构冲突 / 常识存疑。
**检测只做定义冲突**：同名精确匹配 + embedding 相似度近名预筛（阈值内候选交 LLM 比对，
复用 sqlite-vec 标题索引）；冲突入待审队列，审核前新节点不入知识图谱。
**结构冲突与常识存疑的检测逻辑尚未实现**，本轮只落数据模型与审核动作
（审核动作按类别差异化，见 ACTIONS_BY_CATEGORY）。
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.core.embedding.factory import get_embedder
from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.llm.parsing import parse_json
from app.db import SessionLocal
from app.db.models import Conflict, KnowledgeEdge, KnowledgeNode
from app.knowledge.vector_store import VectorStore

_COMPARE_PROMPT = """判断两段知识描述是否相互矛盾（定义冲突）。

旧知识：__OLD__

新知识：__NEW__

只输出 JSON，不要其他文字：
{"conflict": true 或 false, "description": "一句话说明差异或矛盾点"}
"""

# 教师三选一（与 Conflict.status 终态对应：接受新→已接受、保留旧→已拒绝、并存→并存）
REVIEW_ACTIONS = ("接受新", "保留旧", "并存")

# 冲突类别（CONTEXT.md 第 6 节）。类别是检测来源的标记，不能由裁决动作反推。
CONFLICT_CATEGORIES = ("定义冲突", "结构冲突", "常识存疑")

# 动作按类别收窄（ADR-0004）：前两类共用三选一；常识存疑是两选一 + 编辑修正后入库。
ACTIONS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "定义冲突": REVIEW_ACTIONS,
    "结构冲突": REVIEW_ACTIONS,
    "常识存疑": ("照常入库", "拒绝", "编辑修正后入库"),
}

# 动作 → 冲突终态。一个终态可对应多个动作：常识存疑的两条入库出路都落「已接受」，
# 故教师选的动作另存在 Conflict.review_action 里（只靠 status 分不出走了哪条出路）。
STATUS_BY_ACTION = {
    "接受新": "已接受",
    "并存": "并存",
    "照常入库": "已接受",
    "编辑修正后入库": "已接受",
    "保留旧": "已拒绝",
    "拒绝": "已拒绝",
}

# 知识点之间的四种关系（CONTEXT.md 第 5 节）：新知自带的关系只认这四种，其余不入图。
RELATION_TYPES = ("前置依赖", "父子包含", "推导关系", "相关关联")

# 结构冲突终态图里给新知的占位节点 id（真实 id 要等裁决入库后才生成）。
NEW_NODE_ID = "__new__"


class ActionNotAllowed(ValueError):
    """动作不属于该类别的动作集合（请求语义错误，路由层映射为 422）。

    与「已审核」的状态冲突（409）分开：前者与冲突当前状态无关，换一条同类冲突也一样不行。
    """


async def compare_content(old: str, new: str) -> dict:
    """LLM 判断两段知识是否矛盾。"""
    llm = get_llm()
    prompt = _COMPARE_PROMPT.replace("__OLD__", old[:2000]).replace("__NEW__", new[:2000])
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    return parse_json(result.content)


async def detect_conflicts(
    user_id: str, nodes: list[dict], doc_id: str | None = None
) -> tuple[list[dict], list[dict]]:
    """检测新节点与已有知识的定义冲突，冲突写入待审队列。

    返回 (待审节点列表, 同名重复节点列表)，调用方均不得将其入库：
    - 待审节点：与旧知识矛盾，等教师三选一审核；
    - 同名重复节点：同名且比对无矛盾（同一知识的重述），去重不入库，
      保持图谱中无重复同名节点。
    """
    db = SessionLocal()
    store = VectorStore()
    embedder = get_embedder()
    try:
        pending: list[dict] = []
        duplicates: list[dict] = []
        seen_titles: set[str] = set()
        for n in nodes:
            title = (n.get("title") or "").strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            candidates: dict[str, KnowledgeNode] = {}
            exact = (
                db.query(KnowledgeNode)
                .filter(KnowledgeNode.user_id == user_id, KnowledgeNode.title == title)
                .first()
            )
            if exact:
                candidates[exact.id] = exact
            # 近名预筛：标题向量阈值内候选（同名已入 candidates，按 id 去重）
            emb = (await embedder.embed([title]))[0]
            for hit in store.search_node_titles(emb, k=5):
                if hit["distance"] > settings.conflict_distance_threshold:
                    continue
                node = db.get(KnowledgeNode, hit["node_id"])
                if node is not None and node.user_id == user_id:
                    candidates.setdefault(node.id, node)

            conflicted = False
            is_duplicate = False
            for old in candidates.values():
                verdict = await compare_content(old.content, n.get("content", ""))
                if verdict.get("conflict"):
                    db.add(
                        Conflict(
                            user_id=user_id,
                            doc_id=doc_id,
                            category="定义冲突",
                            new_knowledge=n,
                            existing_knowledge={
                                "id": old.id,
                                "title": old.title,
                                "content": old.content,
                            },
                            diff_description=verdict.get("description", ""),
                            status="待审",
                        )
                    )
                    pending.append(n)
                    conflicted = True
                    break
                if old.title == title:
                    is_duplicate = True
            if not conflicted and is_duplicate:
                duplicates.append(n)
        db.commit()
        return pending, duplicates
    finally:
        db.close()


async def resolve_conflict(
    conflict_id: str, action: str, revised_content: str | None = None
) -> dict:
    """教师裁决待审冲突，返回 {"id", "category", "status", "action"}。

    动作集合按类别收窄（ACTIONS_BY_CATEGORY）：

    - 定义冲突 / 结构冲突（三选一）：接受新 = 新节点替换旧节点、旧节点的边重挂到新节点；
      保留旧 = 丢弃新知、图谱不动；并存 = 新旧双节点保留、差异说明留在冲突记录里；
    - 常识存疑（两选一 + 编辑修正后入库）：照常入库 = 按原文入库；拒绝 = 不让它进库；
      编辑修正后入库 = 落库的是**修正后的内容**（revised_content），原文留在冲突记录里。

    结构冲突的新知可自带关系（`new_knowledge["relations"]`，端点按标题解析）：
    端点在被替换的旧节点上时改挂到新知，详见 `_apply_proposed_relations`。
    """
    db = SessionLocal()
    try:
        conflict = db.get(Conflict, conflict_id)
        if conflict is None:
            raise LookupError(f"冲突不存在: {conflict_id}")
        if conflict.status != "待审":
            raise ValueError(f"该冲突已审核: {conflict.status}")

        category = conflict.category or "定义冲突"
        allowed = ACTIONS_BY_CATEGORY.get(category)
        if allowed is None:
            raise ActionNotAllowed(f"未知冲突类别: {category}")
        if action not in allowed:
            raise ActionNotAllowed(f"{category}的动作是 {' / '.join(allowed)}，不接受: {action}")

        old_id = (conflict.existing_knowledge or {}).get("id")
        old = db.get(KnowledgeNode, old_id) if old_id else None

        if action == "接受新":
            node = await _insert_node(db, conflict, inherit=old)
            if old is not None:
                _rehang_edges(db, old, node)
                db.delete(old)
                VectorStore().remove_node_title(old.id)
            _apply_proposed_relations(db, conflict, node, replaced_title=old.title if old else None)
        elif action == "并存":
            node = await _insert_node(db, conflict)
            _apply_proposed_relations(db, conflict, node)
        elif action == "照常入库":
            await _insert_node(db, conflict)
        elif action == "编辑修正后入库":
            revised = (revised_content or "").strip()
            if not revised:
                # 路由层已用请求体校验拦住，这里是服务层兜底（调用方绕过 API 时不静默丢内容）
                raise ActionNotAllowed("编辑修正后入库需要修正后的内容")
            await _insert_node(db, conflict, content=revised)
            conflict.revised_content = revised
        # 剩下的 保留旧 / 拒绝：丢弃新知（新节点从未入图，无需回滚），图谱不动

        conflict.status = STATUS_BY_ACTION[action]
        conflict.review_action = action
        db.commit()
        return {
            "id": conflict.id,
            "category": category,
            "status": conflict.status,
            "action": action,
        }
    finally:
        db.close()


def _rehang_edges(db: Session, old: KnowledgeNode, node: KnowledgeNode) -> None:
    """把旧节点上的关系边改挂到新节点：接受新会**移动边**而不是重建边。"""
    db.query(KnowledgeEdge).filter(KnowledgeEdge.from_node == old.id).update({"from_node": node.id})
    db.query(KnowledgeEdge).filter(KnowledgeEdge.to_node == old.id).update({"to_node": node.id})


def _node_ids_by_title(db: Session, user_id: str) -> dict[str, str]:
    """标题 → 知识点 id（同名取先入库的那个），供结构冲突的关系端点按标题解析。"""
    rows = db.query(KnowledgeNode.id, KnowledgeNode.title).filter(KnowledgeNode.user_id == user_id)
    mapping: dict[str, str] = {}
    for node_id, title in rows:
        mapping.setdefault(title, node_id)
    return mapping


def _apply_proposed_relations(
    db: Session, conflict: Conflict, node: KnowledgeNode, replaced_title: str | None = None
) -> None:
    """把新知自带的关系落进图谱（结构冲突）：端点按标题解析。

    - 指向被替换旧节点的关系改挂到新知（与「接受新」一致：「旧知识点的位置换成了新知」）；
    - 只认 CONTEXT.md 的四种关系；端点解析不到或自环的关系不入图（不留悬空连线）；
    - 已存在的关系不重复插入（幂等保护）。
    """
    relations = (conflict.new_knowledge or {}).get("relations") or []
    if not relations:
        return
    title_to_id = _node_ids_by_title(db, conflict.user_id)
    title_to_id[node.title] = node.id
    if replaced_title:
        title_to_id[replaced_title] = node.id
    for relation in relations:
        relation_type = (relation.get("relation") or "").strip()
        if relation_type not in RELATION_TYPES:
            continue
        from_id = title_to_id.get((relation.get("from_title") or "").strip())
        to_id = title_to_id.get((relation.get("to_title") or "").strip())
        if not from_id or not to_id or from_id == to_id:
            continue
        exists = (
            db.query(KnowledgeEdge)
            .filter(
                KnowledgeEdge.from_node == from_id,
                KnowledgeEdge.to_node == to_id,
                KnowledgeEdge.relation_type == relation_type,
            )
            .first()
        )
        if exists is None:
            db.add(
                KnowledgeEdge(
                    user_id=conflict.user_id,
                    from_node=from_id,
                    to_node=to_id,
                    relation_type=relation_type,
                )
            )


def _node_ref(node: KnowledgeNode) -> dict:
    """图示里的一个节点：终态图上的新知用 `is_new` 标记（前端画强调色描边）。"""
    return {"id": node.id, "title": node.title, "is_new": False}


def _edge_ref(edge: KnowledgeEdge) -> dict:
    """图示里的一条关系：键名与知识图谱接口（graph 区）一致，前端可复用同一套画布代码。"""
    return {"from": edge.from_node, "to": edge.to_node, "relation_type": edge.relation_type}


def _dedupe_edges(edges: list[dict]) -> list[dict]:
    """去掉重复关系（同一对端点 + 同一关系）并保持出现顺序。"""
    seen: set[tuple[str, str, str]] = set()
    result: list[dict] = []
    for edge in edges:
        key = (edge["from"], edge["to"], edge["relation_type"])
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result


def preview_structure(db: Session, conflict: Conflict) -> dict | None:
    """结构冲突的「图谱现状 vs 三种裁决终态」：以冲突知识点为中心的一跳邻域子图。

    终态图与裁决走**同一套语义**（接受新 = 新知顶替旧节点 + 旧节点的边重挂；保留旧 = 不动；
    并存 = 双留 + 新知自带的关系入图），因此图上画的终态就是裁决后图谱的样子
    ——这是 ADR-0004 的验收项，不是装饰。旧节点已不存在（如已被别的裁决删掉）时返回 None。

    新知的节点 id 用占位符 `NEW_NODE_ID`：真实 id 要等裁决入库后才生成。
    """
    old_id = (conflict.existing_knowledge or {}).get("id")
    old = db.get(KnowledgeNode, old_id) if old_id else None
    if old is None:
        return None

    touched = (
        db.query(KnowledgeEdge)
        .filter(or_(KnowledgeEdge.from_node == old.id, KnowledgeEdge.to_node == old.id))
        .all()
    )
    neighbor_ids = {edge.from_node for edge in touched} | {edge.to_node for edge in touched}
    neighbor_ids.discard(old.id)
    current_nodes = [old, *[db.get(KnowledgeNode, nid) for nid in neighbor_ids]]
    current_nodes = [node for node in current_nodes if node is not None]
    current_ids = sorted(node.id for node in current_nodes)
    # 现状 = 这些节点的诱导子图：画出来的节点之间的关系全画上，图上看不出「藏起来的关系」
    current_edges = [
        _edge_ref(edge)
        for edge in db.query(KnowledgeEdge)
        .filter(
            KnowledgeEdge.from_node.in_(current_ids),
            KnowledgeEdge.to_node.in_(current_ids),
        )
        .all()
    ]
    current_refs = [_node_ref(node) for node in current_nodes]

    new_data = conflict.new_knowledge or {}
    new_ref = {"id": NEW_NODE_ID, "title": (new_data.get("title") or "").strip(), "is_new": True}

    def proposed(title_to_id: dict[str, str]) -> list[dict]:
        """新知自带的关系（端点按标题解析；只画两端都在这张终态图里的）。"""
        result: list[dict] = []
        for relation in new_data.get("relations") or []:
            relation_type = (relation.get("relation") or "").strip()
            if relation_type not in RELATION_TYPES:
                continue
            from_id = title_to_id.get((relation.get("from_title") or "").strip())
            to_id = title_to_id.get((relation.get("to_title") or "").strip())
            if from_id and to_id and from_id != to_id:
                result.append({"from": from_id, "to": to_id, "relation_type": relation_type})
        return result

    # 接受新：旧节点让位给新知，旧节点的边改挂到新知（命中旧标题的关系也改挂）
    accept_nodes = [node for node in current_nodes if node.id != old.id]
    accept_refs = [_node_ref(node) for node in accept_nodes] + [new_ref]
    accept_titles = {ref["title"]: ref["id"] for ref in accept_refs}
    accept_titles.setdefault(old.title, NEW_NODE_ID)
    accept_edges = [
        {
            "from": NEW_NODE_ID if edge["from"] == old.id else edge["from"],
            "to": NEW_NODE_ID if edge["to"] == old.id else edge["to"],
            "relation_type": edge["relation_type"],
        }
        for edge in current_edges
    ] + proposed(accept_titles)

    # 并存：新旧双节点都保留，新知自带的关系一并入图
    coexist_refs = current_refs + [new_ref]
    coexist_titles = {ref["title"]: ref["id"] for ref in coexist_refs}
    coexist_edges = current_edges + proposed(coexist_titles)

    return {
        "current": {"nodes": current_refs, "edges": _dedupe_edges(current_edges)},
        "outcomes": [
            {
                "action": "接受新",
                "status": STATUS_BY_ACTION["接受新"],
                "nodes": accept_refs,
                "edges": _dedupe_edges(accept_edges),
            },
            {
                # 保留旧 = 丢弃新知，图谱不动：终态图就是现状图
                "action": "保留旧",
                "status": STATUS_BY_ACTION["保留旧"],
                "nodes": list(current_refs),
                "edges": _dedupe_edges(current_edges),
            },
            {
                "action": "并存",
                "status": STATUS_BY_ACTION["并存"],
                "nodes": coexist_refs,
                "edges": _dedupe_edges(coexist_edges),
            },
        ],
    }


async def _insert_node(
    db: Session,
    conflict: Conflict,
    inherit: KnowledgeNode | None = None,
    content: str | None = None,
) -> KnowledgeNode:
    """按待审新知建节点（接受新时可继承旧节点属性），并写入标题索引。

    `content` 用于常识存疑的「编辑修正后入库」：落库的是修正后的内容（ADR-0004）。
    """
    new_data = conflict.new_knowledge or {}
    title = (new_data.get("title") or (inherit.title if inherit else "")).strip()
    source_docs = list(inherit.source_docs or []) if inherit else []
    if conflict.doc_id and conflict.doc_id not in source_docs:
        source_docs.append(conflict.doc_id)
    node = KnowledgeNode(
        user_id=conflict.user_id,
        title=title,
        content=new_data.get("content", "") if content is None else content,
        difficulty=new_data.get("difficulty") or (inherit.difficulty if inherit else None),
        importance=new_data.get("importance") or (inherit.importance if inherit else None),
        source_docs=source_docs or None,
    )
    db.add(node)
    db.flush()
    emb = (await get_embedder().embed([node.title]))[0]
    VectorStore().add_node_title(node.id, node.title, emb)
    return node
