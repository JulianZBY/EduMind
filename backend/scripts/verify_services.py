"""真实验证已配置服务（设置库优先于 .env）。用法：uv run python scripts/verify_services.py

按配置装配各能力（LLM / 向量化 / 网络搜索 / PDF 解析），因此同时验证配置口径是否正确。
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.embedding.factory import get_embedder
from app.core.errors import ProviderNotConfigured
from app.core.llm.base import ChatMessage
from app.core.llm.factory import get_llm
from app.core.parser.factory import get_pdf_parser
from app.core.search.factory import get_search
from app.core.settings_store import apply_stored_settings, ensure_bootstrap_provider_instance
from app.db import init_db


async def check_chat() -> None:
    llm = get_llm()
    print(f"chat：{type(llm).__name__}，模型={getattr(llm, 'model', '')}")
    r = await llm.chat([ChatMessage(role="user", content="用一句话介绍计算机网络")])
    print(r.content)


async def check_embed() -> None:
    embedder = get_embedder()
    print(f"embed：{type(embedder).__name__}（本地 hash 不代表云端语义能力通过）")
    vecs = await embedder.embed(["计算机网络", "操作系统"])
    print(f"向量数={len(vecs)}, 维度={len(vecs[0])}")


async def check_search() -> None:
    search = get_search()
    print(f"search：{type(search).__name__}")
    pages = await search.search("计算机网络 教学")
    print(f"结果数={len(pages)}")
    for p in pages[:2]:
        print(f"- {p['title'][:40]} | {p['url'][:50]}")


async def check_parse() -> None:
    print(f"parse：PDF_STRATEGY={settings.pdf_strategy}")
    pdf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test.pdf")
    if os.path.exists(pdf):
        md = await get_pdf_parser().parse(pdf)
        print(md[:500])
    else:
        raise FileNotFoundError("backend/test.pdf 未找到，未测试 PDF 解析")


async def run_check(name, check) -> bool | None:
    """独立检查；未配置 / 无样本是跳过，真实服务失败不伪装成通过。"""
    try:
        await check()
    except (ProviderNotConfigured, FileNotFoundError) as exc:
        print(f"SKIP {name}：{exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - 验证脚本逐项记录失败，继续检查其余已配置能力
        # 第三方异常可能含响应体 / URL；不把原始详情带进公开验证输出。
        print(f"FAIL {name}：{type(exc).__name__}")
        return False
    print(f"PASS {name}")
    return True


async def main(only=None) -> int:
    init_db()
    apply_stored_settings()
    ensure_bootstrap_provider_instance()
    checks = {
        "chat": check_chat,
        "embed": check_embed,
        "search": check_search,
        "parse": check_parse,
    }
    results = []
    for name in only or checks:
        results.append(await run_check(name, checks[name]))
    print(f"通过={results.count(True)}，失败={results.count(False)}，跳过={results.count(None)}")
    return 1 if False in results else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", choices=["chat", "embed", "search", "parse"])
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.only)))
