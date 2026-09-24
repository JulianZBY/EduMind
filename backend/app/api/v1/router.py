"""v1 业务路由汇总。"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.openapi_examples import internal_error, json_response
from app.api.v1.artifacts import router as artifacts_router
from app.api.v1.chat import router as chat_router
from app.api.v1.conflicts import router as conflicts_router
from app.api.v1.documents import router as documents_router
from app.api.v1.exam import router as exam_router
from app.api.v1.files import router as files_router
from app.api.v1.interactive import router as interactive_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.revise import router as revise_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.settings import router as settings_router

router = APIRouter()
router.include_router(artifacts_router)
router.include_router(chat_router)
router.include_router(conflicts_router)
router.include_router(documents_router)
router.include_router(exam_router)
router.include_router(files_router)
router.include_router(interactive_router)
router.include_router(knowledge_router)
router.include_router(revise_router)
router.include_router(sessions_router)
router.include_router(settings_router)


class PingResponse(BaseModel):
    """v1 存活探测响应：固定文本，表示 `/api/v1` 已挂载。"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "ok", "message": "EduMind API v1"}}
    )

    status: str  # 固定为 ok
    message: str  # 固定为版本标识文本


@router.get(
    "/ping",
    response_model=PingResponse,
    tags=["系统"],
    summary="v1 存活探测",
    description=(
        "确认 `/api/v1` 已挂载且服务能响应。只回固定文本，不访问数据库、不调用外部能力，"
        "适合作为前端连接异常时的最小排查点（若 `/health` 也失败则是进程问题）。"
    ),
    responses={
        200: json_response("v1 已就绪", {"status": "ok", "message": "EduMind API v1"}),
        500: internal_error(),
    },
)
async def ping() -> PingResponse:
    return PingResponse(status="ok", message="EduMind API v1")
