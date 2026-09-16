"""转写器抽象。"""

from abc import ABC, abstractmethod


class Transcriber(ABC):
    name: str = "base"

    @abstractmethod
    async def transcribe(self, file_path: str) -> str:
        """转写音频文件，返回文字稿文本。"""
