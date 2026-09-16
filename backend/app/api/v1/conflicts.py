"""冲突审核接口（ADR-0001）：待审列表 + 教师三选一（接受新 / 保留旧 / 并存）。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.db.models import Conflict
from app.knowledge.conflict import resolve_conflict

router = APIRouter()

ReviewAction = Literal["接受新", "保留旧", "并存"]


class ReviewRequest(BaseModel):
    action: ReviewAction


@router.get("/conflicts")
async def list_conflicts(db: Annotated[Session, Depends(get_session)], status: str | None = None):
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


@router.post("/conflicts/{conflict_id}/review")
async def review_conflict(conflict_id: str, req: ReviewRequest):
    """教师三选一处置：接受新（替换旧）/ 保留旧（丢弃新）/ 并存（双留并标注差异）。"""
    try:
        result = await resolve_conflict(conflict_id, req.action)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return result
