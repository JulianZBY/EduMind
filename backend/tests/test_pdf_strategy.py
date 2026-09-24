"""PDF 解析三策略 + 兜底：mineru / pypdf / mineru 失败退 pypdf，经配置切换，调用方零改动。"""

import io
import zipfile

import httpx
import pytest

import app.core.parser.factory as pdf_factory_module
from app.config import settings
from app.core.parser.base import PdfParser
from app.core.parser.factory import get_pdf_parser
from app.core.parser.fallback import FallbackPdfParser
from app.core.parser.mineru import MinerUParser
from app.core.parser.pypdf import PypdfParser
from app.knowledge.parsers.pdf import PdfParser as KnowledgePdfParser

PDF_TEXT = "TCP three-way handshake curriculum"
MINERU_MARKDOWN = "# MinerU 解析结果\nTCP 三次握手"

# 最小单页 PDF 的对象定义：xref 偏移由 _make_pdf 精确计算
_PAGE_OBJECT = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources 5 0 R /Contents 4 0 R >>"


def _make_pdf(text: str = PDF_TEXT) -> bytes:
    """手写最小单页 PDF（含可抽取文本层）：不为测试引入新的 PDF 生成依赖。"""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    length = str(len(content)).encode()
    stream = b"<< /Length " + length + b" >>\nstream\n" + content + b"\nendstream"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        _PAGE_OBJECT,
        stream,
        b"<< /Font << /F1 6 0 R >> >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def _pdf_file(tmp_path) -> str:
    path = tmp_path / "讲义.pdf"
    path.write_bytes(_make_pdf())
    return str(path)


def _zip_with_markdown(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("full.md", text)
    return buf.getvalue()


def _mineru_transport(*, state: str, uploaded: dict | None = None) -> httpx.MockTransport:
    """MinerU 云端全流程桩：申请上传地址 → PUT → 轮询 → 下载 zip。"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v4/file-urls/batch":
            assert request.headers["Authorization"] == "Bearer sk-mineru"
            assert request.content and "讲义.pdf".encode() in request.content
            return httpx.Response(
                200,
                json={"data": {"batch_id": "b1", "file_urls": ["https://upload.test/put"]}},
            )
        if request.url.host == "upload.test":
            if uploaded is not None:
                uploaded["content"] = request.content
            return httpx.Response(200)
        if path == "/api/v4/extract-results/batch/b1":
            if state == "done":
                item = {"state": "done", "full_zip_url": "https://zip.test/r.zip"}
            else:
                item = {"state": "failed", "err_msg": "云端解析失败"}
            return httpx.Response(200, json={"data": {"extract_result": [item]}})
        if request.url.host == "zip.test":
            return httpx.Response(200, content=_zip_with_markdown(MINERU_MARKDOWN))
        raise AssertionError(f"未预期的请求: {request.url}")

    return httpx.MockTransport(handler)


def _use_mineru_transport(monkeypatch, transport: httpx.MockTransport) -> None:
    """把注入了 transport 的 MinerU 换进工厂：不改工厂逻辑，只换出网通道。"""
    monkeypatch.setattr(
        pdf_factory_module,
        "MinerUParser",
        lambda token=None: MinerUParser(token=token, transport=transport),
    )
    get_pdf_parser.cache_clear()


@pytest.fixture(autouse=True)
def _clean_pdf_config(monkeypatch):
    get_pdf_parser.cache_clear()
    monkeypatch.setattr(settings, "pdf_strategy", "mineru_then_pypdf")
    monkeypatch.setattr(settings, "mineru_token", "")
    yield
    get_pdf_parser.cache_clear()


async def test_pypdf_strategy_reads_local_text_layer(tmp_path):
    """策略 pypdf：纯本地解析，不碰云端（无 Key 也能跑）。"""
    assert isinstance(PypdfParser(), PdfParser)
    assert PDF_TEXT in await PypdfParser().parse(_pdf_file(tmp_path))


async def test_mineru_strategy_runs_full_cloud_flow(tmp_path, monkeypatch):
    """策略 mineru：申请上传地址 → PUT → 轮询 done → 取 zip 里的 Markdown。"""
    uploaded: dict = {}
    _use_mineru_transport(monkeypatch, _mineru_transport(state="done", uploaded=uploaded))
    monkeypatch.setattr(settings, "pdf_strategy", "mineru")
    monkeypatch.setattr(settings, "mineru_token", "sk-mineru")
    get_pdf_parser.cache_clear()

    result = await get_pdf_parser().parse(_pdf_file(tmp_path))

    assert result == MINERU_MARKDOWN
    assert uploaded["content"] == _make_pdf()  # 上传的正是本地文件内容


async def test_mineru_strategy_without_token_fails_loudly(monkeypatch):
    """策略 mineru 且无 token：明确报错（该策略没有兜底）。"""
    monkeypatch.setattr(settings, "pdf_strategy", "mineru")
    get_pdf_parser.cache_clear()
    with pytest.raises(ValueError, match="MINERU_TOKEN"):
        get_pdf_parser()


async def test_mineru_failure_falls_back_to_pypdf(tmp_path, monkeypatch):
    """策略 mineru_then_pypdf：云端解析失败时退到本地文本层。"""
    _use_mineru_transport(monkeypatch, _mineru_transport(state="failed"))
    monkeypatch.setattr(settings, "mineru_token", "sk-mineru")
    get_pdf_parser.cache_clear()

    result = await get_pdf_parser().parse(_pdf_file(tmp_path))

    assert PDF_TEXT in result


async def test_mineru_missing_token_falls_back_to_pypdf(tmp_path):
    """策略 mineru_then_pypdf 且无 token（未接云端）：同样退到本地，全链路不中断。"""
    result = await get_pdf_parser().parse(_pdf_file(tmp_path))
    assert PDF_TEXT in result


async def test_fallback_parser_degrades_on_any_primary_failure(tmp_path):
    """组合策略对任意主策略异常都退备选（不只 mineru）。"""

    class _Boom(PdfParser):
        name = "boom"

        async def parse(self, pdf_path: str) -> str:
            raise RuntimeError("主策略崩了")

    result = await FallbackPdfParser(_Boom(), PypdfParser()).parse(_pdf_file(tmp_path))
    assert PDF_TEXT in result


async def test_knowledge_layer_follows_configured_strategy(tmp_path, monkeypatch):
    """调用方（知识库 PDF 解析器）只依赖接口：换策略只改配置。"""
    monkeypatch.setattr(settings, "pdf_strategy", "pypdf")
    get_pdf_parser.cache_clear()
    assert PDF_TEXT in await KnowledgePdfParser().parse(_pdf_file(tmp_path))

    _use_mineru_transport(monkeypatch, _mineru_transport(state="done"))
    monkeypatch.setattr(settings, "pdf_strategy", "mineru")
    monkeypatch.setattr(settings, "mineru_token", "sk-mineru")
    get_pdf_parser.cache_clear()
    assert await KnowledgePdfParser().parse(_pdf_file(tmp_path)) == MINERU_MARKDOWN


def test_unknown_strategy_lists_available(monkeypatch):
    monkeypatch.setattr(settings, "pdf_strategy", "nowhere")
    get_pdf_parser.cache_clear()
    with pytest.raises(ValueError, match="可选"):
        get_pdf_parser()
