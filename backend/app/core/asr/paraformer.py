"""阿里百炼（DashScope）paraformer 录音文件识别 provider（真实云端主路径）。

流程（百炼 RESTful API）：
1. GET /api/v1/uploads?action=getPolicy&model=paraformer-v2 获取临时上传凭证；
2. 表单直传 OSS（凭证字段在前，file 字段必须最后）；
3. POST /services/audio/asr/transcription 创建异步转写任务——file_urls 用
   oss:// 临时地址，须带 X-DashScope-Async: enable 与 X-DashScope-OssResourceResolve: enable；
4. GET /tasks/{task_id} 轮询至 SUCCEEDED，取 results[0].transcription_url
   （任务整体 SUCCEEDED 但子任务失败时该结果无 transcription_url 而带 code/message）；
5. 下载签名转写 JSON，拼接 transcripts[].text 为文字稿。
"""

import asyncio
import mimetypes
import os
from pathlib import Path

import httpx

from app.core.asr.base import Transcriber


def _raise_api_error(r: httpx.Response, action: str) -> None:
    """非 2xx 或响应体带 code/message 时抛 RuntimeError（带响应片段便于排查）。"""
    if r.status_code >= 400:
        raise RuntimeError(f"{action}: HTTP {r.status_code} {r.text[:200]}")


class ParaformerTranscriber(Transcriber):
    name = "paraformer"
    BASE = "https://dashscope.aliyuncs.com/api/v1"
    MODEL = "paraformer-v2"

    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = api_key
        self._transport = transport  # 测试注入 MockTransport；生产为 None（直连）

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}"}
        if extra:
            h.update(extra)
        return h

    async def transcribe(
        self, file_path: str, poll_interval: float = 3.0, timeout: float = 600.0
    ) -> str:
        if not self.api_key:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        async with httpx.AsyncClient(timeout=120, transport=self._transport) as client:
            file_url = await self._upload_oss(client, file_path)
            task_id = await self._create_task(client, file_url)
            transcription_url = await self._wait_result(client, task_id, poll_interval, timeout)
            return await self._fetch_transcript(client, transcription_url)

    async def _upload_oss(self, client: httpx.AsyncClient, file_path: str) -> str:
        """获取上传凭证并直传 OSS，返回 oss:// 临时地址（48h 有效）。"""
        r = await client.get(
            f"{self.BASE}/uploads",
            params={"action": "getPolicy", "model": self.MODEL},
            headers=self._headers({"Content-Type": "application/json"}),
        )
        _raise_api_error(r, "获取上传凭证失败")
        d = (r.json().get("data") or {}) if r.status_code < 400 else {}
        if not d.get("upload_host"):
            raise RuntimeError(f"获取上传凭证失败: {r.text[:200]}")
        filename = os.path.basename(file_path)
        key = f"{d['upload_dir']}/{filename}"
        try:
            content = Path(file_path).read_bytes()
        except OSError as e:
            raise RuntimeError(f"无法读取音频文件: {file_path}") from e
        r2 = await client.post(
            d["upload_host"],
            # 官方约定：file 必须为最后一个表单域（httpx 按 data → files 顺序编码）
            data={
                "OSSAccessKeyId": d["oss_access_key_id"],
                "Signature": d["signature"],
                "policy": d["policy"],
                "key": key,
                "x-oss-object-acl": d["x_oss_object_acl"],
                "x-oss-forbid-overwrite": d["x_oss_forbid_overwrite"],
                "success_action_status": "200",
                "x-oss-content-type": mimetypes.guess_type(file_path)[0]
                or "application/octet-stream",
            },
            files={"file": (filename, content)},
        )
        r2.raise_for_status()
        return f"oss://{key}"

    async def _create_task(self, client: httpx.AsyncClient, file_url: str) -> str:
        r = await client.post(
            f"{self.BASE}/services/audio/asr/transcription",
            headers=self._headers(
                {
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",  # 缺失则任务无法提交
                    "X-DashScope-OssResourceResolve": "enable",  # oss:// 临时地址解析
                }
            ),
            json={
                "model": self.MODEL,
                "input": {"file_urls": [file_url]},
                "parameters": {"language_hints": ["zh", "en"]},
            },
        )
        _raise_api_error(r, "创建转写任务失败")
        task_id = (r.json().get("output") or {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"转写任务创建失败: {r.text[:200]}")
        return task_id

    async def _wait_result(
        self, client: httpx.AsyncClient, task_id: str, poll_interval: float, timeout: float
    ) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            r = await client.get(f"{self.BASE}/tasks/{task_id}", headers=self._headers())
            _raise_api_error(r, "查询转写任务失败")
            output = r.json().get("output") or {}
            status = output.get("task_status", "")
            if status == "SUCCEEDED":
                results = output.get("results") or []
                if not results:
                    raise RuntimeError("转写任务成功但无结果")
                first = results[0]
                if first.get("subtask_status") == "FAILED" or not first.get("transcription_url"):
                    raise RuntimeError(
                        f"录音转写失败: {first.get('message') or first.get('code') or first}"
                    )
                return first["transcription_url"]
            if status not in ("PENDING", "RUNNING"):
                raise RuntimeError(f"转写任务异常终止: {output.get('message') or status}")
            if loop.time() > deadline:
                raise TimeoutError("转写任务轮询超时")
            await asyncio.sleep(poll_interval)

    async def _fetch_transcript(self, client: httpx.AsyncClient, url: str) -> str:
        r = await client.get(url)  # 24h 签名公开地址，无需鉴权头
        r.raise_for_status()
        texts = [(t.get("text") or "").strip() for t in r.json().get("transcripts") or []]
        text = "\n".join(t for t in texts if t)
        if not text:
            raise RuntimeError("转写结果为空文本")
        return text
