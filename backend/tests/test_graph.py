"""知识图谱存储与遍历测试（假数据，不依赖 LLM）。"""

import uuid

from app.db import SessionLocal, init_db
from app.db.models import KnowledgeNode
from app.knowledge.graph import save_knowledge, traverse

init_db()  # 幂等


def test_save_and_traverse():
    suffix = uuid.uuid4().hex[:6]
    nodes = [
        {"title": f"导数定义_{suffix}", "content": "导数的极限定义", "difficulty": "基础", "importance": "必修"},
        {"title": f"求导法则_{suffix}", "content": "四则运算求导", "difficulty": "基础", "importance": "必修"},
    ]
    edges = [{"from": f"导数定义_{suffix}", "to": f"求导法则_{suffix}", "relation_type": "前置依赖"}]
    n = save_knowledge("default", nodes, edges, source_doc_id="doc1")
    assert n == 2

    db = SessionLocal()
    node = db.query(KnowledgeNode).filter(KnowledgeNode.title == f"导数定义_{suffix}").first()
    db.close()
    assert node is not None

    result = traverse(node.id, max_depth=1)
    titles = {n["title"] for n in result["nodes"]}
    assert f"导数定义_{suffix}" in titles
    assert f"求导法则_{suffix}" in titles
    assert len(result["edges"]) == 1
    assert result["edges"][0]["relation_type"] == "前置依赖"
