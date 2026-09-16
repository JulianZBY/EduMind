"""阿里云百炼（DashScope）provider：qwen 对话 + qwen-vl 多模态 + text-embedding。"""

import base64
import mimetypes

import httpx

from app.core.llm.base import ChatMessage, ChatResult, LLMProvider

COMPAT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class DashScopeProvider(LLMProvider):
    name = "dashscope"

    def __init__(
        self,
        api_key: str,
        chat_model: str = "qwen-plus",
        vision_model: str = "qwen-vl-max",
        embed_model: str = "text-embedding-v3",
    ) -> None:
        self.api_key = api_key
        self.chat_model = chat_model
        self.vision_model = vision_model
        self.embed_model = embed_model

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        model = kwargs.get("model", self.chat_model)
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{COMPAT_BASE}/chat/completions", headers=self._headers(), json=payload
            )
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        return ChatResult(content=content, raw=data)

    async def vision(self, image_path: str, prompt: str) -> str:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        mime = mimetypes.guess_type(image_path)[0] or "image/png"
        content = [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]
        payload = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": content}],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{COMPAT_BASE}/chat/completions", headers=self._headers(), json=payload
            )
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.embed_model, "input": texts}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{COMPAT_BASE}/embeddings", headers=self._headers(), json=payload
            )
            r.raise_for_status()
            data = r.json()
        # 兼容模式按 input 顺序返回 data[]
        return [item["embedding"] for item in data["data"]]
