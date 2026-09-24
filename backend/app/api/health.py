"""健康检查路由。"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.openapi_examples import internal_error, json_response
from app.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """健康检查响应：服务状态 + 应用名 + 当前生效的对话模型供应商。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"status": "ok", "app": "EduMind", "llm_provider": "stub"}
        }
    )

    status: str  # 固定为 ok：能回这一条就说明进程活着
    app: str  # 应用名
    llm_provider: str  # 当前生效的对话供应商；stub = 无云端 Key，功能仍全链路可跑


@router.get(
    "/health",
    response_model=HealthResponse,
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
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok", app=settings.app_name, llm_provider=settings.llm_provider
    )
