"""ORM 模型：对应 DESIGN.md §3.3 ER 图。"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)  # LLM 理解后的完整描述
    subject: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 学科
    chapter: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 章节
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 基础/进阶/难点
    importance: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 必修/选修/了解
    source_docs: Mapped[list | None] = mapped_column(JSON, nullable=True)  # 溯源引用
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    from_node: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_nodes.id"))
    to_node: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_nodes.id"))
    # 前置依赖 / 父子包含 / 推导关系 / 相关关联
    relation_type: Mapped[str] = mapped_column(String(20))


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20))  # 选择/填空/简答/综合
    source_type: Mapped[str] = mapped_column(String(20))  # 上传/网络/自编
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class QuestionKnowledge(Base):
    __tablename__ = "question_knowledge"

    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id"), primary_key=True
    )
    knowledge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_nodes.id"), primary_key=True
    )
    weight: Mapped[str] = mapped_column(String(10))  # 主考/涉及


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="处理中")  # 处理中/已完成/有冲突
    # 参考资料标记：教师上传时勾选，备课请求携带其 id 后检索加权并在产物中溯源
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)


class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    doc_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=True
    )
    new_knowledge: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    existing_knowledge: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diff_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="待审")  # 待审/已接受/已拒绝/并存
