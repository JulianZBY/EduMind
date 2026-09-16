"""录音解析：转写 provider（paraformer 真实云端 / stub 无 key 可跑）→ 文字稿。"""

from app.core.asr.factory import get_transcriber
from app.knowledge.parsers.base import Parser


class AudioParser(Parser):
    async def parse(self, file_path: str) -> str:
        return await get_transcriber().transcribe(file_path)
