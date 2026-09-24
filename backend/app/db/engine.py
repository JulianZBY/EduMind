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


# 轻量幂等迁移用的补列清单：(表, 列, 列定义)。create_all 不会修改已有表，故新增列在这里补齐。
_LEGACY_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("documents", "is_reference", "BOOLEAN DEFAULT 0"),
    ("conflicts", "category", "VARCHAR(20) DEFAULT '定义冲突'"),
    ("conflicts", "revised_content", "TEXT"),
    ("conflicts", "review_action", "VARCHAR(20)"),
)


def _ensure_sqlite_columns(bind=None) -> None:
    """轻量幂等迁移：补列 + 回填（默认库为 SQLite）。

    - 补列：create_all 不会修改已有表，新增列用 `ALTER TABLE` 补齐（SQLite）；
    - 回填：`conflicts.category` 落地前只有定义冲突这一类检测在产出冲突，
      故存量冲突一律回填为「定义冲突」，老库与新库的队列呈现一致（见 ADR-0006）；
    - 幂等：列已存在、行已有类别时都是空操作，可重复调用。

    参数 `bind` 只给测试用（拿临时库验迁移）；生产走模块级 `engine`。
    """
    target = bind if bind is not None else engine
    with target.connect() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for table, column, ddl in _LEGACY_COLUMNS:
            if table not in tables:
                continue
            cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                conn.commit()
        if "conflicts" in tables:
            conn.exec_driver_sql(
                "UPDATE conflicts SET category = '定义冲突' WHERE category IS NULL OR category = ''"
            )
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
