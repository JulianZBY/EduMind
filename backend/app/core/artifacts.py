"""生成物全版本留痕（core 层）：生成即入库、以历史版本为基线继续修改。

业务判断住本层：什么算同一生成物、以哪一版为基线、版本链怎么接、
「版本记录必须与落盘文件一一对应」这条不变式在哪守。全部 ORM 读写委托
`db/artifacts.py`；路由层只做参数校验与转发（分层铁律见 `backend/AGENTS.md`）。

术语（CONTEXT.md 第 3 节）：版本 / 当前版本 / 历史版本 / 基线；
「当前版本」只是版本号最高的一版，历史版本一律可回看、可下载、可作基线。
"""

import logging
from pathlib import Path

from app.db.artifacts import ArtifactStore
from app.db.models import ArtifactVersion
from app.db.sessions import ConversationStore

logger = logging.getLogger(__name__)

# 生成物类别（CONTEXT.md「生成物」）：课件 / 教案 / 提纲 / 试卷 / 互动内容
PPT = "课件"
WORD = "教案"
OUTLINE = "提纲"
EXAM = "试卷"
CREATIVE = "互动内容"
ARTIFACT_TYPES = (PPT, WORD, OUTLINE, EXAM, CREATIVE)

# 产出方式：生成（一轮备课的产出）/ 修改（按修改意见再产出）
ORIGIN_GENERATED = "生成"
ORIGIN_REVISED = "修改"

# 一轮备课的产物键（orchestrator 的 artifacts）→ 生成物类别 + 内容快照
_GENERATED_ARTIFACTS = {
    "ppt": (PPT, lambda item: {"slides": item.get("slides") or []}),
    "word": (WORD, lambda item: {"word": item.get("data") or {}}),
    "outline": (OUTLINE, lambda item: {"text": item.get("text") or ""}),
    "interactive": (CREATIVE, lambda item: {"html": item.get("html") or ""}),
}


class BaselineNotFound(LookupError):
    """基线不可用：版本不存在，或该会话还没有这一类生成物（路由转 404）。"""


class BaselineMismatch(ValueError):
    """基线版本与本次修改的生成物类别不符（路由转 422）。"""


def require_session(store: ArtifactStore, session_id: str) -> None:
    """带了会话标识的生成 / 修改都先校验会话存在：不存在即 404，不静默丢弃版本记录。"""
    if ConversationStore(store.db).get(session_id) is None:
        raise LookupError(f"会话不存在: {session_id}")


def record_generation(
    store: ArtifactStore,
    *,
    session_id: str,
    artifact_type: str,
    path: str,
    content: dict | None = None,
    title: str = "",
) -> ArtifactVersion:
    """生成即入库：一件产出落一条版本记录（版本号单调递增，落盘文件一一对应）。

    再次生成记为上一次产出的后继（同一个生成物在版本树里只有一条链），
    因此「当前版本」始终是版本号最高的一版。
    """
    if not Path(path).is_file():
        raise FileNotFoundError(f"生成物落盘文件不存在，拒绝留下无文件的版本记录: {path}")
    current = store.current(session_id=session_id, artifact_type=artifact_type)
    return store.record(
        session_id=session_id,
        artifact_type=artifact_type,
        filename=Path(path).name,
        content=content,
        title=title or artifact_type,
        origin=ORIGIN_GENERATED,
        parent_id=current.id if current else None,
    )


def register_generated_artifacts(
    store: ArtifactStore, *, session_id: str, artifacts: dict, topic: str = ""
) -> dict[str, ArtifactVersion]:
    """一轮备课的产出逐件入库，返回 {产物键: 版本记录}。

    没有落盘文件的产物不记版本（版本记录与落盘文件必须一一对应），
    例如提纲生成失败时就没有文件，此时宁可不留版本记录。
    """
    recorded: dict[str, ArtifactVersion] = {}
    for key, (artifact_type, snapshot) in _GENERATED_ARTIFACTS.items():
        item = artifacts.get(key)
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = str(item["path"])
        if not Path(path).is_file():
            logger.warning("生成物 %s 没有落盘文件，跳过版本记录: %s", artifact_type, path)
            continue
        recorded[key] = record_generation(
            store,
            session_id=session_id,
            artifact_type=artifact_type,
            path=path,
            content=snapshot(item),
            title=topic,
        )
    return recorded


def attach_version_refs(artifacts: dict, recorded: dict[str, ArtifactVersion]) -> None:
    """把版本标识回填进这一轮的产物：会话工作台据此与版本中心取同一份数据。"""
    for key, row in recorded.items():
        item = artifacts.get(key)
        if not isinstance(item, dict):
            continue
        item["version_id"] = row.id
        item["version"] = row.version
        item["artifact_type"] = row.artifact_type


def resolve_baseline(
    store: ArtifactStore,
    *,
    artifact_type: str,
    session_id: str | None = None,
    base_version_id: str | None = None,
) -> ArtifactVersion:
    """解析这次修改的基线版本（CONTEXT.md「基线」）。

    - 给了 `base_version_id`：就用它，但必须与本次修改的生成物类别一致（不给跨类改）；
    - 只给了会话：用该会话里这一类生成物的**当前版本**；
    - 都没有（不带会话的修改）：由调用方保持既有语义，不走这里。
    """
    if base_version_id is not None:
        baseline = store.get(version_id=base_version_id)
        if baseline is None:
            raise BaselineNotFound(f"生成物版本不存在: {base_version_id}")
        if baseline.artifact_type != artifact_type:
            raise BaselineMismatch(
                f"基线版本是{baseline.artifact_type}（第 {baseline.version} 版），"
                f"不能作为{artifact_type}修改的基线"
            )
        if session_id is not None and session_id != baseline.session_id:
            raise BaselineMismatch(f"基线版本不属于该备课会话: {base_version_id}")
        return baseline

    if session_id is not None:
        require_session(store, session_id)
    current = store.current(session_id=session_id or "", artifact_type=artifact_type)
    if current is None:
        raise BaselineNotFound(
            f"该备课会话里还没有{artifact_type}版本可作基线：请先生成一次{artifact_type}"
        )
    return current


def record_revision(
    store: ArtifactStore,
    *,
    baseline: ArtifactVersion,
    path: str,
    content: dict | None = None,
    title: str = "",
) -> ArtifactVersion:
    """以历史版本为基线修改：产出更高版本号的新版本，原版本保持可取回。"""
    if not Path(path).is_file():
        raise FileNotFoundError(f"生成物落盘文件不存在，拒绝留下无文件的版本记录: {path}")
    return store.record(
        session_id=baseline.session_id,
        artifact_type=baseline.artifact_type,
        filename=Path(path).name,
        content=content,
        # 标题沿用基线的生成物标题：同一生成物的各版本标题一致，区别在版本号
        title=title or baseline.title or baseline.artifact_type,
        origin=ORIGIN_REVISED,
        parent_id=baseline.id,
    )
