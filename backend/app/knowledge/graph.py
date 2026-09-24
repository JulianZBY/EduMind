"""知识图谱：LLM 提取 + 存储 + 遍历。"""

from collections import deque

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.llm.parsing import parse_json
from app.db import SessionLocal
from app.db.models import Document, KnowledgeEdge, KnowledgeNode
from app.knowledge.vector_store import VectorStore

RELATION_TYPES = ("前置依赖", "父子包含", "推导关系", "相关关联")
# 邻接子图拉取时优先扩展的边：知识递进关系（前置/父子）先于弱关联
_PRIORITY_RELATIONS = ("前置依赖", "父子包含")

_EXTRACT_PROMPT = """你是教学知识图谱构建助手。从下面的教学内容中提取知识点及其关系。

知识点字段：
- title：简短名称
- content：完整描述
- difficulty：基础/进阶/难点
- importance：必修/选修/了解

关系字段（from、to 用知识点 title）：
- relation_type：前置依赖 / 父子包含 / 推导关系 / 相关关联

只输出 JSON，不要其他文字：
{"nodes": [{"title": "...", "content": "...", "difficulty": "...", "importance": "..."}], "edges": [{"from": "...", "to": "...", "relation_type": "..."}]}

教学内容：
__TEXT__
"""


async def extract_knowledge(text: str) -> tuple[list[dict], list[dict]]:
    """LLM 提取知识点节点与关系边。"""
    from app.core.llm.base import ChatMessage
    from app.core.llm.factory import get_llm

    llm = get_llm()
    prompt = _EXTRACT_PROMPT.replace("__TEXT__", text[:8000])
    result = await llm.chat([ChatMessage(role="user", content=prompt)])
    data = parse_json(result.content)
    return data.get("nodes", []), data.get("edges", [])


def save_knowledge(
    user_id: str,
    nodes: list[dict],
    edges: list[dict],
    source_doc_id: str | None = None,
    title_embeddings: dict[str, list[float]] | None = None,
) -> int:
    """存节点 + 边（title 映射到节点 id），返回节点数。

    title_embeddings：title → 向量。提供时同步写入向量库标题索引，
    供冲突检测的近名预筛使用（ADR-0001）。
    """
    db = SessionLocal()
    try:
        title_to_id: dict[str, str] = {}
        for n in nodes:
            title = (n.get("title") or "").strip()
            if not title:
                continue
            node = KnowledgeNode(
                user_id=user_id,
                title=title,
                content=n.get("content", ""),
                difficulty=n.get("difficulty"),
                importance=n.get("importance"),
                source_docs=[source_doc_id] if source_doc_id else None,
            )
            db.add(node)
            db.flush()
            title_to_id[title] = node.id
            emb = (title_embeddings or {}).get(title)
            if emb:
                VectorStore().add_node_title(node.id, title, emb)
        for e in edges:
            f = title_to_id.get((e.get("from") or "").strip())
            t = title_to_id.get((e.get("to") or "").strip())
            if f and t:
                db.add(
                    KnowledgeEdge(
                        user_id=user_id,
                        from_node=f,
                        to_node=t,
                        relation_type=e.get("relation_type", ""),
                    )
                )
        db.commit()
        return len(title_to_id)
    finally:
        db.close()


def nodes_for_docs(doc_ids: list[str]) -> list[dict]:
    """按来源文档定位知识点（命中片段 → 来源文档 → 知识点）。"""
    if not doc_ids:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.execute(select(KnowledgeNode).where(KnowledgeNode.source_docs.isnot(None)))
            .scalars()
            .all()
        )
        wanted = set(doc_ids)
        return [
            {"id": n.id, "title": n.title, "content": n.content}
            for n in rows
            if wanted & set(n.source_docs or [])
        ]
    finally:
        db.close()


def neighborhood(seed_ids: list[str], max_depth: int = 2) -> list[dict]:
    """多源 BFS 拉取邻接子图：前置依赖/父子包含边优先扩展。

    返回按访问序排列的邻接节点（不含种子自身）。
    """
    if not seed_ids:
        return []
    db = SessionLocal()
    try:
        visited = set(seed_ids)
        ordered: list[dict] = []
        queue: deque[tuple[str, int]] = deque((sid, 0) for sid in seed_ids)
        while queue:
            cur, depth = queue.popleft()
            if depth >= max_depth:
                continue
            edges = list(
                db.execute(
                    select(KnowledgeEdge).where(
                        or_(KnowledgeEdge.from_node == cur, KnowledgeEdge.to_node == cur)
                    )
                )
                .scalars()
                .all()
            )
            edges.sort(key=lambda e: e.relation_type not in _PRIORITY_RELATIONS)
            for e in edges:
                nxt = e.to_node if e.from_node == cur else e.from_node
                if nxt in visited:
                    continue
                visited.add(nxt)
                node = db.get(KnowledgeNode, nxt)
                if node:
                    ordered.append({"id": node.id, "title": node.title, "content": node.content})
                queue.append((nxt, depth + 1))
        return ordered
    finally:
        db.close()


