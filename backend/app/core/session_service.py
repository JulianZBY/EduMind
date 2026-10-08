"""备课会话服务（core 层）：会话生命周期 + 一轮对话的落地。

事实源在服务端（ADR-0002）：会话、消息与累积意图全部落库，前端不再持有备课历史。
业务判断住本层与 `conversation`（状态机）；全部 ORM 读写委托 `db/sessions.py`（会话）与
`db/artifacts.py`（生成物版本）。
"""

import logging

from app.core.artifacts import attach_version_refs, register_generated_artifacts
from app.core.conversation import TurnOutcome, accumulate_intent, run_turn
from app.core.intent import TeachingIntent, intent_from_payload
from app.db.artifacts import ArtifactStore
from app.db.models import PrepSession, SessionMessage
from app.db.sessions import ConversationStore
from app.generate import remove_output_files

logger = logging.getLogger(__name__)

# 新建会话的初始名「未命名备课」（CONTEXT.md §2）：零表单直开，首条教师消息自动命名，
# 教师手动改名后（title_edited）不再自动改
UNNAMED_PREP_TITLE = "未命名备课"
# 自动标题取首轮需求的前 N 个字符
AUTO_TITLE_LENGTH = 30


def create_session(
    store: ConversationStore,
    *,
    title: str = "",
    granularity: str = "标准",
    reference_doc_ids: list[str] | None = None,
) -> PrepSession:
    """新建备课会话：零表单直开，标题留空时先叫「未命名备课」。"""
    return store.create(
        title=(title or "").strip() or UNNAMED_PREP_TITLE,
        granularity=granularity,
        reference_doc_ids=reference_doc_ids or [],
    )


def list_sessions(store: ConversationStore, *, keyword: str | None = None) -> list[PrepSession]:
    return store.list_sessions(keyword=keyword)


def get_history(
    store: ConversationStore, session_id: str
) -> tuple[PrepSession, list[SessionMessage]]:
    """会话 + 按序号排好的消息历史；会话不存在时抛 LookupError（路由转 404）。"""
    prep = store.get(session_id)
    if prep is None:
        raise LookupError(f"会话不存在: {session_id}")
    return prep, store.messages(session_id)


def update_session(
    store: ConversationStore,
    session_id: str,
    *,
    title: str | None = None,
    granularity: str | None = None,
    reference_doc_ids: list[str] | None = None,
) -> PrepSession:
    """重命名会话 / 改会话设置（追问粒度、参考资料）。"""
    prep = store.get(session_id)
    if prep is None:
        raise LookupError(f"会话不存在: {session_id}")
    return store.update(
        prep,
        title=title,
        # 教师手动改名：落库为标记，自动命名自此停用（CONTEXT.md「未命名备课」）
        title_edited=True if title is not None else None,
        granularity=granularity,
        reference_doc_ids=reference_doc_ids,
    )


def delete_session(store: ConversationStore, session_id: str) -> str:
    prep = store.get(session_id)
    if prep is None:
        raise LookupError(f"会话不存在: {session_id}")
    # 生成物版本随会话一起清掉，不留无主版本行（与消息同一口径）；落盘文件一并删除：
    # 版本记录没了以后这些文件不再属于任何备课，却仍能按文件名下载（见 docs/api/artifacts.md）。
    # 先删记录再删文件：中途失败时宁可留下无主文件，也不留下指向不存在文件的版本记录。
    artifacts = ArtifactStore(store.db)
    filenames = [v.filename for v in artifacts.list_versions(session_id=session_id)]
    artifacts.delete_for_session(session_id)
    store.delete(prep)
    removed = remove_output_files(filenames)
    if removed != len(filenames):
        logger.warning(
            "删除会话 %s：%d 个生成物文件里实际删掉 %d 个（其余已不在或无法删除）",
            session_id,
            len(filenames),
            removed,
        )
    return session_id


def load_intent(prep: PrepSession) -> TeachingIntent | None:
    """读会话上累积的意图；没落过（或结构不可用）时返回 None，由调用方全量分析。"""
    if not prep.intent:
        return None
    return intent_from_payload(prep.intent)


async def handle_turn(
    store: ConversationStore,
    session_id: str,
    utterance: str,
    *,
    reference_doc_ids: list[str] | None = None,
) -> TurnOutcome:
    """会话内一轮备课：累积意图 → 状态机（澄清 / 生成）→ 消息与意图落库。

    教师随时可换设备回到同一会话：历史与累积意图都在库里，不依赖浏览器。
    """
    prep = store.get(session_id)
    if prep is None:
        raise LookupError(f"会话不存在: {session_id}")
    previous_title = prep.title
    # 首条教师消息自动命名（CONTEXT.md「未命名备课」）：只认未改名且仍叫初始名的会话，
    # 手动改名（title_edited）后教师取的名字不再被覆盖
    if not prep.title_edited and prep.title == UNNAMED_PREP_TITLE:
        prep.title = utterance[:AUTO_TITLE_LENGTH]
    teacher_message = store.append_message(prep, role="user", content=utterance)

    try:
        intent = await accumulate_intent(load_intent(prep), utterance)
        outcome = await run_turn(
            utterance,
            intent=intent,
            granularity=prep.granularity,
            # 会话上的参考资料为准；请求里的显式标识仅在不带会话时生效
            reference_doc_ids=reference_doc_ids or prep.reference_doc_ids,
        )

        # 生成即入库（ADR-0002）：本轮产出逐件落版本记录，并把版本标识回填进产物
        if outcome.artifacts:
            recorded = register_generated_artifacts(
                ArtifactStore(store.db),
                session_id=prep.id,
                artifacts=outcome.artifacts,
                topic=outcome.intent.topic,
            )
            attach_version_refs(outcome.artifacts, recorded)

        store.append_message(
            prep,
            role="assistant",
            content=outcome.content,
            kind=outcome.reply_kind,
            artifacts=outcome.artifacts,
        )
        store.save_intent(prep, outcome.intent.model_dump())
    except Exception:
        # 这一轮没成（例如生成失败 502）：撤掉刚落的教师消息，让「失败不留痕」在库里也成立——
        # 前端发送失败会回滚这条并让教师重发，留着它重发后会变成两条一模一样的。
        store.discard_message(prep, teacher_message, restore_title=previous_title)
        raise
    return outcome


async def run_stateless_turn(
    history_text: str,
    *,
    utterance: str | None = None,
    granularity: str = "标准",
    reference_doc_ids: list[str] | None = None,
) -> TurnOutcome:
    """不带会话的一轮备课：整段历史由调用方带上，意图全量重析（收编前的既有行为）。

    `history_text` 是全量重析的输入（整段教师需求）；`utterance` 是本轮原话，
    供跳过追问的语义判定使用，不传时按整段历史判定。
    """
    intent = await accumulate_intent(None, history_text)
    return await run_turn(
        utterance if utterance is not None else history_text,
        intent=intent,
        granularity=granularity,
        reference_doc_ids=reference_doc_ids,
    )
