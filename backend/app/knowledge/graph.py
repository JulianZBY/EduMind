"""知识图谱：LLM 提取 + 存储 + 遍历。"""

from collections import deque

from sqlalchemy import or_, select

from app.core.llm.parsing import parse_json
from app.db import SessionLocal
from app.db.models import KnowledgeEdge, KnowledgeNode
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
