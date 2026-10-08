"""知识检索接口：RAG 语义搜索 + 知识图谱。"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    PROVIDER_NOT_CONFIGURED,
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.api.v1.documents import DocumentView
from app.core.embedding.factory import get_embedder
from app.core.intent import intent_from_payload
from app.core.search.factory import get_search
from app.db import get_session
from app.knowledge.graph import filter_graph, node_detail, subgraph
from app.knowledge.literature_note import SOURCE_WEB
from app.knowledge.pipeline import parse_document
from app.knowledge.retrieval.factory import get_retriever
from app.knowledge.vector_store import VectorStore
from app.knowledge.web_ingest import prepare_web_ingest

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
        "检索用向量由当前配置的向量化能力生成；未配置云端 Key 时用本地 hash 兜底向量（真实算法），"
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


class WebSearchResult(BaseModel):
    """一条网络搜索结果：标题 / 链接 / 摘要。"""

    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    """网络搜索响应：结果列表（未配置博查 Key 时返回 503 引导，不返回占位结果）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "results": [
                    {
                        "title": "一次函数的定义与图象",
                        "url": "https://example.com/lesson/linear-function",
                        "snippet": "一次函数 y=kx+b（k≠0）的图象是一条直线…",
                    }
                ]
            }
        }
    )

    results: list[WebSearchResult]


@router.post(
    "/knowledge/web-search",
    response_model=WebSearchResponse,
    tags=["知识库"],
    summary="网络搜索",
    description=(
        "调用博查（Bocha）网络搜索补充课本之外的材料，返回标题 / 链接 / 摘要。\n\n"
        "实现按配置选择：默认 `auto`——配了 `BOCHA_API_KEY` 走博查，没配则返回 503 引导（code: provider_not_configured），"
        "不返回任何占位结果——拿假结果当教学依据比明确报错更糟。"
        "显式配成 `SEARCH_PROVIDER=bocha` 但缺 Key 时同样返回 `503` 配置引导。"
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
        500: internal_error(),
        503: PROVIDER_NOT_CONFIGURED,
    },
)
async def web_search(req: SearchRequest) -> WebSearchResponse:
    results = await get_search().search(req.query, count=req.k)
    return WebSearchResponse(results=[WebSearchResult(**r) for r in results])


class WebIngestRequest(BaseModel):
    """教师手动发起联网检索并入库，不触发本次生成。"""

    model_config = ConfigDict(json_schema_extra={"example": {"query": "一次函数", "k": 5}})

    query: str = Field(min_length=1, max_length=500, description="本次备课的检索主题")
    k: int = Field(default=5, ge=1, le=5, description="最多入库的网页结果数（1–5）")

    @field_validator("query", mode="before")
    @classmethod
    def trim_query(cls, value):
        return value.strip() if isinstance(value, str) else value


class WebIngestResponse(BaseModel):
    """已接收入库，不代表后台处理成功；通过资料列表和详情跟进终态。"""

    query: str
    ingested: int = Field(description="已接收入库的网页资料数；零结果为 0")
    documents: list[DocumentView]


@router.post(
    "/knowledge/web-search/ingest",
    response_model=WebIngestResponse,
    tags=["知识库"],
    summary="联网检索并入库",
    description=(
        "仅教师手动触发博查检索；每条结果的标题、URL、摘要作为网页资料入知识库。"
        "响应中的资料为「处理中」，随后与上传资料共用分块、向量化、知识提取、"
        "冲突检测与文献笔记管道（来源＝网页）。待审知识点不入知识图谱。"
        "请在知识库通过资料列表和详情轮询到「已完成／有冲突／失败」。"
        "零结果返回 ingested＝0，不建资料；未配置搜索返回 503 和设置引导。"
        "不自动联网，不修改本次课件或会话消息，后续备课经本地检索使用。"
    ),
    responses={
        200: json_response(
            "已接收入库（后台处理中）；零结果 documents 为空",
            {
                "query": "一次函数",
                "ingested": 1,
                "documents": [
                    {
                        "id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                        "filename": "一次函数的定义",
                        "file_type": "网页",
                        "status": "处理中",
                        "is_reference": False,
                        "failure_reason": "",
                    }
                ],
            },
        ),
        422: VALIDATION_ERROR,
        500: internal_error(),
        503: PROVIDER_NOT_CONFIGURED,
    },
)
async def web_search_ingest(
    req: WebIngestRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_session)],
) -> WebIngestResponse:
    created = await prepare_web_ingest(db, req.query, req.k)
    for doc, text in created:
        background_tasks.add_task(parse_document, doc.id, text=text, source=SOURCE_WEB)
    return WebIngestResponse(
        query=req.query,
        ingested=len(created),
        documents=[DocumentView.model_validate(doc, from_attributes=True) for doc, _ in created],
    )


