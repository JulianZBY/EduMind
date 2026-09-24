"""知识图谱工作台接口测试：过滤 / 节点详情 / 邻域子图（HTTP 缝：只断言响应与数据变迁）。

造一张只属于本次测试的图（用 uuid 后缀把学科、章节、标题、资料名都做唯一），
避免与库里既有数据相互干扰：

    一次函数的定义(A) --前置依赖--> 一次函数的图象(B) --推导关系--> 斜率(C)
    A --相关关联--> 古诗鉴赏(D，另一个学科)

"""

import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.db.models import Document, KnowledgeEdge, KnowledgeNode
from app.main import app

client = TestClient(app)
init_db()  # 幂等：确保表和默认用户存在


def _seed_graph() -> dict:
    """建本次测试的图，返回 id 与唯一取值，供断言比对。"""
    suffix = uuid.uuid4().hex[:6]
    subject = f"数学_{suffix}"
    other_subject = f"语文_{suffix}"
    chapter = f"一次函数_{suffix}"
    other_chapter = f"古诗_{suffix}"
    filename = f"一次函数讲义_{suffix}.pdf"

    db = SessionLocal()
    try:
        doc = Document(
            user_id="default",
            filename=filename,
            file_path="data/uploads/fake.pdf",
            file_type="pdf",
            status="已完成",
        )
        db.add(doc)
        db.flush()

        def add_node(title: str, node_subject: str, node_chapter: str, difficulty: str) -> str:
            node = KnowledgeNode(
                user_id="default",
                title=title,
                content=f"{title}的正文",
                subject=node_subject,
                chapter=node_chapter,
                difficulty=difficulty,
                importance="必修",
                source_docs=[doc.id],
            )
            db.add(node)
            db.flush()
            return node.id

        def_a = add_node(f"一次函数的定义_{suffix}", subject, chapter, "基础")
        img_b = add_node(f"一次函数的图象_{suffix}", subject, chapter, "进阶")
        slope_c = add_node(f"斜率的含义_{suffix}", subject, f"导数_{suffix}", "难点")
        poem_d = add_node(f"古诗鉴赏_{suffix}", other_subject, other_chapter, "基础")

        db.add_all(
            [
                KnowledgeEdge(user_id="default", from_node=def_a, to_node=img_b, relation_type="前置依赖"),
                KnowledgeEdge(user_id="default", from_node=img_b, to_node=slope_c, relation_type="推导关系"),
                # 跨学科的相关关联：按学科过滤时必须随节点一同收缩
                KnowledgeEdge(user_id="default", from_node=def_a, to_node=poem_d, relation_type="相关关联"),
            ]
        )
        db.commit()
        return {
            "suffix": suffix,
            "subject": subject,
            "other_subject": other_subject,
            "chapter": chapter,
            "filename": filename,
            "doc_id": doc.id,
            "def_a": def_a,
            "img_b": img_b,
            "slope_c": slope_c,
            "poem_d": poem_d,
        }
    finally:
        db.close()


def test_graph_filter_keeps_only_matching_nodes_and_their_edges():
    """按学科过滤：节点收缩到该学科，连线只留两端都在结果集里的。"""
    ctx = _seed_graph()

    r = client.get("/api/v1/knowledge/graph", params={"subject": ctx["subject"]})
    assert r.status_code == 200
    data = r.json()
    assert {n["id"] for n in data["nodes"]} == {ctx["def_a"], ctx["img_b"], ctx["slope_c"]}
    assert {(e["from"], e["to"]) for e in data["edges"]} == {
        (ctx["def_a"], ctx["img_b"]),
        (ctx["img_b"], ctx["slope_c"]),
    }
    # 跨学科的相关关联被剔除，不留悬空关系
    assert all(ctx["poem_d"] not in (e["from"], e["to"]) for e in data["edges"])

    # 节点摘要字段：画布渲染与过滤选项所需（id / title / difficulty / subject / chapter）
    node = next(n for n in data["nodes"] if n["id"] == ctx["def_a"])
    assert node["title"] == f"一次函数的定义_{ctx['suffix']}"
    assert node["difficulty"] == "基础"
    # 过滤选项（学科 / 章节）由前端从全图节点上汇总，故节点必须带这两个字段
    assert node["subject"] == ctx["subject"]
    assert node["chapter"] == ctx["chapter"]

    whole = client.get("/api/v1/knowledge/graph").json()
    assert {n["subject"] for n in whole["nodes"]} >= {ctx["subject"], ctx["other_subject"]}


def test_graph_filter_by_chapter_is_narrower_than_by_subject():
    """按章节过滤：只留该章节的知识点；跨章节的关系随之收缩掉。"""
    ctx = _seed_graph()

    r = client.get("/api/v1/knowledge/graph", params={"chapter": ctx["chapter"]})
    assert r.status_code == 200
    data = r.json()
    assert {n["id"] for n in data["nodes"]} == {ctx["def_a"], ctx["img_b"]}
    assert {(e["from"], e["to"]) for e in data["edges"]} == {(ctx["def_a"], ctx["img_b"])}

    # 学科 + 章节同时给：两个条件同时生效（AND）
    both = client.get(
        "/api/v1/knowledge/graph",
        params={"subject": ctx["other_subject"], "chapter": ctx["chapter"]},
    )
    assert both.status_code == 200
    assert both.json() == {"nodes": [], "edges": []}

    # 过滤取值为空：不报错，收缩成空图
    empty = client.get("/api/v1/knowledge/graph", params={"subject": f"不存在的学科_{ctx['suffix']}"})
    assert empty.status_code == 200
    assert empty.json() == {"nodes": [], "edges": []}


