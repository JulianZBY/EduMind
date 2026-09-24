"""DeepSeek provider：OpenAI 兼容对话；无多模态；embed 委托 SiliconFlow（缺失时本地确定性兜底）。

DeepSeek 不提供 embeddings / 多模态 API：
- embed 默认走 SiliconFlow 托管的 bge-large-zh（.env 的 SILICONFLOW_API_KEY）；
  未配置时退化为字符 n-gram 哈希袋向量（可跑通、维度稳定，但语义检索/近名
  冲突预筛质量降级）。
- vision 保持基类 NotImplementedError：图片/视频帧理解需切换 dashscope。
"""

import zlib

import httpx

from app.core.llm.base import ChatMessage, ChatResult, LLMProvider

CHAT_BASE = "https://api.deepseek.com"
SILICONFLOW_BASE = "https://api.siliconflow.cn/v1"


class DeepSeekProvider(LLMProvider):
    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        chat_model: str = "deepseek-chat",
        embed_api_key: str = "",
        embed_base: str = SILICONFLOW_BASE,
        embed_model: str = "BAAI/bge-large-zh-v1.5",
        fallback_dim: int = 64,
    ) -> None:
        self.api_key = api_key
        self.chat_model = chat_model
        self.embed_api_key = embed_api_key
        self.embed_base = embed_base
        self.embed_model = embed_model
        self.fallback_dim = fallback_dim

    def _headers(self, key: str | None = None) -> dict:
        return {
            "Authorization": f"Bearer {key or self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        payload = {
            "model": kwargs.get("model", self.chat_model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{CHAT_BASE}/chat/completions", headers=self._headers(), json=payload
            )
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        return ChatResult(content=content, raw=data)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.embed_api_key:
            payload = {"model": self.embed_model, "input": texts}
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    f"{self.embed_base}/embeddings",
                    headers=self._headers(self.embed_api_key),
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
            return [item["embedding"] for item in data["data"]]
        return [self._fallback_embed(t) for t in texts]

    def _fallback_embed(self, text: str) -> list[float]:
        """本地确定性兜底向量：字符 1/2-gram 的 crc32 哈希袋 + L2 归一化。

        必须跨进程稳定（内置 hash() 带 PYTHONHASHSEED 随机种子，不可用）。
        仅保证可跑通与维度一致；语义质量不做承诺。
        """
        vec = [0.0] * self.fallback_dim
        grams = {text[i : i + 2] for i in range(max(len(text) - 1, 0))} | set(text)
        for g in grams:
            vec[zlib.crc32(g.encode("utf-8")) % self.fallback_dim] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm == 0:  # 空文本：给一个固定非零向量，避免归一化除零
            vec[0] = 1.0
            return vec
        return [v / norm for v in vec]
