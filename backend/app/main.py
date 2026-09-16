"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # 幂等：空库/缺表缺列时自动建，保证全新克隆启动即可用
    yield


app = FastAPI(
    title="EduMind API",
    version="0.1.0",
    description="多模态 AI 互动式教学智能体后端",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}
