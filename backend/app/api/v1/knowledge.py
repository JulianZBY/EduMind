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
from app.core.intent import intent_from_payload
from app.core.search.factory import get_search
from app.db import get_session
from app.db.models import KnowledgeEdge, KnowledgeNode
from app.knowledge.retrieval.factory import get_retriever
from app.knowledge.vector_store import VectorStore

router = APIRouter()


class SearchRequest(BaseModel):
    """检索请求：检索词 + 返回条数。"""

    model_config = ConfigDict(json_schema_extra={"example": {"query": "一次函数的定义", "k": 5}})

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


class RetrieveRequest(BaseModel):
    """检索观察请求：备课意图 + 返回条数 + 本次备课的参考资料。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent": {"topic": "一次函数", "knowledge_points": ["斜率"]},
                "k": 5,
                "reference_doc_ids": ["5c9d1e3b-6f47-4a1c-9a2e-0d4c5b7a8f01"],
            }
        }
    )

    # 备课意图（与备课会话同一形状）；结构不完整时退化为仅凭主题检索
    intent: dict = {}
    k: int = 5
    reference_doc_ids: list[str] = []


class RetrievedChunk(BaseModel):
    chunk_id: int
    distance: float
    doc_id: str
    content: str


class RetrievedNode(BaseModel):
    id: str
    title: str
    content: str


class RetrieveResponse(BaseModel):
    strategy: str  # 本次生效的检索策略名
    context: str  # 拼给生成器的上下文档（命中片段 + 融合的知识点，预算内）
    sources: list[str]  # 命中的来源资料名（按排名去重）
    hits: list[RetrievedChunk]  # 命中分块明细
    graph_nodes: list[RetrievedNode]  # 融合到上下文里的图谱知识点（纯向量档为空）


@router.post(
    "/knowledge/retrieve",
    response_model=RetrieveResponse,
    tags=["知识库"],
    summary="按检索策略观察命中",
    description=(
        "用**当前生效的检索策略**跑一次备课检索，看本次命中了什么：`strategy` 为策略名，"
        "`context` 为拼给生成器的上下文档（命中片段 + 融合的知识点，总量受预算约束），"
        "`sources` 为命中的来源资料名（按排名去重，备课回复与教案「参考资料」节溯源自此），"
        "`hits` 为命中分块明细，`graph_nodes` 为融合进上下文的图谱知识点。\n\n"
        "策略由 `RETRIEVAL_STRATEGY` 配置：`vector_graph`（默认，向量 + 图谱邻接融合）/ "
        "`vector`（纯向量，`context` 只有命中片段、`graph_nodes` 为空）。"
        "`intent` 与备课会话同一形状，结构不完整时退化为仅凭主题检索；"
        "`reference_doc_ids` 为本次备课勾选的参考资料，命中这些资料的片段在排名中加权。"
    ),
    responses={
        200: json_response(
            "本次检索命中的分块、来源与图谱知识点",
            {
                "strategy": "vector_graph",
                "context": "=== 知识片段 ===\n一次函数：形如 y=kx+b（k≠0）的函数。",
                "sources": ["一次函数讲义.pdf"],
                "hits": [
                    {
                        "chunk_id": 42,
                        "distance": 0.18,
                        "doc_id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                        "content": "一次函数：形如 y=kx+b（k≠0）的函数。",
                    }
                ],
                "graph_nodes": [
                    {
                        "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                        "title": "一次函数的定义",
                        "content": "形如 y=kx+b（k≠0）…",
                    }
                ],
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def retrieve(req: RetrieveRequest):
    retriever = get_retriever()
    result = await retriever.retrieve(
        intent_from_payload(req.intent),
        top_k=req.k,
        reference_doc_ids=req.reference_doc_ids,
    )
    return RetrieveResponse(
        strategy=retriever.name,
        context=result.context,
        sources=result.sources,
        hits=[
            RetrievedChunk(
                chunk_id=h.chunk_id, distance=h.distance, doc_id=h.doc_id, content=h.content
            )
            for h in result.hits
        ],
        graph_nodes=[RetrievedNode(**n) for n in result.graph_nodes],
    )


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
        "nodes": [{"id": n.id, "title": n.title, "difficulty": n.difficulty} for n in nodes],
        "edges": [
            {"from": e.from_node, "to": e.to_node, "relation_type": e.relation_type} for e in edges
        ],
    }