def test_graph_without_filter_still_returns_the_whole_graph():
    """不带过滤参数 = 全图（既有语义不变）：本次测试的节点与边都在。"""
    ctx = _seed_graph()

    r = client.get("/api/v1/knowledge/graph")
    assert r.status_code == 200
    data = r.json()
    ids = {n["id"] for n in data["nodes"]}
    assert {ctx["def_a"], ctx["img_b"], ctx["slope_c"], ctx["poem_d"]} <= ids
    triplets = {(e["from"], e["to"], e["relation_type"]) for e in data["edges"]}
    assert (ctx["def_a"], ctx["poem_d"], "相关关联") in triplets


def test_knowledge_point_detail_returns_content_difficulty_and_sources():
    """节点详情：内容 / 难度 / 来源引用（翻成资料名）。"""
    ctx = _seed_graph()

    r = client.get(f"/api/v1/knowledge/nodes/{ctx['def_a']}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == ctx["def_a"]
    assert data["title"] == f"一次函数的定义_{ctx['suffix']}"
    assert data["content"] == f"一次函数的定义_{ctx['suffix']}的正文"
    assert data["difficulty"] == "基础"
    assert data["subject"] == ctx["subject"]
    assert data["chapter"] == ctx["chapter"]
    assert data["importance"] == "必修"
    assert data["sources"] == [{"doc_id": ctx["doc_id"], "filename": ctx["filename"]}]


def test_knowledge_point_detail_of_missing_node_is_404():
    r = client.get("/api/v1/knowledge/nodes/no-such-knowledge-point")
    assert r.status_code == 404
    assert r.json()["detail"] == "知识点不存在"


def test_neighborhood_takes_subgraph_centered_on_the_selected_node():
    """邻域子图：中心在 nodes 首位、跳数决定范围、每条关系只出现一次。"""
    ctx = _seed_graph()

    one_hop = client.get(
        f"/api/v1/knowledge/nodes/{ctx['def_a']}/neighborhood", params={"max_depth": 1}
    )
    assert one_hop.status_code == 200
    data = one_hop.json()
    node_ids = [n["id"] for n in data["nodes"]]
    assert node_ids[0] == ctx["def_a"]  # 中心知识点在首位
    assert set(node_ids) == {ctx["def_a"], ctx["img_b"], ctx["poem_d"]}
    assert {(e["from"], e["to"], e["relation_type"]) for e in data["edges"]} == {
        (ctx["def_a"], ctx["img_b"], "前置依赖"),
        (ctx["def_a"], ctx["poem_d"], "相关关联"),
    }

    two_hop = client.get(
        f"/api/v1/knowledge/nodes/{ctx['def_a']}/neighborhood", params={"max_depth": 2}
    )
    assert two_hop.status_code == 200
    data2 = two_hop.json()
    node_ids2 = [n["id"] for n in data2["nodes"]]
    assert node_ids2[0] == ctx["def_a"]  # 中心知识点仍在首位
    assert set(node_ids2) == {
        ctx["def_a"],
        ctx["img_b"],
        ctx["slope_c"],
        ctx["poem_d"],
    }
    # A→B 与 B→C 各出现一次：两端都展开过也不重复计数
    assert len(data2["edges"]) == 3
    # 默认 max_depth = 2：不带参数与带 2 同形
    default_depth = client.get(f"/api/v1/knowledge/nodes/{ctx['def_a']}/neighborhood")
    assert default_depth.status_code == 200
    assert default_depth.json() == data2


def test_neighborhood_edge_cases_are_explicit():
    """中心不存在 = 404；跳数越界 = 422；叶子节点的邻域只有关系里的一端。"""
    ctx = _seed_graph()

    missing = client.get("/api/v1/knowledge/nodes/no-such-knowledge-point/neighborhood")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "知识点不存在"

    out_of_range = client.get(
        f"/api/v1/knowledge/nodes/{ctx['def_a']}/neighborhood", params={"max_depth": 9}
    )
    assert out_of_range.status_code == 422

    leaf = client.get(
        f"/api/v1/knowledge/nodes/{ctx['poem_d']}/neighborhood", params={"max_depth": 1}
    )
    assert leaf.status_code == 200
    data = leaf.json()
    # 一跳只到直接相邻的一跳：从叶子出发就是「它 + 与它相连的那个」
    assert {n["id"] for n in data["nodes"]} == {ctx["poem_d"], ctx["def_a"]}
    assert {(e["from"], e["to"]) for e in data["edges"]} == {(ctx["def_a"], ctx["poem_d"])}
