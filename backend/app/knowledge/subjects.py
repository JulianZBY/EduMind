"""学科清单与归类约束：初始化、维护和入库共用唯一事实源（票 08）。"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Subject

UNCLASSIFIED = "未分类"
DEFAULT_SUBJECTS = (
    "语文",
    "数学",
    "英语",
    "物理",
    "化学",
    "生物",
    "历史",
    "地理",
    "政治",
    "信息技术",
)


def normalize_subject(value: object, names: set[str]) -> str:
    """单一字符串且在当前清单内才有效；空值、多值和清单外值归「未分类」。"""
    name = value.strip() if isinstance(value, str) else ""
    return name if name in names else UNCLASSIFIED


def initialize_subjects(bind, *, seed: bool) -> None:
    """仅首次建清单时内置基础学科；后续启动不复活教师已删除的学科。

    SQLite 触发器兼容已有 knowledge_nodes 表，不重建有外键引用的知识点表。
    直接 SQL 写入同样受约束；更名联动更新、删除归未分类在同一事务完成。
    """
    with bind.begin() as conn:
        names = (*DEFAULT_SUBJECTS, UNCLASSIFIED) if seed else (UNCLASSIFIED,)
        for name in names:
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO subjects (id, name) VALUES (?, ?)",
                (str(uuid.uuid4()), name),
            )
        conn.exec_driver_sql(
            "UPDATE knowledge_nodes SET subject='未分类' "
            "WHERE subject IS NULL OR subject NOT IN (SELECT name FROM subjects)"
        )
        for operation in ("INSERT", "UPDATE"):
            conn.exec_driver_sql(
                f"CREATE TRIGGER IF NOT EXISTS knowledge_subject_{operation.lower()} "
                f"BEFORE {operation} ON knowledge_nodes "
                "WHEN NEW.subject IS NULL OR NEW.subject NOT IN (SELECT name FROM subjects) "
                "BEGIN SELECT RAISE(ABORT, '学科必须在清单内'); END"
            )
        conn.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS subject_rename AFTER UPDATE OF name ON subjects "
            "BEGIN UPDATE knowledge_nodes SET subject=NEW.name WHERE subject=OLD.name; END"
        )
        conn.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS subject_delete BEFORE DELETE ON subjects "
            "BEGIN UPDATE knowledge_nodes SET subject='未分类' WHERE subject=OLD.name; END"
        )
        conn.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS subject_reserved_update BEFORE UPDATE OF name ON subjects "
            "WHEN OLD.name='未分类' AND NEW.name != OLD.name "
            "BEGIN SELECT RAISE(ABORT, '未分类不能更名'); END"
        )
        conn.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS subject_reserved_delete BEFORE DELETE ON subjects "
            "WHEN OLD.name='未分类' "
            "BEGIN SELECT RAISE(ABORT, '未分类不能删除'); END"
        )


class SubjectError(ValueError):
    """清单维护的业务错误；薄路由只映射状态码。"""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def list_subjects(db: Session) -> list[Subject]:
    return list(db.scalars(select(Subject).order_by(Subject.name)))


def maintain_subject(
    db: Session, *, name: str | None = None, subject_id: str | None = None
) -> dict:
    """新建 / 更名 / 删除：唯一名称校验与知识点联动都在事务内。"""
    subject = db.get(Subject, subject_id) if subject_id else None
    if subject_id and subject is None:
        raise SubjectError(404, "学科不存在。")
    if subject and subject.name == UNCLASSIFIED:
        raise SubjectError(409, "「未分类」用于归类兜底，不能更名或删除。")
    if name is not None:
        name = name.strip()
        if not name or len(name) > 100 or "\n" in name or "\r" in name:
            raise SubjectError(400, "学科名称须为一行，包含 1～100 个字符。")
        if subject is None:
            subject = Subject(name=name)
            db.add(subject)
        else:
            subject.name = name
    elif subject:
        db.delete(subject)
    else:
        raise SubjectError(400, "请填写学科名称。")
    try:
        db.flush()
        result = {"id": subject.id, "name": subject.name}
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SubjectError(409, "学科名称已在清单内，请使用其他名称。") from exc
    return result
