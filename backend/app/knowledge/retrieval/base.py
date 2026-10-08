"""检索策略接口：调用方只消费返回结果，不计权重、不走图谱邻接、不拼溯源字段（ADR-0003）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 只用于类型标注：检索策略住 knowledge 层，不在运行时依赖 core 的领域模型
    from app.core.intent import TeachingIntent


@dataclass(frozen=True)
class RetrievalHit:
    """一次命中的分块：分块编号 + 距离 + 来源资料 id + 正文（可回溯来源资料）。"""

    chunk_id: int
    distance: float
    doc_id: str
    content: str


@dataclass
class RetrievalResult:
    """检索结果：生成上下文 + 命中来源资料名（溯源共用）+ 本次命中明细与融合知识点。

    `graph_nodes` 为沿图谱邻接拉到、参与上下文组装的知识点（超出预算的会被截断，
    实际进入上下文的内容以 `context` 为准）。
    """

    context: str
    sources: list[str]
    hits: list[RetrievalHit] = field(default_factory=list)
    graph_nodes: list[dict] = field(default_factory=list)
    # 空命中的口径（票 01）：True = 向量库本身一个分块都没有（「知识库为空」）；
    # False = 库里可能有内容但本次没命中 / 检索失败（「知识库未命中相关内容」）。
    # 只在 hits 为空时有意义；回复文案据此诚实二选一，不再一律说「知识库为空」。
    library_empty: bool = False

    @classmethod
    def empty(cls, library_empty: bool = False) -> "RetrievalResult":
        """没有可检内容或检索失败时的空结果（既有降级行为）。

        `library_empty` 区分两种空：库里没东西，与库里有东西但没命中（票 01）。
        """
        return cls(context="", sources=[], library_empty=library_empty)


class Retriever(ABC):
    """检索策略：一种取知识的方式，按配置名选择（ADR-0003）。"""

    name: str = ""

    @abstractmethod
    async def retrieve(
        self,
        intent: "TeachingIntent",
        top_k: int = 5,
        reference_doc_ids: list[str] | None = None,
    ) -> RetrievalResult:
        """按备课意图取命中分块与来源；向量库为空或检索失败时降级为空结果。"""
