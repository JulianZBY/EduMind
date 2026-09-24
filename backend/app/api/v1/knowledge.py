"""知识检索接口：RAG 语义搜索 + 知识图谱。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.embedding.factory import get_embedder
from app.core.search.factory import get_search
from app.db import get_session
from app.db.models import KnowledgeEdge, KnowledgeNode
from app.knowledge.vector_store import VectorStore

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    k: int = 5


class SearchHit(BaseModel):
    chunk_id: int
    distance: float
    doc_id: str
    content: str


class SearchResponse(BaseModel):
    hits: list[SearchHit]


@router.post("/knowledge/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    emb = await get_embedder().embed([req.query])
    results = VectorStore().search(emb[0], k=req.k)
    return SearchResponse(hits=[SearchHit(**r) for r in results])


@router.post("/knowledge/web-search")
async def web_search(req: SearchRequest):
    results = await get_search().search(req.query, count=req.k)
    return {"results": results}


@router.get("/knowledge/graph")
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
