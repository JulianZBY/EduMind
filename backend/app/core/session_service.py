"""备课会话服务（core 层）：会话生命周期 + 一轮对话的落地。

事实源在服务端（ADR-0002）：会话、消息与累积意图全部落库，前端不再持有备课历史。
业务判断住本层与 `conversation`（状态机）；全部 ORM 读写委托 `db/sessions.py`。
"""

from app.core.conversation import TurnOutcome, accumulate_intent, run_turn
from app.core.intent import TeachingIntent, intent_from_payload
from app.db.models import PrepSession, SessionMessage
from app.db.sessions import ConversationStore

# 新建会话的占位标题：首轮教师需求自动充当标题（改用 CONTEXT.md 术语，不用「未命名」）
SESSION_TITLE_PLACEHOLDER = "新的备课会话"
# 自动标题取首轮需求的前 N 个字符
AUTO_TITLE_LENGTH = 30


def create_session(
    store: ConversationStore,
    *,
    title: str = "",
    granularity: str = "标准",
    reference_doc_ids: list[str] | None = None,
) -> PrepSession:
    """新建备课会话：标题留空时先用占位标题，等首轮需求自动替换。"""
    return store.create(
        title=(title or "").strip() or SESSION_TITLE_PLACEHOLDER,
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
        prep, title=title, granularity=granularity, reference_doc_ids=reference_doc_ids
    )


def delete_session(store: ConversationStore, session_id: str) -> str:
    prep = store.get(session_id)
    if prep is None:
        raise LookupError(f"会话不存在: {session_id}")
    store.delete(prep)
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
    if prep.title == SESSION_TITLE_PLACEHOLDER:
        prep.title = utterance[:AUTO_TITLE_LENGTH]  # 首轮需求充当会话标题
    store.append_message(prep, role="user", content=utterance)

    intent = await accumulate_intent(load_intent(prep), utterance)
    outcome = await run_turn(
        utterance,
        intent=intent,
        granularity=prep.granularity,
        # 会话上的参考资料为准；请求里的显式标识仅在不带会话时生效
        reference_doc_ids=reference_doc_ids or prep.reference_doc_ids,
    )

    store.append_message(
        prep,
        role="assistant",
        content=outcome.content,
        kind=outcome.reply_kind,
        artifacts=outcome.artifacts,
    )
    store.save_intent(prep, outcome.intent.model_dump())
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
