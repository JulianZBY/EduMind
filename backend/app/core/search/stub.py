"""桩搜索：无 Key 可跑，返回标注清楚的占位结果（避免拿假结果当教学依据）。"""

from app.core.search.base import WebSearch

STUB_MARK = "（stub 网络搜索）"
MAX_STUB_RESULTS = 5


class StubSearch(WebSearch):
    name = "stub"

    async def search(self, query: str, count: int = 5, summary: bool = False) -> list[dict]:
        n = max(1, min(count, MAX_STUB_RESULTS))
        return [
            {
                "title": f"{STUB_MARK}{query} 相关结果 {i + 1}",
                "url": f"https://example.com/stub/{i + 1}",
                "snippet": f"{STUB_MARK}未配置搜索服务，本结果为占位内容。",
            }
            for i in range(n)
        ]
