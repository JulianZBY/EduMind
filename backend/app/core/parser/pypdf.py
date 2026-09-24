"""本地 PDF 文本层抽取（pypdf）：不依赖云端的策略，也是 mineru 的兜底。"""

from pypdf import PdfReader

from app.core.parser.base import PdfParser


class PypdfParser(PdfParser):
    name = "pypdf"

    async def parse(self, pdf_path: str) -> str:
        reader = PdfReader(pdf_path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
