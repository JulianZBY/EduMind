"""解析器抽象。"""

from abc import ABC, abstractmethod


class Parser(ABC):
    @abstractmethod
    async def parse(self, file_path: str) -> str:
        """解析文件，返回文本 / Markdown。"""
