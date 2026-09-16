"""真实验证云端服务（需 .env 配置真实 key）。用法：uv run python scripts/verify_services.py"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.llm.base import ChatMessage
from app.core.llm.providers.dashscope import DashScopeProvider
from app.core.parser.mineru import MinerUParser
from app.core.search.bocha import BochaSearchClient


async def main() -> None:
    llm = DashScopeProvider(settings.dashscope_api_key)

    print("=== 1. chat (qwen-plus) ===")
    r = await llm.chat([ChatMessage(role="user", content="用一句话介绍计算机网络")])
    print(r.content)

    print("\n=== 2. embed (text-embedding-v3) ===")
    vecs = await llm.embed(["计算机网络", "操作系统"])
    print(f"向量数={len(vecs)}, 维度={len(vecs[0])}")

    print("\n=== 3. search (博查) ===")
    pages = await BochaSearchClient().search("计算机网络 教学")
    print(f"结果数={len(pages)}")
    for p in pages[:2]:
        print(f"- {p['title'][:40]} | {p['url'][:50]}")

    print("\n=== 4. parse (MinerU) ===")
    pdf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test.pdf")
    if os.path.exists(pdf):
        md = await MinerUParser().parse(pdf)
        print(md[:500])
    else:
        print(f"跳过：未找到 {pdf}")


asyncio.run(main())
