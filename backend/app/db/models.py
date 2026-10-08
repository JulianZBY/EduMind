"""ORM 模型：全部持久化表（备课会话 / 消息 / 文档 / 知识点 / 关系 / 冲突 / 题库）。

字段语义写在每个模型与列的中文注释里：新表进本文件是分层铁律（见 `backend/AGENTS.md`）。
持久化决策与分层见 `docs/architecture.md`（一页图与分层表）与
`docs/adr/0002-backend-source-of-truth.md`（后端是备课会话与生成物的唯一事实源）。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PrepSession(Base):
    """备课会话（CONTEXT.md「备课会话」）：围绕一节课的一次完整备课过程，跨设备回看。"""

    __tablename__ = "prep_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(
        String(200)
    )  # 会话标题：新建先叫「未命名备课」，首条教师消息自动命名；教师手动改名后不再自动改
    # 教师是否手动改过名：True 后自动命名停用，后续对话不再覆盖教师取的名字（票 04「未命名备课」）
    title_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    granularity: Mapped[str] = mapped_column(String(20), default="标准")  # 追问粒度：快速/标准/精细
    # 累积意图：上一轮意图 + 本轮新增（避免每轮把全部对话重析一遍）
    intent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 本次备课勾选的参考资料（文档 id）：检索加权并在生成物中溯源
    reference_doc_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    # 消息随会话级联删除：会话没了，其历史不再留孤儿行
    messages: Mapped[list["SessionMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionMessage(Base):
    """会话消息（CONTEXT.md「消息」）：一条对话内容，分教师说的与助手说的。"""

    __tablename__ = "session_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("prep_sessions.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)  # 会话内消息序号：从 1 单调递增，历史按此排序
    role: Mapped[str] = mapped_column(String(20))  # user = 教师说的 / assistant = 助手说的
    content: Mapped[str] = mapped_column(Text)  # 消息原话
    # 回复形态：澄清回复 / 生成回复（CONTEXT.md）；教师消息没有形态，为空
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 生成回复携带的生成物与命中来源；澄清回复为空
    artifacts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    session: Mapped["PrepSession"] = relationship(back_populates="messages")


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


class AppSetting(Base):
    """设置项（CONTEXT.md「设置」）：设置页写入的云端能力与模型档位。

    配置优先级：设置库 > `.env` 引导默认 > 代码默认（ADR-0003）。没写过（或被写空清除）的项
    回落引导默认；写入后立即生效、不需要重启（见 `app/core/settings_store.py`）。
    """

    __tablename__ = "app_settings"

    # 设置项名：与 Settings 字段同名，可选范围由 app/core/catalog.py 的 FIELDS 登记决定
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 设置项的值：统一存字符串；API Key 项存原文（回读一律掩码，响应与表单都不回显明文）
    value: Mapped[str] = mapped_column(Text)
    # 最后一次改动时间：设置页可据此提示「刚刚生效」
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

class LLMProviderInstance(Base):
    """已添加的供应商实例（多供应商并存；CONTEXT.md「供应商目录」的多供应商形态）。

    一行 = 设置页「添加供应商」产生的一条：目录家（千问 / DeepSeek / Kimi / GLM / MiniMax /
    豆包 / 硅基流动）或「自定义 OpenAI 兼容服务」。任务级模型按 `task_provider_*` 指到这里；
    `default_provider_instance` 设置项指到默认那一条。
    API Key 存原文（与 app_settings 同口径），回读一律掩码、响应与表单都不回显明文。
    """

    __tablename__ = "llm_provider_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # 方言 id（catalog PROVIDERS 的取值；custom = 自定义 OpenAI 兼容服务）
    provider: Mapped[str] = mapped_column(String(50))
    # 面向教师的名称：目录家用方言 label；自定义服务由教师命名
    label: Mapped[str] = mapped_column(String(100))
    # 覆盖预设地址（空 = 用方言预设；自定义服务必填）
    base_url: Mapped[str] = mapped_column(String(500), default="")
    # 覆盖默认模型（空 = 用方言默认；兼容旧行，新添加不再选模型）
    model: Mapped[str] = mapped_column(String(200), default="")
    # 该实例的 API Key（只入库；回读走掩码）
    api_key: Mapped[str] = mapped_column(Text, default="")
    # 上次模型拉取失败的原因（空 = 拉取成功或尚未拉取；模型清单存 provider_models 表）
    models_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


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
    # 解析失败的原因（面向教师的一句话；非「失败」状态为空）：让教师知道该重传、换格式还是去配置
    failure_reason: Mapped[str] = mapped_column(Text, default="")


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
    # 冲突类别（CONTEXT.md 第 6 节）：定义冲突 / 结构冲突 / 常识存疑。
    # 类别是「检测来源」的标记，不能靠裁决动作反推——同一动作在不同类别下含义不同
    # （例如「并存」对常识错误没有意义）。默认与回填口径见 ADR-0006。
    category: Mapped[str] = mapped_column(String(20), default="定义冲突", server_default="定义冲突")
    # 常识存疑「编辑修正后入库」实际入库的正文；原文留在 new_knowledge 里，两条都留痕，
    # 教师日后能看出「原来的说法」与「最终入库的说法」的差别（ADR-0004）。
    revised_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 教师最终选的动作（审核痕迹）：常识存疑的「照常入库」与「编辑修正后入库」终态同为
    # 已接受，只靠 status 分不出教师走的是哪条出路。
    review_action: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ArtifactVersion(Base):
    """生成物版本（CONTEXT.md「版本」）：某一生成物的一次产出记录，一条记录对应一个落盘文件。

    - 同一生成物 + 同一会话内每次产出都形成新版本，版本号从 1 单调递增；
    - `parent_id` 是「由哪一版衍生而来」（CONTEXT.md「基线」）：修改记传入的基线版本，
      同一生成物的再次生成记上一次产出——全部版本连同该关系构成版本树；
    - 「当前版本」= 版本号最高的那一版，只是列表与预览默认打开的一版，没有特殊权威。
    """

    __tablename__ = "artifact_versions"
    # 同一会话内「同一生成物 + 同一版本号」只允许一行：版本号单调递增的兜底约束
    __table_args__ = (
        UniqueConstraint("session_id", "artifact_type", "version", name="uq_artifact_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("prep_sessions.id"), index=True
    )  # 所属备课会话
    artifact_type: Mapped[str] = mapped_column(
        String(20), index=True
    )  # 生成物类别：课件/教案/提纲/试卷/互动内容
    version: Mapped[int] = mapped_column(Integer)  # 同一会话同一生成物的版本号：从 1 单调递增
    origin: Mapped[str] = mapped_column(String(20), default="生成")  # 产出方式：生成 / 修改
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("artifact_versions.id"), nullable=True
    )  # 基线版本（版本树的父节点）；首次生成为空
    filename: Mapped[str] = mapped_column(String(255))  # 落盘文件名：一个版本对应一个文件
    title: Mapped[str] = mapped_column(String(200), default="")  # 生成物标题：教师认这一版是什么
    # 版本内容快照（课件 slides / 教案结构 / 提纲正文 / 题目 / 互动内容 HTML），
    # 供版本详情直接回看；落盘文件仍是下载与预览的字节源
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ProviderModel(Base):
    """供应商实例的模型清单（添加/刷新时从服务商 `GET /v1/models` 拉取并缓存）。

    设置页的统一模型池由此表组装：每条模型带它属于哪个实例（哪家供应商）。
    拉取失败时不落行——该家模型池为空，界面走「手动填写」兜底，稍后可点刷新重试。
    """

    __tablename__ = "provider_models"
    __table_args__ = (
        UniqueConstraint("instance_id", "model_id", name="uq_provider_instance_model"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("llm_provider_instances.id"), index=True
    )
    model_id: Mapped[str] = mapped_column(String(200))  # 服务商返回的模型 id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
