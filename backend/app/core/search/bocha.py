"""博查网络搜索。"""

import httpx

from app.config import settings


class BochaSearchClient:
    URL = "https://api.bochaai.com/v1/web-search"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.bocha_api_key

    async def search(
        self, query: str, count: int = 5, summary: bool = False
    ) -> list[dict]:
        if not self.api_key:
            raise ValueError("BOCHA_API_KEY 未配置")
        payload = {
            "query": query,
            "count": count,
            "summary": summary,
            "freshness": "noLimit",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                self.URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        pages = data.get("data", {}).get("webPages", {}).get("value", [])
        return [
            {"title": p.get("name", ""), "url": p.get("url", ""), "snippet": p.get("snippet", "")}
            for p in pages
        ]
