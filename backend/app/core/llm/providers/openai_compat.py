"""OpenAI 兼容 provider：base_url + model + api_key 三个构造参数即可接任何方言。

千问 / DeepSeek / 硅基流动的差异（地址、模型名、是否支持多模态）全部落在
`app.core.dialects` 预设与配置里，实现只有这一份。
"""

import base64
import mimetypes

import httpx

from app.core.errors import ProviderNotConfigured, ProviderRequestFailed
from app.core.http import tls_context
from app.core.llm.base import ChatMessage, ChatResult, LLMProvider
from app.core.llm.model_capabilities import require_capability

DEFAULT_TIMEOUT = 120.0


def content_of(data: dict) -> str:
    """取 choices[0].message.content；部分方言返回 parts 数组，按文本部分拼接。"""
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if content is not None and not isinstance(content, str):
        raise TypeError("message.content must be text")
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
        model_capabilities: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.vision_model = vision_model
        self.timeout = timeout
        # 测试注入点（httpx.MockTransport）；生产恒为 None
        self._transport = transport
        self.model_capabilities = model_capabilities or {}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout, transport=self._transport, verify=tls_context()
        )

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            async with self._client() as client:
                r = await client.post(
                    f"{self.base_url}{path}", headers=self._headers(), json=payload
                )
                r.raise_for_status()
                data = r.json()
                # 供应商返回 200 也可能没有正常对话结构，不能当作有效生成。
                if not isinstance(data, dict) or not data.get("choices"):
                    raise ValueError("missing choices")
                content_of(data)
                return data
        except httpx.TimeoutException as exc:
            raise ProviderRequestFailed("模型服务响应超时，请稍后重试。", status_code=504) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                message = "模型服务拒绝访问，请到设置页检查 Key 与模型权限。"
            elif status == 429:
                message = "模型服务额度不足或请求过于频繁，请检查余额或稍后重试。"
            elif status in (400, 404, 422):
                message = "模型服务不接受当前请求，请到设置页检查服务地址、模型与能力配置。"
            else:
                message = "模型服务暂时不可用，请稍后重试。"
            raise ProviderRequestFailed(message) from exc
        except httpx.RequestError as exc:
            raise ProviderRequestFailed(
                "无法连接模型服务，请检查网络、代理与证书配置后重试。"
            ) from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestFailed("模型服务返回的内容无法读取，请稍后重试。") from exc

    @staticmethod
    def _text_payload(model: str, messages: list[ChatMessage]) -> dict:
        return {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        model = kwargs.get("model") or self.model
        self._check_capability(model, "text")
        payload = self._text_payload(model, messages)
        data = await self._post("/chat/completions", payload)
        return ChatResult(content=content_of(data), raw=data)

    async def vision(self, image_path: str, prompt: str) -> str:
        if not self.vision_model:
            raise ProviderNotConfigured("多模态模型未配置：请到设置页配置支持视觉的模型。")
        self._check_capability(self.vision_model, "vision")
        content = [
            {"type": "image_url", "image_url": {"url": data_uri(image_path)}},
            {"type": "text", "text": prompt},
        ]
        payload = {"model": self.vision_model, "messages": [{"role": "user", "content": content}]}
        data = await self._post("/chat/completions", payload)
        return content_of(data)

    def _check_capability(self, model: str, capability: str) -> None:
        known = self.model_capabilities.get(model)
        # unknown 模型支持既有手动配置；已标注模型则禁止走不支持的接口。
        require_capability(model, capability, known or ())
