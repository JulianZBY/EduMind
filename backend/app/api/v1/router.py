"""v1 业务路由汇总。"""

from fastapi import APIRouter

from app.api.v1.chat import router as chat_router
from app.api.v1.conflicts import router as conflicts_router
from app.api.v1.documents import router as documents_router
from app.api.v1.exam import router as exam_router
from app.api.v1.files import router as files_router
from app.api.v1.interactive import router as interactive_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.ppt_edit import router as ppt_edit_router
from app.api.v1.revise import router as revise_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(conflicts_router)
router.include_router(documents_router)
router.include_router(exam_router)
router.include_router(files_router)
router.include_router(interactive_router)
router.include_router(knowledge_router)
router.include_router(revise_router)
router.include_router(ppt_edit_router)


@router.get("/ping")
async def ping():
    return {"status": "ok", "message": "EduMind API v1"}
