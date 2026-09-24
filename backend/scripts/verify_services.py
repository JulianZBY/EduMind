"""真实验证云端服务（需 .env 配置真实 key）。用法：uv run python scripts/verify_services.py

按配置装配各能力（LLM / 向量化 / 网络搜索 / PDF 解析），因此同时验证配置口径是否正确。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.embedding.factory import get_embedder
from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.parser.factory import get_pdf_parser
from app.core.search.factory import get_search


async def main() -> None:
    llm = get_llm()
    embedder = get_embedder()
    search = get_search()

    print(f"=== 1. chat（LLM_PROVIDER={settings.llm_provider} → {type(llm).__name__}）===")
    r = await llm.chat([ChatMessage(role="user", content="用一句话介绍计算机网络")])
    print(r.content)

    print(f"\n=== 2. embed（{type(embedder).__name__}）===")
    vecs = await embedder.embed(["计算机网络", "操作系统"])
    print(f"向量数={len(vecs)}, 维度={len(vecs[0])}")

    print(f"\n=== 3. search（{type(search).__name__}）===")
    pages = await search.search("计算机网络 教学")
    print(f"结果数={len(pages)}")
    for p in pages[:2]:
        print(f"- {p['title'][:40]} | {p['url'][:50]}")

    print(f"\n=== 4. parse（PDF_STRATEGY={settings.pdf_strategy}）===")
    pdf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test.pdf")
    if os.path.exists(pdf):
        md = await get_pdf_parser().parse(pdf)
        print(md[:500])
    else:
        print(f"跳过：未找到 {pdf}")


asyncio.run(main())
