"""课件文件下载接口。"""

import pathlib
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import FileResponse

from app.api.openapi_examples import error_response, internal_error

router = APIRouter()

OUTPUT_DIR = pathlib.Path("data/output")


@router.get(
    "/files/{filename}",
    tags=["生成物"],
    summary="下载生成物文件",
    description=(
        "按文件名取回落盘的生成物（课件 pptx / 教案与提纲 docx / 试卷 docx / 互动内容 html）。\n\n"
        "* `inline=false`（默认）：附下载头，浏览器保存文件；\n"
        "* `inline=true`：不附下载头，互动内容 HTML 可直接在浏览器内联打开试用。\n\n"
        "文件名由生成接口返回，不接受目录与路径分隔符；生成物与版本记录的一一对应关系见 `docs/api/`。"
    ),
    responses={
        200: {
            "description": (
                "文件字节流；实际媒体类型由生成物后缀决定（pptx / docx / xlsx / html），"
                "`Content-Disposition` 决定下载或内联"
            ),
            "content": {
                "application/octet-stream": {
                    "description": "文件二进制内容",
                    "example": "<file bytes>",
                }
            },
        },
        400: error_response(
            "文件名非法：含 `..` 或路径分隔符（防止目录穿越）", "非法文件名"
        ),
        404: error_response("文件不存在或已被清理", "文件不存在"),
        500: internal_error(),
    },
)
async def download_file(
    filename: Annotated[str, Path(description="生成物文件名（不含目录），取自生成接口返回")],
    inline: Annotated[
        bool, Query(description="true 时不附下载头：互动内容 HTML 可在浏览器直接打开互动")
    ] = False,
):
    """inline=true 时不附下载头：互动内容 HTML 可在浏览器直接打开互动（内联预览）。"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = OUTPUT_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=None if inline else filename)
