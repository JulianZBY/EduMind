"""课件文件下载接口。"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

OUTPUT_DIR = Path("data/output")


@router.get("/files/{filename}")
async def download_file(filename: str, inline: bool = False):
    """inline=true 时不附下载头：互动内容 HTML 可在浏览器直接打开互动（内联预览）。"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = OUTPUT_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=None if inline else filename)
