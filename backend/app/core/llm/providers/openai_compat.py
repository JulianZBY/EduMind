"""OpenAI 兼容 provider：base_url + model + api_key 三个构造参数即可接任何方言。

dashscope / deepseek / 硅基流动的差异（地址、模型名、是否支持多模态）全部落在
`app.core.dialects` 预设与配置里，实现只有这一份。
"""

import base64
import mimetypes

import httpx

from app.core.llm.base import ChatMessage, ChatResult, LLMProvider

DEFAULT_TIMEOUT = 120.0


def content_of(data: dict) -> str:
    """取 choices[0].message.content；部分方言返回 parts 数组，按文本部分拼接。"""
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return content or ""


def data_uri(image_path: str) -> str:
    """本地图片转 data URI；读不到文件时给出可读错误（vision 的唯一失败入口）。"""
    try:
        with open(image_path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise FileNotFoundError(f"图片不可读: {image_path}") from e
    mime = mimetypes.guess_type(image_path)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


class OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容对话 / 多模态 provider。"""

    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        vision_model: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.vision_model = vision_model
        self.timeout = timeout
        # 测试注入点（httpx.MockTransport）；生产恒为 None
        self._transport = transport

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self._transport)

    async def _post(self, path: str, payload: dict) -> dict:
        async with self._client() as client:
            r = await client.post(f"{self.base_url}{path}", headers=self._headers(), json=payload)
            r.raise_for_status()
            return r.json()

    @staticmethod
    def _text_payload(model: str, messages: list[ChatMessage]) -> dict:
        return {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        payload = self._text_payload(kwargs.get("model") or self.model, messages)
        data = await self._post("/chat/completions", payload)
        return ChatResult(content=content_of(data), raw=data)

    async def vision(self, image_path: str, prompt: str) -> str:
        if not self.vision_model:
            raise NotImplementedError(f"{self.name} 方言未配置多模态模型")
        content = [
            {"type": "image_url", "image_url": {"url": data_uri(image_path)}},
            {"type": "text", "text": prompt},
        ]
        payload = {"model": self.vision_model, "messages": [{"role": "user", "content": content}]}
        data = await self._post("/chat/completions", payload)
        return content_of(data)
