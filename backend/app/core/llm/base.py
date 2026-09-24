"""LLM 网关统一接口（对话 / 多模态）。

向量化（Embedder）见 `app.core.embedding`，搜索与 PDF 解析归属不同服务商，
见 `app.core.search` / `app.core.parser`——调用方只依赖各自接口，不依赖 provider 实现。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str  # system / user / assistant
    content: str


@dataclass
class ChatResult:
    content: str
    raw: dict | None = None


class LLMProvider(ABC):
    """对话 / 多模态 统一抽象。"""

    name: str = "base"

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        """多轮对话 / 意图理解 / 内容生成。"""

    async def vision(self, image_path: str, prompt: str) -> str:
        """多模态：图片 / 视频帧理解。"""
        raise NotImplementedError
