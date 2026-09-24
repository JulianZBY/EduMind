"""备课会话与消息的读写（持久层：只有 ORM 读写，不含业务判断）。

事实源后移（ADR-0002）：会话与消息落 SQLite，前端不再持有备课历史。
业务判断（澄清 / 追问 / 意图累积）住 `core/`，本模块只负责存与取。
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import PrepSession, SessionMessage

# 单用户假设：无鉴权，所有数据挂在 default 用户下（与 documents / conflicts 同一口径）
DEFAULT_USER_ID = "default"


class ConversationStore:
    """会话与消息的读写句柄：一个请求一个实例，包住当次请求的 SQLAlchemy session。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, *, title: str, granularity: str, reference_doc_ids: list[str]) -> PrepSession:
        prep = PrepSession(
            user_id=DEFAULT_USER_ID,
            title=title,
            granularity=granularity,
            reference_doc_ids=list(reference_doc_ids),
        )
        self.db.add(prep)
        self.db.commit()
        self.db.refresh(prep)
        return prep

    def list_sessions(self, *, keyword: str | None = None) -> list[PrepSession]:
        """会话列表：最近使用在前；`keyword` 非空时按标题过滤（会话列表检索）。"""
        query = self.db.query(PrepSession).filter(PrepSession.user_id == DEFAULT_USER_ID)
        if keyword:
            query = query.filter(PrepSession.title.contains(keyword))
        return query.order_by(PrepSession.updated_at.desc()).all()

    def get(self, session_id: str) -> PrepSession | None:
        prep = self.db.get(PrepSession, session_id)
        if prep is None or prep.user_id != DEFAULT_USER_ID:
            return None
        return prep

    def update(
        self,
        prep: PrepSession,
        *,
        title: str | None = None,
        granularity: str | None = None,
        reference_doc_ids: list[str] | None = None,
    ) -> PrepSession:
        """按传入字段更新；未传的字段保持原值（重命名与改设置共用）。"""
        if title is not None:
            prep.title = title
        if granularity is not None:
            prep.granularity = granularity
        if reference_doc_ids is not None:
            prep.reference_doc_ids = list(reference_doc_ids)
        # 沿用既有表的时间口径：naive 本地时间（见 models.py 的 DateTime 列）
        prep.updated_at = datetime.now()  # noqa: DTZ005
        self.db.commit()
        self.db.refresh(prep)
        return prep

    def delete(self, prep: PrepSession) -> None:
        """删会话连同其消息：不留孤儿消息行。"""
        self.db.query(SessionMessage).filter(SessionMessage.session_id == prep.id).delete()
        self.db.delete(prep)
        self.db.commit()

    def messages(self, session_id: str) -> list[SessionMessage]:
        return (
            self.db.query(SessionMessage)
            .filter(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.seq)
            .all()
        )

    def message_count(self, session_id: str) -> int:
        return self.db.query(SessionMessage).filter(SessionMessage.session_id == session_id).count()

    def append_message(
        self,
        prep: PrepSession,
        *,
        role: str,
        content: str,
        kind: str | None = None,
        artifacts: dict | None = None,
    ) -> SessionMessage:
        """追加一条消息：序号在会话内单调递增，并把会话的最近使用时间前移。"""
        message = SessionMessage(
            session_id=prep.id,
            user_id=DEFAULT_USER_ID,
            seq=self.message_count(prep.id) + 1,
            role=role,
            content=content,
            kind=kind,
            artifacts=artifacts,
        )
        self.db.add(message)
        # 沿用既有表的时间口径：naive 本地时间（见 models.py 的 DateTime 列）
        prep.updated_at = datetime.now()  # noqa: DTZ005
        self.db.commit()
        self.db.refresh(message)
        return message

    def save_intent(self, prep: PrepSession, intent: dict) -> None:
        """把按会话累积的意图落库，供下一轮增量累积（不重析全部历史）。"""
        prep.intent = intent
        self.db.commit()
