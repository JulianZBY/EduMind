"""录音解析：转写 provider（paraformer 云端，需百炼 Key）→ 文字稿；未配置时给出引导。"""

from app.core.asr.factory import get_transcriber
from app.knowledge.parsers.base import Parser


class AudioParser(Parser):
    async def parse(self, file_path: str) -> str:
        return await get_transcriber().transcribe(file_path)