def node_summary(node: KnowledgeNode) -> dict:
    """画布节点：图谱渲染、邻域子图与过滤选项共用同一形状。"""
    return {
        "id": node.id,
        "title": node.title,
        "difficulty": node.difficulty,
        "subject": node.subject,
        "chapter": node.chapter,
    }


def edge_ref(edge: KnowledgeEdge) -> dict:
    """画布连线：`from` / `to` 是既有消费者已在用的键名，不改语义。"""
    return {"from": edge.from_node, "to": edge.to_node, "relation_type": edge.relation_type}


def filter_graph(db: Session, subject: str | None = None, chapter: str | None = None) -> dict:
    """按学科 / 章节取图：只留命中的知识点，以及**两端都在结果集里**的关系。

    过滤后连线随之收缩——否则会留下指向已过滤节点的悬空关系。
    """
    conditions = []
    if subject:
        conditions.append(KnowledgeNode.subject == subject)
    if chapter:
        conditions.append(KnowledgeNode.chapter == chapter)
    nodes = list(db.execute(select(KnowledgeNode).where(*conditions)).scalars().all())
    ids = {n.id for n in nodes}
    if not ids:
        return {"nodes": [], "edges": []}
    edges = (
        db.execute(
            select(KnowledgeEdge).where(
                KnowledgeEdge.from_node.in_(ids), KnowledgeEdge.to_node.in_(ids)
            )
        )
        .scalars()
        .all()
    )
    return {"nodes": [node_summary(n) for n in nodes], "edges": [edge_ref(e) for e in edges]}


def source_refs(db: Session, doc_ids: list) -> list[dict]:
    """来源引用：把 `source_docs` 里的资料 id 翻成资料名（资料已删除时只留 id）。"""
    refs = []
    for doc_id in doc_ids:
        doc = db.get(Document, doc_id)
        refs.append({"doc_id": doc_id, "filename": doc.filename if doc else None})
    return refs


def node_detail(db: Session, node_id: str) -> dict | None:
    """单个知识点的详情（节点详情抽屉）：内容 / 难度 / 来源引用；不存在时返回 None。"""
    node = db.get(KnowledgeNode, node_id)
    if node is None:
        return None
    return {
        "id": node.id,
        "title": node.title,
        "content": node.content or "",
        "subject": node.subject,
        "chapter": node.chapter,
        "difficulty": node.difficulty,
        "importance": node.importance,
        "sources": source_refs(db, node.source_docs or []),
    }


def subgraph(db: Session, node_id: str, max_depth: int = 2) -> dict | None:
    """以选中知识点为中心、向外 max_depth 跳取子图；中心不存在时返回 None。

    返回顺序确定：`nodes` 以中心知识点开头、其余按 BFS 访问序；
    `edges` 每条关系只出现一次（按边 id 去重，避免两端各展开一次时重复）。
    """
    center = db.get(KnowledgeNode, node_id)
    if center is None:
        return None
    visited = {node_id}
    order = [node_id]
    edges_out: list[dict] = []
    seen_edges: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(node_id, 0)])
    while queue:
        cur, depth = queue.popleft()
        if depth >= max_depth:
            continue
        rows = (
            db.execute(
                select(KnowledgeEdge).where(
                    or_(KnowledgeEdge.from_node == cur, KnowledgeEdge.to_node == cur)
                )
            )
            .scalars()
            .all()
        )
        for e in rows:
            if e.id not in seen_edges:
                seen_edges.add(e.id)
                edges_out.append(edge_ref(e))
            nxt = e.to_node if e.from_node == cur else e.from_node
            if nxt not in visited:
                visited.add(nxt)
                order.append(nxt)
                queue.append((nxt, depth + 1))
    nodes = []
    for nid in order:
        node = db.get(KnowledgeNode, nid)
        if node:
            nodes.append(node_summary(node))
    return {"nodes": nodes, "edges": edges_out}


def traverse(node_id: str, max_depth: int = 2) -> dict:
    """从节点 BFS 遍历关联子图，返回 {nodes: [...], edges: [...]}。"""
    db = SessionLocal()
    try:
        edges_out: list[dict] = []
        visited = {node_id}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        while queue:
            cur, depth = queue.popleft()
            if depth >= max_depth:
                continue
            rows = (
                db.execute(
                    select(KnowledgeEdge).where(
                        or_(KnowledgeEdge.from_node == cur, KnowledgeEdge.to_node == cur)
                    )
                )
                .scalars()
                .all()
            )
            for e in rows:
                edges_out.append(
                    {"from": e.from_node, "to": e.to_node, "relation_type": e.relation_type}
                )
                nxt = e.to_node if e.from_node == cur else e.from_node
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, depth + 1))
        nodes_out = []
        for nid in visited:
            node = db.get(KnowledgeNode, nid)
            if node:
                nodes_out.append(
                    {
                        "id": node.id,
                        "title": node.title,
                        "content": node.content,
                        "difficulty": node.difficulty,
                        "importance": node.importance,
                    }
                )
        return {"nodes": nodes_out, "edges": edges_out}
    finally:
        db.close()
