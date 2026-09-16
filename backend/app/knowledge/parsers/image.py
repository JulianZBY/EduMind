"""图片解析：qwen-vl 多模态解读。"""

from app.core.llm.factory import get_llm
from app.knowledge.parsers.base import Parser

_PROMPT = "请描述这张图片的内容，包括文字、图表、公式等，用于教学知识提取。"


class ImageParser(Parser):
    async def parse(self, file_path: str) -> str:
        llm = get_llm()
        return await llm.vision(file_path, _PROMPT)
