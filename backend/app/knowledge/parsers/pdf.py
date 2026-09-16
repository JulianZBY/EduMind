"""PDF 解析：MinerU 云端（主）+ pypdf 本地文本层兜底。"""

from app.core.parser.mineru import MinerUParser
from app.knowledge.parsers.base import Parser


class PdfParser(Parser):
    async def parse(self, file_path: str) -> str:
        try:
            return await MinerUParser().parse(file_path)
        except Exception:  # noqa: BLE001 - 主路径失败兜底到本地 pypdf
            # 本地兜底：pypdf 抽文本层
            from pypdf import PdfReader

            reader = PdfReader(file_path)
            return "\n".join((p.extract_text() or "") for p in reader.pages)
