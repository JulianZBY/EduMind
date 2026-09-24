"""知识冲突检测与教师审核（ADR-0001）：定义冲突为唯一类别。

候选发现：同名精确匹配 + embedding 相似度近名预筛（阈值内候选交 LLM 比对，
复用 sqlite-vec 标题索引）；冲突入待审队列，审核前新节点不入知识图谱；
教师三选一——接受新（替换旧节点）/ 保留旧（丢弃新知）/ 并存（双节点保留并标注差异）。
结构冲突、常识存疑不在承诺范围。
"""

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


async def resolve_conflict(conflict_id: str, action: str) -> dict:
    """教师三选一处置待审冲突，返回 {"id", "status"}。

    - 接受新：新节点替换旧节点，旧节点的边重挂到新节点；
    - 保留旧：丢弃新知，图谱不动；
    - 并存：新旧双节点保留，差异说明保留在冲突记录中。
    """
    if action not in REVIEW_ACTIONS:
        raise ValueError(f"未知审核动作: {action}")
    db = SessionLocal()
    try:
        conflict = db.get(Conflict, conflict_id)
        if conflict is None:
            raise LookupError(f"冲突不存在: {conflict_id}")
        if conflict.status != "待审":
            raise ValueError(f"该冲突已审核: {conflict.status}")

        old_id = (conflict.existing_knowledge or {}).get("id")
        old = db.get(KnowledgeNode, old_id) if old_id else None

        if action == "接受新":
            node = await _insert_node(db, conflict, inherit=old)
            if old is not None:
                db.query(KnowledgeEdge).filter(KnowledgeEdge.from_node == old.id).update(
                    {"from_node": node.id}
                )
                db.query(KnowledgeEdge).filter(KnowledgeEdge.to_node == old.id).update(
                    {"to_node": node.id}
                )
                db.delete(old)
                VectorStore().remove_node_title(old.id)
            conflict.status = "已接受"
        elif action == "并存":
            await _insert_node(db, conflict)
            conflict.status = "并存"
        else:  # 保留旧：丢弃新知（新节点从未入图，无需回滚）
            conflict.status = "已拒绝"

        db.commit()
        return {"id": conflict.id, "status": conflict.status}
    finally:
        db.close()


async def _insert_node(
    db, conflict: Conflict, inherit: KnowledgeNode | None = None
) -> KnowledgeNode:
    """按待审新知建节点（接受新时可继承旧节点属性），并写入标题索引。"""
    new_data = conflict.new_knowledge or {}
    title = (new_data.get("title") or (inherit.title if inherit else "")).strip()
    source_docs = list(inherit.source_docs or []) if inherit else []
    if conflict.doc_id and conflict.doc_id not in source_docs:
        source_docs.append(conflict.doc_id)
    node = KnowledgeNode(
        user_id=conflict.user_id,
        title=title,
        content=new_data.get("content", ""),
        difficulty=new_data.get("difficulty") or (inherit.difficulty if inherit else None),
        importance=new_data.get("importance") or (inherit.importance if inherit else None),
        source_docs=source_docs or None,
    )
    db.add(node)
    db.flush()
    emb = (await get_embedder().embed([node.title]))[0]
    VectorStore().add_node_title(node.id, node.title, emb)
    return node
