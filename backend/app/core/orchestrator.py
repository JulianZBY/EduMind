"""教学智能体编排器：意图 → 检索 → 生成。检索细节住在 knowledge/retrieval 的策略里。"""

import asyncio
import logging
from pathlib import Path

from app.core.errors import GenerationFailed
from app.core.intent import TeachingIntent, wants_interactive_content
from app.generate.creative import generate_html_creative, is_single_file_html, save_html
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
    gen_calls = [
        generate_ppt_structure(intent_dict, knowledge),
        generate_word_structure(intent_dict, knowledge),
        generate_outline(intent_dict, knowledge),
    ]
    if wants_interactive_content(intent):
        # 空知识库仍须有教学主题与要求，不能让互动生成收到空提示。
        gen_calls.append(
            generate_html_creative(f"教学意图：{intent.model_dump_json()}\n知识内容：{knowledge}")
        )
    results = await asyncio.gather(*gen_calls, return_exceptions=True)
    ppt_slides, word_data, outline = results[0], results[1], results[2]
    interactive_result = results[3] if len(results) > 3 else None
    # 必需生成全部检查后才落盘：配置/连接错误保持原类型，不伪造空文件或成功回复。
    for value in results[:3]:
        if isinstance(value, BaseException):
            raise value
    if (
        not isinstance(ppt_slides, list)
        or not ppt_slides
        or not all(
            isinstance(slide, dict)
            and isinstance(slide.get("title"), str)
            and slide["title"].strip()
            for slide in ppt_slides
        )
    ):
        raise GenerationFailed("课件生成失败：模型未返回可用页面，请重试。")
    if not isinstance(word_data, dict) or not any(
        word_data.get(key)
        for key in ("objectives", "process", "activities", "homework", "key_points")
    ):
        raise GenerationFailed("教案生成失败：模型未返回可用内容，请重试。")
    if not isinstance(outline, str) or not outline.strip():
        raise GenerationFailed("提纲生成失败：模型未返回可用正文，请重试。")
    slides = ppt_slides
    # 课件主题化：页面角色差异化版式 + 风格偏好映射配色主题（简约/学术/活泼）在渲染层生效
    ppt_path = render_ppt(slides, style=intent_dict.get("style", ""))

    word = word_data
    word_path = render_word(word, references=references)
    # 提纲与课件 / 教案同形：正文 + 落盘文件（版本记录与落盘文件一一对应）
    outline_text = outline
    outline_artifact: dict | None = None
    if outline_text.strip():
        outline_path = render_outline(outline_text)
        outline_artifact = {
            "text": outline_text,
            "path": outline_path,
            "filename": Path(outline_path).name,
        }

    # 互动内容：单个生成失败不拖垮整体，降级为不附带；产物统一随机命名落盘
    interactive: dict | None = None
    warnings: list[str] = []
    if interactive_result is not None:
        if isinstance(interactive_result, BaseException):
            logger.warning("互动内容生成失败: %s", interactive_result)
            warnings.append("互动内容生成失败，请在生成物区重试。")
        elif isinstance(interactive_result, str) and is_single_file_html(interactive_result):
            path = save_html(str(interactive_result))
            interactive = {
                "html": str(interactive_result),
                "path": path,
                "filename": Path(path).name,
            }
        else:
            warnings.append("互动内容生成失败：模型未返回完整网页，请在生成物区重试。")

    return {
        "intent": intent_dict,
        "knowledge_hits": bool(knowledge),
        "references": references,
        "ppt": {"slides": slides, "path": ppt_path},
        # data：教案完整结构随产物下发，供预览面板发起教案修改（与 slides 同理）
        "word": {"data": word, "path": word_path},
        "outline": outline_artifact,
        "interactive": interactive,
        "warnings": warnings,
    }
