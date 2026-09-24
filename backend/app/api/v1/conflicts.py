"""冲突审核接口（ADR-0001）：待审列表 + 教师三选一（接受新 / 保留旧 / 并存）。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.openapi_examples import (
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.db import get_session
from app.db.models import Conflict
from app.knowledge.conflict import resolve_conflict

router = APIRouter()

ReviewAction = Literal["接受新", "保留旧", "并存"]


class ReviewRequest(BaseModel):
    """裁决动作：三选一，与冲突终态一一对应。"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"action": "接受新"}}
    )

    action: ReviewAction


@router.get(
    "/conflicts",
    tags=["冲突审核"],
    summary="冲突列表",
    description=(
        "返回待审及已裁决的冲突。每条包含新旧知识对照（`new_knowledge` / "
        "`existing_knowledge`）与差异说明，供教师判断谁对。\n\n"
        "当前唯一类别是**定义冲突**（同一知识点两段矛盾描述）；结构冲突与常识存疑两种类别"
        "的数据模型见 ADR-0004，检测逻辑尚未实现，因此不会出现在本列表。"
    ),
    responses={
        200: json_response(
            "冲突列表（不传 status 时返回全部）",
            {
                "conflicts": [
                    {
                        "id": "c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
                        "doc_id": "7f6e5d4c-3b2a-4918-8776-655443322110",
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
                    }
                ]
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
):
    """冲突列表（默认全部，可按状态过滤：待审/已接受/已拒绝/并存）。"""
    query = db.query(Conflict)
    if status:
        query = query.filter(Conflict.status == status)
    conflicts = query.all()
    return {
        "conflicts": [
            {
                "id": c.id,
                "doc_id": c.doc_id,
                "new_knowledge": c.new_knowledge,
                "existing_knowledge": c.existing_knowledge,
                "diff_description": c.diff_description,
                "status": c.status,
            }
            for c in conflicts
        ]
    }


@router.post(
    "/conflicts/{conflict_id}/review",
    tags=["冲突审核"],
    summary="裁决冲突",
    description=(
        "教师三选一处置待审冲突，每条冲突只能裁决一次：\n\n"
        "* `接受新`：新知识点替换旧知识点，旧知识点上的关系边重挂到新知识点，终态 `已接受`；\n"
        "* `保留旧`：丢弃新知，图谱不动，终态 `已拒绝`；\n"
        "* `并存`：新旧双知识点保留，差异说明留在冲突记录中，终态 `并存`。\n\n"
        "裁决后该知识点才进入知识图谱（审核前新知不入图）。"
    ),
    responses={
        200: json_response(
            "裁决成功，返回冲突 id 与终态",
            {"id": "c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d", "status": "已接受"},
        ),
        404: error_response("冲突不存在", "冲突不存在: c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d"),
        409: error_response("该冲突已被裁决过，不能重复提交", "该冲突已审核: 已接受"),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def review_conflict(
    conflict_id: Annotated[str, Path(description="待审冲突 id，取自冲突列表")],
    req: ReviewRequest,
):
    """教师三选一处置：接受新（替换旧）/ 保留旧（丢弃新）/ 并存（双留并标注差异）。"""
    try:
        result = await resolve_conflict(conflict_id, req.action)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return result
