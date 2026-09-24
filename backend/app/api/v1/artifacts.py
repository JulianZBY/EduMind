"""生成物版本接口：列出某次备课的全部版本、取任意版本详情、下载任意版本的文件。

事实源在服务端（ADR-0002）：每次产出落一条版本记录，一条记录对应一个落盘文件，
因此「找回上一版更好的课件」是一步操作。本层只做参数校验、转发与 OpenAPI 注解；
版本与基线的判断（什么算同一生成物、以哪一版为基线）住 `core/artifacts.py`。
"""

import pathlib
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import generate
from app.api.openapi_examples import (
    VALIDATION_ERROR,
    error_response,
    internal_error,
    json_response,
)
from app.core import artifacts as artifact_service
from app.db import get_session
from app.db.artifacts import ArtifactStore
from app.db.models import ArtifactVersion

router = APIRouter()

# 生成物类别（CONTEXT.md「生成物」）：课件 / 教案 / 提纲 / 试卷 / 互动内容
ArtifactType = Literal["课件", "教案", "提纲", "试卷", "互动内容"]
# 类别取值与次序以 core 层那一份为准（Literal 供 OpenAPI 枚举用，两者必须一致）
_ARTIFACT_TYPE_VALUES: tuple[ArtifactType, ...] = cast(
    tuple[ArtifactType, ...], artifact_service.ARTIFACT_TYPES
)

_EXAMPLE_VERSION = {
    "id": "3f2a1b0c-9d8e-4f70-8a1b-2c3d4e5f6a7b",
    "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
    "artifact_type": "课件",
    "version": 1,
    "label": "第 1 版",
    "origin": "生成",
    "filename": "courseware_ppt_1a2b3c4d.pptx",
    "title": "一次函数",
    "parent_id": None,
    "created_at": "2026-09-24T10:00:30",
    "download_url": "/api/v1/artifacts/3f2a1b0c-9d8e-4f70-8a1b-2c3d4e5f6a7b/download",
}


class ArtifactVersionItem(BaseModel):
    id: str
    session_id: str
    artifact_type: ArtifactType
    version: int
    label: str  # 「第 N 版」：教师看到的版本号，文件名不可读、不当标题用
    origin: str  # 产出方式：生成 / 修改
    filename: str  # 落盘文件名：一个版本对应一个文件
    title: str  # 生成物标题（如备课主题），同一生成物的各版本一致
    parent_id: str | None = None  # 基线版本 id（版本树的父节点）；首次生成为空
    created_at: datetime
    download_url: str  # 下载这一版文件的地址（相对本服务根路径）


class ArtifactVersionDetail(ArtifactVersionItem):
    content: dict | None = None  # 这一版的内容快照（课件 slides / 教案结构 / 提纲正文 / 题目 / HTML）


class ArtifactVersionGroup(BaseModel):
    artifact_type: ArtifactType
    current_version_id: str  # 当前版本 = 版本号最高的那一版（没有特殊权威）
    current_version: int
    versions: list[ArtifactVersionItem]  # 版本号升序：当前版本与全部历史版本都在里面


class ArtifactListResponse(BaseModel):
    session_id: str
    groups: list[ArtifactVersionGroup]


def _artifact_type(value: str) -> ArtifactType:
    """把库内读出的生成物类别收窄成契约里的字面量类型（响应模型因此可校验）。"""
    if value in _ARTIFACT_TYPE_VALUES:
        return cast(ArtifactType, value)
    raise ValueError(f"未知生成物类别: {value}")


def _item(row: ArtifactVersion) -> ArtifactVersionItem:
    return ArtifactVersionItem(
        id=row.id,
        session_id=row.session_id,
        artifact_type=_artifact_type(row.artifact_type),
        version=row.version,
        label=f"第 {row.version} 版",
        origin=row.origin,
        filename=row.filename,
        title=row.title,
        parent_id=row.parent_id,
        created_at=row.created_at,
        download_url=f"/api/v1/artifacts/{row.id}/download",
    )


