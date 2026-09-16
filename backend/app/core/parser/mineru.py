"""MinerU 云端 PDF 解析（主路径）。

流程：file-urls/batch 获取上传地址 → PUT 上传 → 自动提交 → 轮询 extract-results/batch/{id} → 下载 zip 读 Markdown。
"""

import asyncio
import io
import os
import zipfile

import httpx

from app.config import settings


class MinerUParser:
    BASE = "https://mineru.net/api/v4"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or settings.mineru_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def parse(
        self, pdf_path: str, poll_interval: float = 3.0, timeout: float = 300.0
    ) -> str:
        if not self.token:
            raise ValueError("MINERU_TOKEN 未配置")
        filename = os.path.basename(pdf_path)
        async with httpx.AsyncClient(timeout=120) as client:
            # 1. 获取上传地址
            r1 = await client.post(
                f"{self.BASE}/file-urls/batch",
                headers=self._headers(),
                json={"files": [{"name": filename, "is_ocr": False}], "enable_formula": True},
            )
            r1.raise_for_status()
            d1 = r1.json()["data"]
            batch_id = d1["batch_id"]
            upload_url = d1["file_urls"][0]

            # 2. PUT 上传
            with open(pdf_path, "rb") as f:
                r2 = await client.put(upload_url, content=f.read())
            r2.raise_for_status()

            # 3. 轮询结果
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while True:
                r3 = await client.get(
                    f"{self.BASE}/extract-results/batch/{batch_id}", headers=self._headers()
                )
                r3.raise_for_status()
                results = r3.json().get("data", {}).get("extract_result") or []
                if results:
                    first = results[0]
                    state = first.get("state", "")
                    if state == "done":
                        zip_url = first.get("full_zip_url")
                        if not zip_url:
                            raise RuntimeError("MinerU 返回 done 但缺少 full_zip_url")
                        r4 = await client.get(zip_url)
                        r4.raise_for_status()
                        return self._extract_markdown(r4.content)
                    if state == "failed":
                        raise RuntimeError(f"MinerU 解析失败: {first.get('err_msg') or first}")
                if loop.time() > deadline:
                    raise TimeoutError("MinerU 解析超时")
                await asyncio.sleep(poll_interval)

    @staticmethod
    def _extract_markdown(zip_bytes: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            md_names = [n for n in z.namelist() if n.endswith(".md")]
            if not md_names:
                raise RuntimeError("MinerU 结果 zip 中无 .md 文件")
            md_names.sort(key=len)  # 最短的通常是主文档
            return z.read(md_names[0]).decode("utf-8")
