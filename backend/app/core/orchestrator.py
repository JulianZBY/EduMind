"""教学智能体编排器：意图 → 检索 → 生成。检索细节住在 knowledge/retrieval 的策略里。"""

import asyncio
import logging
from pathlib import Path

from app.core.errors import GenerationFailed, ProviderNotConfigured
from app.core.intent import TeachingIntent, wants_interactive_content
from app.generate.creative import generate_html_creative, save_html
from app.generate.outline import generate_outline, render_outline
from app.generate.ppt import generate_ppt_structure, render_ppt
from app.generate.word import generate_word_structure, render_word
from app.knowledge.retrieval.factory import get_retriever

logger = logging.getLogger(__name__)


async def orchestrate(intent: TeachingIntent, reference_doc_ids: list[str] | None = None) -> dict:
    """一次备课的编排：检索（按配置的检索策略）→ 生成 PPT/Word/提纲 + 互动内容。

    意图由调用方（core 状态机：按会话累积或全量分析）传入：本轮不再重析一次意图，
    一次生成只花一次意图分析调用。
    """
    intent_dict = intent.model_dump()
    retrieval = await get_retriever().retrieve(intent, reference_doc_ids=reference_doc_ids)
    knowledge = retrieval.context
    # 溯源：回复文案、教案「参考资料」节共用同一份来源信息；未携带参考资料标识时保持现状
    references = retrieval.sources if reference_doc_ids else []

    # 互动诉求命中（小游戏/动画）时，备课流程自动附带生成互动内容（单文件 HTML）
    wants_interactive = wants_interactive_content(intent)
    gen_calls = [
        generate_ppt_structure(intent_dict, knowledge),
        generate_word_structure(intent_dict, knowledge),
        generate_outline(intent_dict, knowledge),
    ]
    if wants_interactive:
        gen_calls.append(generate_html_creative(knowledge))
    results = await asyncio.gather(*gen_calls, return_exceptions=True)
    ppt_slides, word_data, outline = results[0], results[1], results[2]
    interactive_result = results[3] if wants_interactive else None

    # 核心生成物（课件 / 教案 / 提纲）任一路失败，本轮备课就是不完整的：显式失败并可重试，
    # 绝不落一份空课件 / 空教案冒充成功（产品不返回「看起来像真结果的占位内容」）。
    core_failures = [
        (label, result)
        for label, result in zip(("课件", "教案", "提纲"), results[:3], strict=True)
        if isinstance(result, BaseException)
    ]
    if core_failures:
        for label, exc in core_failures:
            logger.error("生成失败 %s: %s", label, exc, exc_info=exc)
        for _, exc in core_failures:
            if isinstance(exc, ProviderNotConfigured):
                raise exc  # 未配置保持 503 语义：交全局处理器给设置页引导，不算生成故障
        failed = "、".join(label for label, _ in core_failures)
        raise GenerationFailed(
            f"{failed}生成失败，本轮备课未完成。请稍后重试；若持续失败，"
            "请到「设置」页检查对话模型的配置。"
        )

    slides: list[dict] = ppt_slides
    # 课件主题化：页面角色差异化版式 + 风格偏好映射配色主题（简约/学术/活泼）在渲染层生效
    # render_* 是同步的 python-pptx/docx 渲染 + 落盘：放线程池，不阻塞事件循环（M1）
    ppt_path = await asyncio.to_thread(render_ppt, slides, style=intent_dict.get("style", ""))

    word: dict = word_data
    word_path = await asyncio.to_thread(render_word, word, references=references)
    # 提纲与课件 / 教案同形：正文 + 落盘文件（版本记录与落盘文件一一对应）
    outline_text = str(outline or "")
    outline_artifact: dict | None = None
    if outline_text.strip():
        outline_path = await asyncio.to_thread(render_outline, outline_text)
        outline_artifact = {
            "text": outline_text,
            "path": outline_path,
            "filename": Path(outline_path).name,
        }

    # 互动内容是可选附加项：生成失败不拖垮备课，但在回复里如实告知教师（不静默丢弃）；
    # 产物统一随机命名落盘
    interactive_failed = wants_interactive and isinstance(interactive_result, BaseException)
    if interactive_failed:
        logger.warning("互动内容生成失败: %s", interactive_result)
    interactive: dict | None = None
    if (
        interactive_result is not None
        and not isinstance(interactive_result, BaseException)
        and str(interactive_result).strip()
    ):
        path = await asyncio.to_thread(save_html, str(interactive_result))
        interactive = {
            "html": str(interactive_result),
            "path": path,
            "filename": Path(path).name,
        }

    return {
        "intent": intent_dict,
        "knowledge_hits": bool(knowledge),
        "references": references,
        "ppt": {"slides": slides, "path": ppt_path},
        # data：教案完整结构随产物下发，供预览面板发起教案修改（与 slides 同理）
        "word": {"data": word, "path": word_path},
        "outline": outline_artifact,
        "interactive": interactive,
        # 互动内容是否「想要但没生成出来」：回复文案据此如实告知，不静默吞掉
        "interactive_failed": interactive_failed,
    }