def _groups(rows: list[ArtifactVersion]) -> list[ArtifactVersionGroup]:
    """按生成物类别分组：组内按版本号升序，组间按 CONTEXT.md 的生成物次序。"""
    grouped: dict[str, list[ArtifactVersion]] = {}
    for row in rows:
        grouped.setdefault(row.artifact_type, []).append(row)

    groups: list[ArtifactVersionGroup] = []
    for artifact_type in _ARTIFACT_TYPE_VALUES:
        versions = sorted(grouped.get(artifact_type) or [], key=lambda row: row.version)
        if not versions:
            continue
        groups.append(
            ArtifactVersionGroup(
                artifact_type=artifact_type,
                current_version_id=versions[-1].id,
                current_version=versions[-1].version,
                versions=[_item(row) for row in versions],
            )
        )
    return groups


def _require_version(store: ArtifactStore, version_id: str) -> ArtifactVersion:
    row = store.get(version_id=version_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"生成物版本不存在: {version_id}")
    return row


@router.get(
    "/sessions/{session_id}/artifacts",
    response_model=ArtifactListResponse,
    tags=["生成物"],
    summary="列出某次备课的生成物历史版本",
    description=(
        "返回某次备课（会话）的**全部生成物版本**，供生成物区按会话分组的版本时间线使用。\n\n"
        "结果按生成物类别（课件 / 教案 / 提纲 / 试卷 / 互动内容）分组；每组内 `versions` 按版本号升序，"
        "**当前版本与历史版本并列**——`current_version_id` 只是版本号最高的那一版"
        "（列表与预览默认打开的一版），不代表其它版本作废：历史版本一律可回看、可下载、可作基线继续修改。\n\n"
        "* `artifact_type` 非空时只看某一类生成物（例如生成物区的某一条时间线）；\n"
        "* 每个版本带 `filename` 与 `download_url`：由文件反查版本、由版本取回文件都可一步完成；\n"
        "* 版本号在同一生成物、同一会话内单调递增；`label` 是给教师看的「第 N 版」。\n\n"
        "会话不存在时返回 `404`（不静默返回空列表）。"
    ),
    responses={
        200: json_response(
            "按生成物类别分组的版本列表（含当前版本与全部历史版本）",
            {
                "session_id": "9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b",
                "groups": [
                    {
                        "artifact_type": "课件",
                        "current_version_id": "4a3b2c1d-0e9f-4a81-9b2c-3d4e5f6a7b8c",
                        "current_version": 2,
                        "versions": [
                            _EXAMPLE_VERSION,
                            {
                                **_EXAMPLE_VERSION,
                                "id": "4a3b2c1d-0e9f-4a81-9b2c-3d4e5f6a7b8c",
                                "version": 2,
                                "label": "第 2 版",
                                "origin": "修改",
                                "filename": "courseware_ppt_5e6f7a8b.pptx",
                                "parent_id": _EXAMPLE_VERSION["id"],
                                "created_at": "2026-09-24T10:05:00",
                                "download_url": (
                                    "/api/v1/artifacts/4a3b2c1d-0e9f-4a81-9b2c-3d4e5f6a7b8c/download"
                                ),
                            },
                        ],
                    },
                    {
                        "artifact_type": "教案",
                        "current_version_id": "5c4d3e2f-1a0b-4c92-8d3e-4f5a6b7c8d9e",
                        "current_version": 1,
                        "versions": [
                            {
                                **_EXAMPLE_VERSION,
                                "id": "5c4d3e2f-1a0b-4c92-8d3e-4f5a6b7c8d9e",
                                "artifact_type": "教案",
                                "filename": "lesson_plan_2b3c4d5e.docx",
                                "download_url": (
                                    "/api/v1/artifacts/5c4d3e2f-1a0b-4c92-8d3e-4f5a6b7c8d9e/download"
                                ),
                            }
                        ],
                    },
                ],
            },
        ),
        404: error_response("备课会话不存在", "会话不存在: 9f1a2b3c-4d5e-4f60-8a7b-1c2d3e4f5a6b"),
        422: VALIDATION_ERROR,
        500: internal_error(),
    },
)
async def list_artifact_versions(
    db: Annotated[Session, Depends(get_session)],
    session_id: Annotated[str, Path(description="备课会话 id，取自会话列表")],
    artifact_type: Annotated[
        ArtifactType | None,
        Query(description="只看某一类生成物；不传返回全部（课件 / 教案 / 提纲 / 试卷 / 互动内容）"),
    ] = None,
):
    """某次备课的全部生成物版本（按生成物类别分组，含当前版本与全部历史版本）。"""
    store = ArtifactStore(db)
    try:
        artifact_service.require_session(store, session_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    rows = store.list_versions(session_id=session_id, artifact_type=artifact_type)
    return ArtifactListResponse(session_id=session_id, groups=_groups(rows))


@router.get(
    "/artifacts/{version_id}",
    response_model=ArtifactVersionDetail,
    tags=["生成物"],
    summary="取某个生成物版本的详情",
    description=(
        "按版本 id 取这一版的详情：版本号、产出方式（生成 / 修改）、落盘文件名、"
        "标题、基线版本（`parent_id`，即「由哪一版衍生而来」）以及**这一版的内容快照**。\n\n"
        "内容快照让历史版本可以直接回看（课件结构与页面、教案结构、提纲正文、题目、互动内容 HTML）；"
        "下载文件请用 `download_url` 指向的下载端点。\n\n"
        "版本 id 不存在时返回 `404`。"
    ),
    responses={
        200: json_response(
            "某一版生成物的详情（含内容快照）",
            {
                **_EXAMPLE_VERSION,
                "origin": "修改",
                "version": 2,
                "label": "第 2 版",
                "parent_id": "3f2a1b0c-9d8e-4f70-8a1b-2c3d4e5f6a7b",
                "content": {
                    "slides": [
                        {"role": "封面", "title": "一次函数", "points": ["情境导入：出租车计价"]}
                    ]
                },
            },
        ),
        404: error_response("生成物版本不存在", "生成物版本不存在: 3f2a1b0c-9d8e-4f70-8a1b-2c3d4e5f6a7b"),
        500: internal_error(),
    },
)
async def get_artifact_version(
    db: Annotated[Session, Depends(get_session)],
    version_id: Annotated[str, Path(description="版本 id，取自版本列表的 `versions[].id`")],
):
    """某一版生成物的详情（含这一版的内容快照）。"""
    row = _require_version(ArtifactStore(db), version_id)
    return ArtifactVersionDetail(**_item(row).model_dump(), content=row.content)


@router.get(
    "/artifacts/{version_id}/download",
    tags=["生成物"],
    summary="下载某个生成物版本的文件",
    description=(
        "按版本 id 取回**这一版**的落盘文件（课件 pptx / 教案与提纲 docx / 试卷 docx / 互动内容 html），"
        "不是「最新那个文件」的别名——每个版本对应各自的一次产出。\n\n"
        "* `inline=false`（默认）：附下载头，浏览器保存文件；\n"
        "* `inline=true`：不附下载头，互动内容 HTML 可在浏览器新标签页直接打开试用。\n\n"
        "落盘文件名由服务端生成（不接受目录与路径分隔符）；版本不存在返回 `404`，"
        "文件已被清理时同样 `404`，含义是「这个版本的文件不在了」。"
    ),
    responses={
        200: {
            "description": (
                "文件字节流；实际媒体类型由生成物后缀决定（pptx / docx / html），"
                "`Content-Disposition` 决定下载或内联"
            ),
            "content": {
                "application/octet-stream": {
                    "description": "文件二进制内容",
                    "example": "<file bytes>",
                }
            },
        },
        400: error_response("文件名非法：含 `..` 或路径分隔符（防止目录穿越）", "非法文件名"),
        404: error_response(
            "版本不存在，或该版本的文件已被清理", "生成物版本不存在: 3f2a1b0c-9d8e-4f70-8a1b-2c3d4e5f6a7b"
        ),
        500: internal_error(),
    },
)
async def download_artifact_version(
    db: Annotated[Session, Depends(get_session)],
    version_id: Annotated[str, Path(description="版本 id，取自版本列表的 `versions[].id`")],
    inline: Annotated[
        bool, Query(description="true 时不附下载头：互动内容 HTML 可在浏览器直接打开互动")
    ] = False,
):
    """按版本下载这一版的落盘文件（inline=true 时不附下载头）。"""
    row = _require_version(ArtifactStore(db), version_id)
    filename = row.filename
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = generate.output_dir() / filename
    if not pathlib.Path(path).is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=None if inline else filename)
