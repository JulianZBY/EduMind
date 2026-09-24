"""教学智能体编排器：意图 → 检索 → 生成。检索细节住在 knowledge/retrieval 的策略里。"""

import asyncio
import logging
from pathlib import Path

from app.core.intent import TeachingIntent, wants_interactive_content
from app.generate.creative import generate_html_creative, save_html
from app.generate.outline import generate_outline
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
    gen_calls = [
        generate_ppt_structure(intent_dict, knowledge),
        generate_word_structure(intent_dict, knowledge),
        generate_outline(intent_dict, knowledge),
    ]
    if wants_interactive_content(intent):
        gen_calls.append(generate_html_creative(knowledge))
    results = await asyncio.gather(*gen_calls, return_exceptions=True)
    ppt_slides, word_data, outline = results[0], results[1], results[2]
    interactive_result = results[3] if len(results) > 3 else None
    # 单个生成失败不拖垮整体，降级为空结果
    slides: list[dict]
    if isinstance(ppt_slides, BaseException):
        logger.warning("PPT 生成失败: %s", ppt_slides)
        slides = []
    else:
        slides = ppt_slides
    # 课件主题化：页面角色差异化版式 + 风格偏好映射配色主题（简约/学术/活泼）在渲染层生效
    ppt_path = render_ppt(slides, style=intent_dict.get("style", ""))

    word: dict
    if isinstance(word_data, BaseException):
        logger.warning("Word 生成失败: %s", word_data)
        word = {}
    else:
        word = word_data
    word_path = render_word(word, references=references)
    if isinstance(outline, BaseException):
        logger.warning("提纲生成失败: %s", outline)
        outline = ""

    # 互动内容：单个生成失败不拖垮整体，降级为不附带；产物统一随机命名落盘
    interactive: dict | None = None
    if interactive_result is not None:
        if isinstance(interactive_result, BaseException):
            logger.warning("互动内容生成失败: %s", interactive_result)
        elif str(interactive_result).strip():
            path = save_html(str(interactive_result))
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
        "outline": outline,
        "interactive": interactive,
    }
