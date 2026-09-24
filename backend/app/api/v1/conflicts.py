"""冲突审核接口（ADR-0006 自述本轮范围，三类别见 ADR-0004）：待审队列 + 类别差异化裁决。

三类别（CONTEXT.md 第 6 节）各有自己的形态与动作集合：

- 定义冲突 = 三选一（接受新 / 保留旧 / 并存）；
- 结构冲突 = 三选一，并带「图谱现状 vs 三种裁决终态」的图示数据（`structure_preview`）；
- 常识存疑 = 两选一（照常入库 / 拒绝）+ 编辑修正后入库。

**结构冲突与常识存疑的检测逻辑尚未实现**（ADR-0006）：这两类的数据模型与审核动作已就位，
当前的自动检测只产出定义冲突。
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    error_response,
    internal_error,
    json_response_examples,
    named,
)
from app.db import get_session
from app.db.models import Conflict
from app.knowledge.conflict import (
    ActionNotAllowed,
    preview_structure,
    resolve_conflict,
)

router = APIRouter()

# 六种动作的并集：具体哪几种适用由冲突类别决定（见 ACTIONS_BY_CATEGORY），
# 请求体只负责挡住未知取值（422），类别不匹配的排除在服务层做（也是 422）。
ReviewAction = Literal["接受新", "保留旧", "并存", "照常入库", "拒绝", "编辑修正后入库"]


class ReviewRequest(BaseModel):
    """裁决动作；「编辑修正后入库」另需带修正后的内容。"""

    model_config = ConfigDict(json_schema_extra={"example": {"action": "接受新"}})

    action: ReviewAction = Field(
        description=(
            "裁决动作。定义冲突与结构冲突用 接受新 / 保留旧 / 并存；"
            "常识存疑用 照常入库 / 拒绝 / 编辑修正后入库。"
        )
    )
    revised_content: str | None = Field(
        default=None,
        description=(
            "仅「编辑修正后入库」需要：教师改对后的正文。落库的是这份内容，"
            "原文留在冲突记录里（两条都可追溯）。"
        ),
    )

    @model_validator(mode="after")
    def _revised_content_required(self) -> "ReviewRequest":
        if self.action == "编辑修正后入库" and not (self.revised_content or "").strip():
            raise ValueError("「编辑修正后入库」必须带修正后的内容（revised_content）")
        return self


class NewKnowledgeEntry(BaseModel):
    """待审的新知：标题 + 正文（结构冲突还带 `relations`）。

    已知字段给出类型（前端对照卡片直接用），其余键原样保留——冲突记录里的知识点字典是
    检测阶段存下的，不因本接口丢字段，也不凭空多出键。
    """

    model_config = ConfigDict(extra="allow")

    title: str = ""
    content: str = ""


class ExistingKnowledgeEntry(NewKnowledgeEntry):
    """库里的旧知识点：比新知多一个图谱节点 id。"""

    id: str | None = None


class StructureNode(BaseModel):
    """终态图上的一个节点。

    新知用占位 id `__new__`（真实 id 要等裁决入库后才生成）；`is_new` 让前端把新知
    画成强调色描边（CONTEXT.md 的「接受新」语义：旧知识点的位置换成新知）。
    """

    id: str
    title: str
    is_new: bool = False


class StructureEdge(BaseModel):
    """终态图上的一条关系。键名与知识图谱接口一致，前端复用同一套画布。"""

    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    relation_type: str


class StructureGraph(BaseModel):
    """一张小图：节点 + 关系。"""

    nodes: list[StructureNode]
    edges: list[StructureEdge]


class StructureOutcome(StructureGraph):
    """一种裁决终态的图示 + 它对应的冲突终态。"""

    action: str
    status: str


class StructurePreview(BaseModel):
    """「图谱现状 vs 三种裁决终态」（仅待审的结构冲突带它）。

    以冲突知识点为中心的一跳邻域子图；终态图与实际裁决走的是一套语义，
    因此图上画的终态就是裁决后图谱的样子。
    """

    current: StructureGraph
    outcomes: list[StructureOutcome]


class ConflictItem(BaseModel):
    """一条冲突：类别 + 新旧知识对照 + 差异说明 + 状态。"""

    id: str
    doc_id: str | None = None
    category: str
    new_knowledge: NewKnowledgeEntry | None = None
    existing_knowledge: ExistingKnowledgeEntry | None = None
    diff_description: str | None = None
    status: str
    revised_content: str | None = None
    # 教师实际选的动作（常识存疑的两条入库出路终态都是「已接受」，靠 status 分不出来）
    review_action: str | None = None
    structure_preview: StructurePreview | None = None


class ConflictList(BaseModel):
    """冲突列表。"""

    conflicts: list[ConflictItem]


class ReviewResult(BaseModel):
    """裁决结果：冲突 id、类别、终态与教师选的动作。"""

    id: str
    category: str
    status: str
    action: str


def _conflict_item(db: Session, conflict: Conflict) -> dict:
    """把冲突行整理成响应形状；待审结构冲突附带三种终态的图示数据。"""
    preview = None
    if conflict.category == "结构冲突" and conflict.status == "待审":
        preview = preview_structure(db, conflict)
    return {
        "id": conflict.id,
        "doc_id": conflict.doc_id,
        "category": conflict.category or "定义冲突",
        "new_knowledge": conflict.new_knowledge,
        "existing_knowledge": conflict.existing_knowledge,
        "diff_description": conflict.diff_description,
        "status": conflict.status,
        "revised_content": conflict.revised_content,
        "review_action": conflict.review_action,
        "structure_preview": preview,
    }


@router.get(
    "/conflicts",
    tags=["冲突审核"],
    response_model=ConflictList,
    summary="冲突列表",
    description=(
        "返回待审及已裁决的冲突，每条带**类别**（定义冲突 / 结构冲突 / 常识存疑）与"
        "新旧知识对照（`new_knowledge` / `existing_knowledge`）、差异说明。\n\n"
        "结构冲突另带 `structure_preview`：「图谱现状 vs 三种裁决终态」的小图数据"
        "（以冲突知识点为中心的一跳邻域），供审核界面在按下按钮前就画出图谱会变成什么样。\n\n"
        "**当前只有定义冲突由检测产出**（ADR-0006）：结构冲突与常识存疑的检测逻辑尚未实现，"
        "两类冲突的形态与裁决动作已就位，因此在队列里出现要等检测落地。"
    ),
    responses={
        200: json_response_examples(
            "冲突列表（不传 status / category 时返回全部）",
            {
                "定义冲突": named(
                    "定义冲突：新旧描述对照，三选一",
                    {
                        "conflicts": [
                            {
                                "id": "c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
                                "doc_id": "7f6e5d4c-3b2a-4918-8776-655443322110",
                                "category": "定义冲突",
                                "new_knowledge": {
                                    "title": "一次函数的定义",
                                    "content": "形如 y=kx+b（k≠0）的函数叫一次函数。",
                                },
                                "existing_knowledge": {
                                    "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                    "title": "一次函数的定义",
                                    "content": "形如 y=kx（k≠0）的函数叫一次函数。",
                                },
                                "diff_description": "新知识多了常数项 b，旧知识把正比例函数当成一次函数全集。",
                                "status": "待审",
                                "revised_content": None,
                                "review_action": None,
                                "structure_preview": None,
                            }
                        ]
                    },
                ),
                "结构冲突": named(
                    "结构冲突：图谱现状 vs 三种裁决终态",
                    {
                        "conflicts": [
                            {
                                "id": "d2b3c4e5-6f70-4182-93a4-b5c6d7e8f902",
                                "doc_id": None,
                                "category": "结构冲突",
                                "new_knowledge": {
                                    "title": "一次函数的图象",
                                    "content": "一次函数的图象是一条直线。",
                                    "relations": [
                                        {
                                            "from_title": "一次函数的图象",
                                            "to_title": "一次函数的定义",
                                            "relation": "推导关系",
                                        }
                                    ],
                                },
                                "existing_knowledge": {
                                    "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                    "title": "一次函数的定义",
                                    "content": "形如 y=kx+b（k≠0）的函数叫一次函数。",
                                },
                                "diff_description": "新知识想插在定义与图象之间，与现状的层级冲突。",
                                "status": "待审",
                                "revised_content": None,
                                "review_action": None,
                                "structure_preview": {
                                    "current": {
                                        "nodes": [
                                            {
                                                "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                                "title": "一次函数的定义",
                                                "is_new": False,
                                            },
                                            {
                                                "id": "3c4d5e6f-7081-4293-a4b5-c6d7e8f90123",
                                                "title": "函数的三种表示法",
                                                "is_new": False,
                                            },
                                        ],
                                        "edges": [
                                            {
                                                "from": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                                "to": "3c4d5e6f-7081-4293-a4b5-c6d7e8f90123",
                                                "relation_type": "父子包含",
                                            }
                                        ],
                                    },
                                    "outcomes": [
                                        {
                                            "action": "接受新",
                                            "status": "已接受",
                                            "nodes": [
                                                {
                                                    "id": "3c4d5e6f-7081-4293-a4b5-c6d7e8f90123",
                                                    "title": "函数的三种表示法",
                                                    "is_new": False,
                                                },
                                                {
                                                    "id": "__new__",
                                                    "title": "一次函数的图象",
                                                    "is_new": True,
                                                },
                                            ],
                                            "edges": [
                                                {
                                                    "from": "__new__",
                                                    "to": "3c4d5e6f-7081-4293-a4b5-c6d7e8f90123",
                                                    "relation_type": "父子包含",
                                                },
                                                {
                                                    "from": "__new__",
                                                    "to": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                                    "relation_type": "推导关系",
                                                },
                                            ],
                                        },
                                        {
                                            "action": "保留旧",
                                            "status": "已拒绝",
                                            "nodes": [
                                                {
                                                    "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                                    "title": "一次函数的定义",
                                                    "is_new": False,
                                                },
                                                {
                                                    "id": "3c4d5e6f-7081-4293-a4b5-c6d7e8f90123",
                                                    "title": "函数的三种表示法",
                                                    "is_new": False,
                                                },
                                            ],
                                            "edges": [
                                                {
                                                    "from": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                                    "to": "3c4d5e6f-7081-4293-a4b5-c6d7e8f90123",
                                                    "relation_type": "父子包含",
                                                }
                                            ],
                                        },
                                        {
                                            "action": "并存",
                                            "status": "并存",
                                            "nodes": [
                                                {
                                                    "id": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                                    "title": "一次函数的定义",
                                                    "is_new": False,
                                                },
                                                {
                                                    "id": "3c4d5e6f-7081-4293-a4b5-c6d7e8f90123",
                                                    "title": "函数的三种表示法",
                                                    "is_new": False,
                                                },
                                                {
                                                    "id": "__new__",
                                                    "title": "一次函数的图象",
                                                    "is_new": True,
                                                },
                                            ],
                                            "edges": [
                                                {
                                                    "from": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                                    "to": "3c4d5e6f-7081-4293-a4b5-c6d7e8f90123",
                                                    "relation_type": "父子包含",
                                                },
                                                {
                                                    "from": "__new__",
                                                    "to": "2b3c4d5e-6f70-4182-93a4-b5c6d7e8f901",
                                                    "relation_type": "推导关系",
                                                },
                                            ],
                                        },
                                    ],
                                },
                            }
                        ]
                    },
                ),
                "常识存疑": named(
                    "常识存疑：红旗标记 + 原文 + 两选一 / 编辑修正后入库",
                    {
                        "conflicts": [
                            {
                                "id": "e3c4d5f6-7081-4293-a4b5-c6d7e8f90134",
                                "doc_id": "8f7e6d5c-4b3a-4928-8776-655443322119",
                                "category": "常识存疑",
                                "new_knowledge": {
                                    "title": "地球的形状",
                                    "content": "地球是平的。",
                                },
                                "existing_knowledge": None,
                                "diff_description": "内容可能是错的常识，需要教师决定要不要让它进库。",
                                "status": "待审",
                                "revised_content": None,
                                "review_action": None,
                                "structure_preview": None,
                            }
                        ]
                    },
                ),
            },
        ),
        500: internal_error(),
    },
)
async def list_conflicts(
    db: Annotated[Session, Depends(get_session)],
    status: Annotated[
        str | None,
        Query(description="按状态过滤：待审 / 已接受 / 已拒绝 / 并存；不传返回全部"),
    ] = None,
    category: Annotated[
        str | None,
        Query(description="按类别过滤：定义冲突 / 结构冲突 / 常识存疑；不传返回全部"),
    ] = None,
):
    """冲突列表（默认全部；可按状态与类别过滤，队列按类别分区呈现）。"""
    conditions = []
    if status:
        conditions.append(Conflict.status == status)
    if category:
        conditions.append(Conflict.category == category)
    conflicts = db.execute(select(Conflict).where(*conditions)).scalars().all()
    return {"conflicts": [_conflict_item(db, conflict) for conflict in conflicts]}


@router.post(
    "/conflicts/{conflict_id}/review",
    tags=["冲突审核"],
    response_model=ReviewResult,
    summary="裁决冲突",
    description=(
        "教师处置待审冲突，每条冲突只能裁决一次。**动作集合按类别收窄**：\n\n"
        "* 定义冲突 / 结构冲突（三选一）：`接受新`：新知识点替换旧知识点，"
        "旧知识点上的关系边重挂到新知识点，终态 `已接受`；"
        "`保留旧`：丢弃新知，图谱不动，终态 `已拒绝`；"
        "`并存`：新旧双知识点保留，差异说明留在冲突记录中，终态 `并存`。\n"
        "* 常识存疑（两选一 + 编辑修正后入库）：`照常入库`：按原文进库，终态 `已接受`；"
        "`拒绝`：不让它进库，终态 `已拒绝`；`编辑修正后入库`：教师改对了再入库，"
        "**落库的是修正后的内容**（原文留在冲突记录里），终态 `已接受`。\n\n"
        "动作不属于该类别 = `422`（与冲突当前状态无关的请求语义错误）；"
        "对已裁决的冲突再提交 = `409`（状态冲突，不是请求格式错误）。\n\n"
        "审核前新知不入知识图谱——「待审」期间图谱里看不到它；"
        '结构冲突的新知可自带关系（`new_knowledge["relations"]`，端点按知识点标题解析），'
        "随「接受新」/「并存」一并入图。"
    ),
    responses={
        200: json_response_examples(
            "裁决成功，返回冲突 id、类别与终态",
            {
                "接受新（定义冲突 / 结构冲突）": named(
                    "接受新 → 已接受",
                    {
                        "id": "c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
                        "category": "定义冲突",
                        "status": "已接受",
                        "action": "接受新",
                    },
                ),
                "编辑修正后入库（常识存疑）": named(
                    "编辑修正后入库 → 已接受（落库的是修正后的内容）",
                    {
                        "id": "e3c4d5f6-7081-4293-a4b5-c6d7e8f90134",
                        "category": "常识存疑",
                        "status": "已接受",
                        "action": "编辑修正后入库",
                    },
                ),
            },
        ),
        404: error_response("冲突不存在", "冲突不存在: c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d"),
        409: error_response("该冲突已被裁决过，不能重复提交", "该冲突已审核: 已接受"),
        422: json_response_examples(
            "动作不属于该冲突类别的动作集合，或请求体校验失败"
            "（未知动作 / 「编辑修正后入库」缺修正后的内容）",
            {
                "动作与类别不匹配": named(
                    "动作与类别不匹配",
                    {"detail": "常识存疑的动作是 照常入库 / 拒绝 / 编辑修正后入库，不接受: 并存"},
                ),
                "请求体校验失败": named(
                    "请求体校验失败",
                    {
                        "detail": [
                            {
                                "type": "value_error",
                                "loc": ["body"],
                                "msg": "Value error, 「编辑修正后入库」必须带修正后的内容（revised_content）",
                            }
                        ]
                    },
                ),
            },
        ),
        500: internal_error(),
    },
)
async def review_conflict(
    conflict_id: Annotated[str, Path(description="待审冲突 id，取自冲突列表")],
    req: ReviewRequest,
):
    """裁决待审冲突：动作按类别差异化，终态与裁决动作一一对应。"""
    try:
        return await resolve_conflict(conflict_id, req.action, req.revised_content)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ActionNotAllowed as e:
        # 动作与该类别不匹配：与状态无关的请求语义错误，故是 422 而不是 409
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
