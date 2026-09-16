"""数据库引擎与初始化。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# SQLite 在 FastAPI 多线程下需关闭同线程检查
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _ensure_sqlite_columns() -> None:
    """轻量幂等迁移：create_all 不会修改已有表，新增列用 ALTER TABLE 补齐（SQLite）。"""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(documents)")}
        if cols and "is_reference" not in cols:
            conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN is_reference BOOLEAN DEFAULT 0")
            conn.commit()


def init_db() -> None:
    """建表（幂等）+ 补列（幂等）+ 确保默认用户。"""
    from app.db.models import Base, User

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
    # 单用户假设：无鉴权，所有数据挂在 default 用户下，预留多用户扩展
    with SessionLocal() as db:
        if not db.query(User).filter(User.id == "default").first():
            db.add(User(id="default", name="default"))
            db.commit()


def get_session():
    """FastAPI 依赖：请求级 session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