class GraphNode(BaseModel):
    """图谱里的一个知识点（画布节点）。

    `subject` / `chapter` 随节点一起返回，前端据此列出过滤选项（学科 / 章节）。
    """

    id: str
    title: str
    difficulty: str | None = None
    subject: str | None = None
    chapter: str | None = None


class GraphEdge(BaseModel):
    """图谱里的一条关系（画布连线）。

    `from` / `to` 是既有消费者已在用的键名，不改语义。
    """

    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    relation_type: str


class GraphResponse(BaseModel):
    """知识图谱数据：知识点与关系。"""

    nodes: list[GraphNode]
    edges: list[GraphEdge]


class KnowledgeSourceRef(BaseModel):
    """来源引用：这个知识点的正文来自哪份资料（资料已删除时 `filename` 为空）。"""

    doc_id: str
    filename: str | None = None


class KnowledgePointDetail(BaseModel):
    """知识点详情：内容 / 难度 / 来源引用（节点详情抽屉的数据）。"""

    id: str
    title: str
    content: str
    subject: str | None = None
    chapter: str | None = None
    difficulty: str | None = None
    importance: str | None = None
    sources: list[KnowledgeSourceRef]


@router.get(
    "/knowledge/graph",
    response_model=GraphResponse,
    tags=["知识图谱"],
    summary="知识图谱数据",
    description=(
        "返回知识点与关系，前端据此自行渲染图谱。\n\n"
        "`subject` / `chapter` 为可选过滤：带上则只返回命中的知识点，"
        "以及**两端都在结果集里**的关系（连线随节点一同收缩，不留悬空关系）；都不带即全图。\n\n"
        "`relation_type` 取值：`前置依赖` / `父子包含` / `推导关系` / `相关关联`。"
        "单个知识点的详情见 `GET /knowledge/nodes/{node_id}`，邻域子图见 "
        "`GET /knowledge/nodes/{node_id}/neighborhood`。"
    ),
    responses={
        200: json_response(
            "知识点与关系（带上过滤参数时已收缩）",
            {
                "nodes": [
                    {
                        "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                        "title": "一次函数的定义",
                        "difficulty": "基础",
                        "subject": "数学",
                        "chapter": "一次函数",
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
async def get_graph(
    db: Annotated[Session, Depends(get_session)],
    subject: Annotated[str | None, Query(description="按学科过滤；不带即不限学科")] = None,
    chapter: Annotated[str | None, Query(description="按章节过滤；不带即不限章节")] = None,
):
    return filter_graph(db, subject=subject, chapter=chapter)


@router.get(
    "/knowledge/nodes/{node_id}",
    response_model=KnowledgePointDetail,
    tags=["知识图谱"],
    summary="知识点详情",
    description=(
        "返回一个知识点的完整内容、学科章节、难度与重要度，以及**来源引用**"
        "（这个知识点的正文来自哪几份资料）。\n\n"
        "`sources` 按知识点记录的来源资料逐个给出：`doc_id` 为资料 id，"
        "`filename` 为资料名（资料已删除时只留 id、名字为空）。"
    ),
    responses={
        200: json_response(
            "知识点详情",
            {
                "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                "title": "一次函数的定义",
                "content": "形如 y=kx+b（k≠0）的函数，图象是一条直线。",
                "subject": "数学",
                "chapter": "一次函数",
                "difficulty": "基础",
                "importance": "必修",
                "sources": [
                    {
                        "doc_id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                        "filename": "一次函数讲义.pdf",
                    }
                ],
            },
        ),
        404: error_response(
            "知识点不存在：该 id 在知识图谱里没有对应节点（可能已被删除或替换）",
            "知识点不存在",
        ),
        500: internal_error(),
    },
)
async def get_knowledge_point(node_id: str, db: Annotated[Session, Depends(get_session)]):
    detail = node_detail(db, node_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="知识点不存在")
    return detail


@router.get(
    "/knowledge/nodes/{node_id}/neighborhood",
    response_model=GraphResponse,
    tags=["知识图谱"],
    summary="邻域子图",
    description=(
        "以选中知识点为中心、向外 `max_depth` 跳取邻域子图（看清它的上下游）。\n\n"
        "返回的 `nodes` 以中心知识点开头，其余按广度优先的访问顺序；"
        "`edges` 只包含两端都在子图里的关系，每条关系只出现一次。\n\n"
        "中心知识点不存在时返回 `404`；`max_depth` 超出 1–3 返回 `422`。"
    ),
    responses={
        200: json_response(
            "邻域子图（中心知识点在 nodes 首位）",
            {
                "nodes": [
                    {
                        "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                        "title": "一次函数的定义",
                        "difficulty": "基础",
                        "subject": "数学",
                        "chapter": "一次函数",
                    },
                    {
                        "id": "9c8b7a65-4321-4f0e-8d9c-1b2a3c4d5e6f",
                        "title": "一次函数的图象",
                        "difficulty": "进阶",
                        "subject": "数学",
                        "chapter": "一次函数",
                    },
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
        404: error_response("知识点不存在：无法以它为中心取邻域", "知识点不存在"),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def get_neighborhood(
    node_id: str,
    db: Annotated[Session, Depends(get_session)],
    max_depth: Annotated[int, Query(ge=1, le=3, description="向外几跳（1–3），默认 2")] = 2,
):
    data = subgraph(db, node_id, max_depth=max_depth)
    if data is None:
        raise HTTPException(status_code=404, detail="知识点不存在")
    return data


class SubjectNameRequest(BaseModel):
    """教师维护学科名称；主学科归类和本清单共用同一存储。"""

    model_config = ConfigDict(
        str_strip_whitespace=True, json_schema_extra={"example": {"name": "天文学"}}
    )
    name: str = Field(min_length=1, max_length=100, description="学科名称，一行，前后空白自动去除")


class SubjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class SubjectListResponse(BaseModel):
    subjects: list[SubjectView]


def _maintain_subject(db: Session, **kwargs) -> dict:
    from app.knowledge.subjects import SubjectError, maintain_subject

    try:
        return maintain_subject(db, **kwargs)
    except SubjectError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "/knowledge/subjects",
    response_model=SubjectListResponse,
    tags=["知识库"],
    summary="读取学科清单",
    description="返回教师认可的当前学科清单。知识点的唯一主学科只能取清单内名称，无法选择时归「未分类」。",
    responses={
        200: json_response("学科清单", {"subjects": [{"id": "subject-math", "name": "数学"}]}),
        500: internal_error(),
    },
)
def get_subjects(db: Annotated[Session, Depends(get_session)]):
    from app.knowledge.subjects import list_subjects

    return {"subjects": list_subjects(db)}


@router.post(
    "/knowledge/subjects",
    status_code=201,
    response_model=SubjectView,
    tags=["知识库"],
    summary="新增学科",
    description="教师将新学科加入清单，即时用于后续知识点归类。名称须唯一，不自动重新归类已有知识点。",
    responses={
        201: json_response("已新增学科", {"id": "subject-astronomy", "name": "天文学"}),
        400: error_response("名称内容不可接受", "学科名称须为一行，包含 1～100 个字符。"),
        409: error_response("名称重复", "学科名称已在清单内，请使用其他名称。"),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
def create_subject(req: SubjectNameRequest, db: Annotated[Session, Depends(get_session)]):
    return _maintain_subject(db, name=req.name)


@router.patch(
    "/knowledge/subjects/{subject_id}",
    response_model=SubjectView,
    tags=["知识库"],
    summary="学科更名",
    description="更名在同一事务中更新该学科的所有知识点，不留下清单外名称。「未分类」不可更名。",
    responses={
        200: json_response("已更名学科", {"id": "subject-math", "name": "数学与应用"}),
        400: error_response("名称内容不可接受", "学科名称须为一行，包含 1～100 个字符。"),
        404: error_response("学科不存在", "学科不存在。"),
        409: error_response("名称重复或兜底项不可更名", "「未分类」用于归类兜底，不能更名或删除。"),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
def rename_subject(
    subject_id: str, req: SubjectNameRequest, db: Annotated[Session, Depends(get_session)]
):
    return _maintain_subject(db, subject_id=subject_id, name=req.name)


@router.delete(
    "/knowledge/subjects/{subject_id}",
    response_model=SubjectView,
    tags=["知识库"],
    summary="删除学科",
    description="删除清单项并在同一事务中将其知识点归「未分类」，知识点与关系不删除。「未分类」不可删除。",
    responses={
        200: json_response("已删除的学科", {"id": "subject-math", "name": "数学"}),
        404: error_response("学科不存在", "学科不存在。"),
        409: error_response("兜底项不能删除", "「未分类」用于归类兜底，不能更名或删除。"),
        500: internal_error(),
    },
)
def delete_subject(subject_id: str, db: Annotated[Session, Depends(get_session)]):
    return _maintain_subject(db, subject_id=subject_id)
