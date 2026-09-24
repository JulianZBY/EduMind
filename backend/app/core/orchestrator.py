"""教学智能体编排器：对话 → 意图 → 检索 → 生成。"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

from app.core.intent import TeachingIntent, analyze_intent, wants_interactive_content
from app.generate.creative import generate_html_creative, save_html
from app.generate.outline import generate_outline
from app.generate.ppt import generate_ppt_structure, render_ppt
from app.generate.word import generate_word_structure, render_word

logger = logging.getLogger(__name__)

# 生成上下文总预算（字符）：命中片段优先，图谱节点内容在剩余空间内截断。
# 与生成 prompt 的知识窗口（knowledge[:6000]）对齐，保证图谱段不被下游二次截断。
CONTEXT_BUDGET_CHARS = 6000
_CHUNKS_HEADER = "=== 知识片段 ===\n"
_NODES_HEADER = "=== 图谱关联知识点（按知识递进） ===\n"


class RetrievalResult(NamedTuple):
    """检索结果：拼好的生成上下文 + 按排名去重的命中来源文档名（溯源共用）。"""

    context: str
    sources: list[str]


async def retrieve_knowledge(
    intent: TeachingIntent, top_k: int = 5, reference_doc_ids: list[str] | None = None
) -> RetrievalResult:
    """RAG 语义检索（参考资料加权）+ 图谱邻接子图融合。向量库为空或检索失败时降级为空。"""
    query = " ".join([intent.topic, *intent.knowledge_points]).strip()
    if not query:
        return RetrievalResult(context="", sources=[])
    try:
        from app.core.embedding.factory import get_embedder
        from app.knowledge.vector_store import VectorStore

        emb = await get_embedder().embed([query])
        hits = VectorStore().search(emb[0], k=top_k, boost_doc_ids=reference_doc_ids or None)
        chunks = [h["content"] for h in hits if h.get("content")]
        sources = _source_names([h["doc_id"] for h in hits])
    except Exception:
        logger.warning("知识检索失败，降级为空上下文", exc_info=True)
        return RetrievalResult(context="", sources=[])
    try:
        context = _fused_context(chunks, [h["doc_id"] for h in hits])
    except Exception:
        logger.warning("图谱邻接子图拉取失败，降级为仅片段上下文", exc_info=True)
        context = "\n\n".join(chunks)
    return RetrievalResult(context=context, sources=sources)


def _source_names(doc_ids: list[str]) -> list[str]:
    """命中 doc_id 按排名映射为文档名（去重）；文档已删除时回退为 doc_id。"""
    names: dict[str, str] = {}
    try:
        from app.db import SessionLocal
        from app.db.models import Document

        db = SessionLocal()
        try:
            rows = db.query(Document).filter(Document.id.in_(doc_ids)).all()
            names = {d.id: d.filename for d in rows}
        finally:
            db.close()
    except Exception:
        logger.warning("来源文档名查询失败，回退为 doc_id", exc_info=True)
    ordered: list[str] = []
    for doc_id in doc_ids:
        name = names.get(doc_id, doc_id)
        if name not in ordered:
            ordered.append(name)
    return ordered


def _fused_context(chunks: list[str], doc_ids: list[str]) -> str:
    """命中片段经来源文档定位知识点，沿图谱边拉取邻接子图，拼入同一上下文。"""
    from app.knowledge.graph import neighborhood, nodes_for_docs

    seed_ids = [n["id"] for n in nodes_for_docs(doc_ids)]
    adjacent = neighborhood(seed_ids)
    return _assemble_context(chunks, adjacent)


def _assemble_context(
    chunks: list[str], nodes: list[dict], budget: int = CONTEXT_BUDGET_CHARS
) -> str:
    """预算内组装：命中片段优先完整保留，图谱节点内容按剩余空间截断。"""
    parts: list[str] = []
    used = 0

    chunk_block = "\n\n".join(c for c in chunks if c)
    if chunk_block:
        piece = (_CHUNKS_HEADER + chunk_block)[: budget - used]
        if piece:
            parts.append(piece)
            used += len(piece)

    if nodes and used < budget:
        # 预留段头与分段符（"\n\n".join），避免拼接后总量超出预算
        room = budget - used - len(_NODES_HEADER) - (2 if parts else 0)
        lines: list[str] = []
        used_lines = 0
        for n in nodes:
            sep = 2 if lines else 0
            line_room = room - used_lines - sep
            if line_room <= 0:
                break
            line = f"【{n['title']}】{n.get('content') or ''}"[:line_room]
            lines.append(line)
            used_lines += sep + len(line)
        if lines:
            parts.append(_NODES_HEADER + "\n\n".join(lines))
    return "\n\n".join(parts)


async def orchestrate(message: str, reference_doc_ids: list[str] | None = None) -> dict:
    """一次备课请求的完整编排：意图 → 检索（参考资料加权）→ 生成 PPT/Word/提纲。"""
    intent = await analyze_intent(message)
    intent_dict = intent.model_dump()
    retrieval = await retrieve_knowledge(intent, reference_doc_ids=reference_doc_ids)
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
