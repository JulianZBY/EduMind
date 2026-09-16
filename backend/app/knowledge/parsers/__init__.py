"""解析器注册表：按文件类型分发。"""

from app.knowledge.parsers.audio import AudioParser
from app.knowledge.parsers.base import Parser
from app.knowledge.parsers.image import ImageParser
from app.knowledge.parsers.pdf import PdfParser
from app.knowledge.parsers.ppt import PptParser
from app.knowledge.parsers.video import VideoParser
from app.knowledge.parsers.word import WordParser

_PARSERS: dict[str, type[Parser]] = {
    "pdf": PdfParser,
    "doc": WordParser,
    "docx": WordParser,
    "ppt": PptParser,
    "pptx": PptParser,
    "png": ImageParser,
    "jpg": ImageParser,
    "jpeg": ImageParser,
    "mp4": VideoParser,
    "avi": VideoParser,
    "mov": VideoParser,
    # 录音：paraformer-v2 支持的常见音频容器（alaw/ape 等冷门格式不注册）
    "mp3": AudioParser,
    "wav": AudioParser,
    "m4a": AudioParser,
    "aac": AudioParser,
    "flac": AudioParser,
    "ogg": AudioParser,
    "oga": AudioParser,
    "opus": AudioParser,
    "wma": AudioParser,
    "amr": AudioParser,
}


def get_parser(file_type: str) -> Parser:
    cls = _PARSERS.get(file_type.lower())
    if cls is None:
        raise ValueError(f"不支持的格式: {file_type}")
    return cls()
