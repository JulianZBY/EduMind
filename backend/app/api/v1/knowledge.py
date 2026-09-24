"""知识检索接口：RAG 语义搜索 + 知识图谱。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    internal_error,
    json_response,
    unconfigured,
)
from app.core.embedding.factory import get_embedder
from app.core.search.factory import get_search
from app.db import get_session
from app.db.models import KnowledgeEdge, KnowledgeNode
from app.knowledge.vector_store import VectorStore

router = APIRouter()


class SearchRequest(BaseModel):
    """检索请求：检索词 + 返回条数。"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"query": "一次函数的定义", "k": 5}}
    )

    query: str
    k: int = 5


class SearchHit(BaseModel):
    chunk_id: int
    distance: float
    doc_id: str
    content: str


class SearchResponse(BaseModel):
    hits: list[SearchHit]


@router.post(
    "/knowledge/search",
    response_model=SearchResponse,
    tags=["知识库"],
    summary="知识库语义检索",
    description=(
        "在本地知识库里做语义检索，返回最相近的段落（`distance` 越小越相近，`doc_id` 可回溯来源文档）。\n\n"
        "检索用向量由当前配置的向量化能力生成；无云端 Key 时由 stub 提供与宿主无关的兜底向量，"
        "因此无 Key 时排序不具语义意义，仅供链路联调。"
    ),
    responses={
        200: json_response(
            "命中段落（按相似度升序）",
            {
                "hits": [
                    {
                        "chunk_id": 42,
                        "distance": 0.18,
                        "doc_id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                        "content": "一次函数：形如 y=kx+b（k≠0）的函数。",
                    }
                ]
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def search(req: SearchRequest):
    emb = await get_embedder().embed([req.query])
    results = VectorStore().search(emb[0], k=req.k)
    return SearchResponse(hits=[SearchHit(**r) for r in results])


@router.post(
    "/knowledge/web-search",
    tags=["知识库"],
    summary="网络搜索",
    description=(
        "调用博查（Bocha）网络搜索补充课本之外的材料，返回标题 / 链接 / 摘要。\n\n"
        "本能力无 stub 实现：`BOCHA_API_KEY` 未配置时请求失败（`500`，`detail` 为 "
        "`BOCHA_API_KEY 未配置`），而不是静默返回空结果。"
    ),
    responses={
        200: json_response(
            "搜索结果",
            {
                "results": [
                    {
                        "title": "一次函数的定义与图象",
                        "url": "https://example.com/lesson/linear-function",
                        "snippet": "一次函数 y=kx+b（k≠0）的图象是一条直线…",
                    }
                ]
            },
        ),
        422: VALIDATION_ERROR,
        500: unconfigured("网络搜索（BOCHA_API_KEY）"),
    },
)
async def web_search(req: SearchRequest):
    results = await get_search().search(req.query, count=req.k)
    return {"results": results}


@router.get(
    "/knowledge/graph",
    tags=["知识图谱"],
    summary="知识图谱数据",
    description=(
        "返回知识图谱的全部知识点与关系，前端据此自行渲染图谱。\n\n"
        "`relation_type` 取值：`前置依赖` / `父子包含` / `推导关系` / `相关关联`。\n"
        "节点详情、按学科章节过滤与邻域取子图接口随知识图谱工作台（票 10）交付。"
    ),
    responses={
        200: json_response(
            "知识点与关系",
            {
                "nodes": [
                    {
                        "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                        "title": "一次函数的定义",
                        "difficulty": "基础",
                    }
                ],
                "edges": [
                    {
                        "from": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                        "to": "9c8b7a65-4321-4f0e-8d9c-1b2a3c4d5e6f",
                        "relation_type": "前置依赖",
                    }
                ],
            },
        ),
        500: internal_error(),
    },
)
async def get_graph(db: Annotated[Session, Depends(get_session)]):
    nodes = db.query(KnowledgeNode).all()
    edges = db.query(KnowledgeEdge).all()
    return {
        "nodes": [
            {"id": n.id, "title": n.title, "difficulty": n.difficulty} for n in nodes
        ],
        "edges": [
            {"from": e.from_node, "to": e.to_node, "relation_type": e.relation_type}
            for e in edges
        ],
    }
