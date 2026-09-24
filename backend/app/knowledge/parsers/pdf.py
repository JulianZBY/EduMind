"""PDF 解析：策略由 app.core.parser 工厂按配置选择（mineru / pypdf / 云端失败退 pypdf）。"""

from app.core.parser.factory import get_pdf_parser
from app.knowledge.parsers.base import Parser


class PdfParser(Parser):
    async def parse(self, file_path: str) -> str:
        return await get_pdf_parser().parse(file_path)
