"""OpenAI 兼容 embedding：base_url + model + api_key 即可接任何 /embeddings 服务商。"""

import httpx

from app.core.embedding.base import Embedder

DEFAULT_TIMEOUT = 120.0

# 单次 /embeddings 请求的 input 条数上限：千问 MaaS 实测 11 条即 400
# （服务端原文 "batch size ... should not be larger than 10"），取 10 对其他
# OpenAI 兼容家也安全（它们的上限普遍 ≥10，多拆只会多几个请求不会错）。
EMBED_BATCH_MAX = 10


class OpenAICompatEmbedder(Embedder):
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        dimensions: int = 0,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        # >0 时随请求发送（千问 text-embedding-v3 支持 1024/768/512）
        self.dimensions = dimensions
        self.timeout = timeout
        # 测试注入点（httpx.MockTransport）；生产恒为 None
        self._transport = transport

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            # 分批串行：大文档几百块不能一批发（服务商单请求 input 上限），串行避免限速
            for start in range(0, len(texts), EMBED_BATCH_MAX):
                batch = texts[start : start + EMBED_BATCH_MAX]
                payload: dict = {"model": self.model, "input": list(batch)}
                if self.dimensions:
                    payload["dimensions"] = self.dimensions
                r = await client.post(f"{self.base_url}/embeddings", headers=headers, json=payload)
                r.raise_for_status()
                vectors.extend(self._vectors(r.json(), len(batch)))
        return vectors

    @staticmethod
    def _vectors(data: dict, expected: int) -> list[list[float]]:
        """按 index 还原顺序（兼容响应可能乱序），并校验条数与输入一致。"""
        items = data.get("data") or []
        if items and all("index" in item for item in items):
            items = sorted(items, key=lambda item: item["index"])
        vectors = [item["embedding"] for item in items]
        if len(vectors) != expected:
            raise RuntimeError(f"embedding 响应条数不符：期望 {expected}，得到 {len(vectors)}")
        return vectors
