"""联网检索并入库（CONTEXT.md 第 4 节词条，票 10）：搜索结果按文献笔记入库（来源=网页）。

教师在会话里手动触发（**不自动联网**）：每条搜索结果建一份网页资料，入库正文由
标题 / URL / 摘要组成——来源信息随分块进库，检索命中可回溯到网页。入库本体走
`pipeline.parse_document` 的文本入口，与上传资料同一条管道：分块 → 知识点提取 → 冲突待审
（ADR-0006：审核前不入图谱）→ 文献笔记；生成器只经检索消费这批知识，不直接拼网页原文。
"""

from sqlalchemy.orm import Session

from app.core.search.factory import get_search
from app.db.models import Document
from app.knowledge.literature_note import SOURCE_WEB

# 网页资料的类型标记（Document.file_type）：不指向任何解析器——正文在检索时已拿到，
# 入库走文本入口，不经过 parse_document 的按类型解析器分发。
FILE_TYPE_WEB = SOURCE_WEB

# 资料列表的标题显示上限；完整标题保留在入库正文中
_FILENAME_LIMIT = 200


def result_text(result: dict) -> str:
    """一条搜索结果的入库正文：标题 / URL / 摘要三行（分块与文献笔记共享同一份文本）。"""
    title = str(result.get("title") or "").strip()
    url = str(result.get("url") or "").strip()
    snippet = str(result.get("snippet") or "").strip()
    return f"标题：{title}\n来源：{url}\n摘要：{snippet}"


async def prepare_web_ingest(db: Session, query: str, count: int) -> list[tuple[Document, str]]:
    """每条搜索结果建一份「处理中」的网页资料，返回 (资料, 入库正文) 列表。

    仅教师手动调用的入口：检索后建行；入库本体（分块 / 知识点 / 冲突 / 文献笔记）由调用方
    把 `pipeline.parse_document` 的文本入口 交后台任务，与上传解析同一推进方式与失败语义。
    不去重：同一结果再次触发会重复入库（教师手动扳机，误入的资料按 ADR-0007 在知识库区管理）。
    """
    results = await get_search().search(query, count=count, summary=True)
    created: list[tuple[Document, str]] = []
    for result in results:
        title = str(result.get("title") or "").strip() or "网页检索结果"
        doc = Document(
            user_id="default",
            filename=title[:_FILENAME_LIMIT],
            file_path="",  # 无本地原件；来源 URL 随正文分块入库，不能作为本地文件删除
            file_type=FILE_TYPE_WEB,
            status="处理中",
        )
        db.add(doc)
        created.append((doc, result_text(result)))
    db.commit()
    return created
