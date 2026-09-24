"""健康检查路由。"""

from fastapi import APIRouter

from app.api.openapi_examples import internal_error, json_response
from app.config import settings

router = APIRouter()


@router.get(
    "/health",
    tags=["系统"],
    summary="健康检查",
    description=(
        "返回服务状态、应用名与当前生效的对话模型供应商。"
        "前端启动自检与运维探活都读这一条；不访问数据库、不调用外部能力。"
        "`llm_provider` 为 `stub` 时表示当前无云端 Key，功能仍可全链路跑通。"
    ),
    responses={
        200: json_response(
            "服务可用", {"status": "ok", "app": "EduMind", "llm_provider": "stub"}
        ),
        500: internal_error(),
    },
)
async def health():
    return {"status": "ok", "app": settings.app_name, "llm_provider": settings.llm_provider}
