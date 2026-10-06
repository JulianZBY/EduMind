"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.api.health import router as health_router
from app.api.openapi_examples import internal_error, json_response
from app.api.v1.router import router as v1_router
from app.config import settings
from app.core.errors import GenerationFailed, ProviderNotConfigured
from app.db import init_db
from app.knowledge.pipeline import fail_stuck_documents

# 端点分组：面向教师的术语与 CONTEXT.md 一致，Swagger / ReDoc 按此导航。
TAGS_METADATA = [
    {"name": "系统", "description": "存活检查与服务信息；不含备课语义。"},
    {
        "name": "备课会话",
        "description": "备课对话主入口：澄清与生成两种回复形态，支持追问粒度与参考资料。",
    },
    {
        "name": "知识库",
        "description": "教学资料上传、列表与语义检索；参考资料标记影响备课检索加权与溯源。",
    },
    {
        "name": "知识图谱",
        "description": "知识点及其关系：前置依赖 / 父子包含 / 推导关系 / 相关关联。",
    },
    {
        "name": "生成物",
        "description": "课件、教案、提纲、试卷、互动内容的生成、修改与文件下载。",
    },
    {"name": "冲突审核", "description": "待审冲突队列与教师的裁决动作。"},
    {
        "name": "题库",
        "description": "可复用的题目资产库：浏览题目、按考查知识点筛选、看题目详情。",
    },
    {
        "name": "设置",
        "description": (
            "云端能力与模型档位的配置页：供应商目录、任务级模型、能力切换；"
            "配置库优先于 .env 引导默认，写入即时生效，Key 一律掩码。"
        ),
    },
]

DESCRIPTION = """多模态 AI 备课智能体后端。

OpenAPI 是本服务接口文档的**唯一事实源**：每个端点都带 `summary`、描述、
请求/响应示例、错误码与分组 tag；前端 TypeScript 类型由本 schema 生成，禁止手抄。
* **界面**：Swagger UI `/docs`，ReDoc `/redoc`。
* **分组**：系统 / 备课会话 / 知识库 / 知识图谱 / 生成物 / 冲突审核 / 题库。
* **单用户**：固定 `user_id="default"`，本服务不含登录与多租户。
* **启动清扫**：进程重启时，上一轮被中断的「处理中」资料不会有后台任务再推进，
  服务启动时统一标记为「失败」，避免前端无限轮询（教师可按原文重新上传）。
* **能力切换**：对话模型、向量化、语音转写、PDF 解析、网络搜索均按配置选择。
  云端能力未配置时相关端点返回 `503`（`code: provider_not_configured`，`message` 面向教师，
  指到设置页）——产品不返回任何「看起来像真结果的占位内容」。
* **生成失败**：配好了但生成没成功时返回 `502`（`code: generation_failed`），
  教师可重试——不落一份空课件 / 空教案冒充成功。
* **版本策略**：只有破坏性变更才升 `/api/v2`。
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # 幂等：空库/缺表缺列时自动建，保证全新克隆启动即可用
    fail_stuck_documents()  # 清扫上次进程残留的「处理中」资料（没有任务再推进，避免永久轮询）
    yield


app = FastAPI(
    title="EduMind API",
    version="0.1.0",
    description=DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)


@app.exception_handler(ProviderNotConfigured)
async def _provider_not_configured_handler(_: Request, exc: ProviderNotConfigured) -> JSONResponse:
    """未配置云端能力：503 + 稳定 code + 面向教师的一句话（引导去设置页，而不是假成功）。"""
    return JSONResponse(
        status_code=503,
        content={"detail": {"code": "provider_not_configured", "message": str(exc)}},
    )


@app.exception_handler(GenerationFailed)
async def _generation_failed_handler(_: Request, exc: GenerationFailed) -> JSONResponse:
    """本轮备课生成失败：502 + 稳定 code + 面向教师的一句话（可重试，不返回空壳生成物）。"""
    return JSONResponse(
        status_code=502,
        content={"detail": {"code": "generation_failed", "message": str(exc)}},
    )


app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")


class RootResponse(BaseModel):
    """服务信息：应用名与两个运维入口（接口文档 / 健康检查）的地址。"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"name": "EduMind", "docs": "/docs", "health": "/health"}}
    )

    name: str  # 应用名
    docs: str  # Swagger UI 地址（接口文档入口）
    health: str  # 健康检查地址


@app.get(
    "/",
    response_model=RootResponse,
    tags=["系统"],
    summary="服务信息",
    description="返回应用名与文档、健康检查入口地址，供启动自检与人工排查使用。",
    responses={
        200: json_response("服务信息", {"name": "EduMind", "docs": "/docs", "health": "/health"}),
        500: internal_error(),
    },
)
async def root() -> RootResponse:
    return RootResponse(name=settings.app_name, docs="/docs", health="/health")
