"""生成物版本的读写（持久层：只有 ORM 读写，不含业务判断）。

生成物全版本留痕（ADR-0002）：每次产出都落一条版本记录，一条记录对应一个落盘文件。
业务判断（什么算同一生成物、以哪一版为基线、版本链怎么接）住 `core/artifacts.py`。
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import ArtifactVersion

# 单用户假设：无鉴权，所有数据挂在 default 用户下（与 sessions / documents 同一口径）
DEFAULT_USER_ID = "default"


class ArtifactStore:
    """生成物版本的读写句柄：一个请求一个实例，包住当次请求的 SQLAlchemy session。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def next_version(self, *, session_id: str, artifact_type: str) -> int:
        """同一会话内同一生成物的下一个版本号 = 当前最大版本号 + 1（单调递增）。

        ORM 语句由 SQLAlchemy 编译为参数化查询（参数经绑定传入，非字符串拼接）。
        """
        latest = self.db.execute(
            select(func.max(ArtifactVersion.version)).where(
                ArtifactVersion.session_id == session_id,
                ArtifactVersion.artifact_type == artifact_type,
            )
        ).scalar()
        return (latest or 0) + 1

    def record(
        self,
        *,
        session_id: str,
        artifact_type: str,
        filename: str,
        content: dict | None = None,
        title: str = "",
        origin: str = "生成",
        parent_id: str | None = None,
    ) -> ArtifactVersion:
        """追加一条版本记录：版本号由库内现状算出，调用方不传版本号。"""
        row = ArtifactVersion(
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
            artifact_type=artifact_type,
            version=self.next_version(session_id=session_id, artifact_type=artifact_type),
            origin=origin,
            parent_id=parent_id,
            filename=filename,
            title=title,
            content=content,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_for_session(self, session_id: str) -> None:
        """会话被删除时连同其版本记录一起清掉：不留无主版本行（与消息的清理同一口径）。"""
        db: Session = self.db
        db.execute(delete(ArtifactVersion).where(ArtifactVersion.session_id == session_id))
        db.commit()

    def list_versions(
        self, *, session_id: str, artifact_type: str | None = None
    ) -> list[ArtifactVersion]:
        """某次备课的全部版本（同一生成物内按版本号升序）；可按生成物类别过滤。"""
        db: Session = self.db
        if artifact_type is None:
            rows = db.execute(
                select(ArtifactVersion)
                .where(ArtifactVersion.session_id == session_id)
                .order_by(ArtifactVersion.artifact_type, ArtifactVersion.version)
            )
        else:
            rows = db.execute(
                select(ArtifactVersion)
                .where(
                    ArtifactVersion.session_id == session_id,
                    ArtifactVersion.artifact_type == artifact_type,
                )
                .order_by(ArtifactVersion.artifact_type, ArtifactVersion.version)
            )
        return list(rows.scalars().all())

    def get(self, *, version_id: str) -> ArtifactVersion | None:
        row = self.db.get(ArtifactVersion, version_id)
        if row is None or row.user_id != DEFAULT_USER_ID:
            return None
        return row

    def current(self, *, session_id: str, artifact_type: str) -> ArtifactVersion | None:
        """当前版本（CONTEXT.md）：该生成物版本号最高的那一版。"""
        rows = self.db.execute(
            select(ArtifactVersion)
            .where(
                ArtifactVersion.session_id == session_id,
                ArtifactVersion.artifact_type == artifact_type,
            )
            .order_by(ArtifactVersion.version.desc())
        )
        return rows.scalars().first()
