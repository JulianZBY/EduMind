"""健康检查路由。"""

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "llm_provider": settings.llm_provider}
