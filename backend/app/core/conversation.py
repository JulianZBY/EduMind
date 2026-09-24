"""备课会话状态机（core 层）：澄清 → 检索 → 生成 → 反馈。

路由层只做参数校验与转发；追问粒度、跳过追问的语义判定、意图累积，以及
澄清回复 / 生成回复两种形态的流转全部住在这里（ADR-0002 状态机收编）。
检索与生成由 `orchestrator` 编排（检索细节住 knowledge/retrieval 的策略里）。
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.core.clarify import build_question, missing_fields, should_skip_clarification
from app.core.intent import TeachingIntent, analyze_intent, merge_intent
from app.core.orchestrator import orchestrate

# 回复形态（CONTEXT.md「澄清回复」/「生成回复」）：两种形态互斥
CLARIFY_REPLY = "澄清回复"
GENERATE_REPLY = "生成回复"

# 教师完全没说主题时的第一句追问（与收编前逐字一致）
TOPIC_QUESTION = "请问你要讲什么课？可以告诉我主题、学段和大致时长。"
# 澄清回复里对「跳过追问」的提示（与收编前逐字一致）
SKIP_HINT = "（也可以回复「开始生成」跳过追问）"


@dataclass(frozen=True)
class TurnOutcome:
    """一轮备课的结果：回复形态 + 回复内容 + 生成物 + 累积意图。

    `clarifying` 直接对应既有 `POST /chat` 响应字段；`reply_kind` 是消息落库时
    记录的回复形态（CONTEXT.md 术语），`intent` 是落库供下一轮增量累积的意图。
    """

    content: str
    clarifying: bool
    artifacts: dict | None = None
    intent: TeachingIntent = field(default_factory=TeachingIntent)

    @property
    def reply_kind(self) -> str:
        """这条回复的形态：澄清回复 / 生成回复（同一条回复只属于一种）。"""
        return CLARIFY_REPLY if self.clarifying else GENERATE_REPLY


async def accumulate_intent(
    previous: TeachingIntent | None, utterance: str
) -> TeachingIntent:
    """按会话累积意图：上一轮意图 + 本轮新增；没有上一轮时才全量分析本轮原话。

    同一会话多轮对话不再每轮把全部历史重析一遍——增量合并只喂「已累积意图 +
    本轮表述」，矛盾时以本轮表述为准。
    """
    if previous is None or previous == TeachingIntent():
        return await analyze_intent(utterance)
    return await merge_intent(previous, utterance)


def _generate_reply(topic: str, result: dict) -> str:
    """生成回复的文案（反馈）：说清产出了什么、知识库是否命中、命中了哪些参考资料。"""
    n_slides = len(result["ppt"]["slides"])
    kb_note = "已融合本地知识库" if result["knowledge_hits"] else "知识库为空，已由 AI 直接生成"
    content = f"已完成备课「{topic}」：生成 PPT {n_slides} 页、Word 教案、教学提纲。（{kb_note}）"
    references = result.get("references") or []
    if references:
        content += f" 本次命中的来源文档：{'、'.join(references)}。"
    if result.get("interactive"):
        content += " 已按你的互动诉求自动生成互动内容（HTML），可在生成物区打开。"
    return content


async def run_turn(
    utterance: str,
    *,
    intent: TeachingIntent,
    granularity: str,
    reference_doc_ids: list[str] | None = None,
) -> TurnOutcome:
    """跑一轮备课：澄清（追问粒度 + 跳过追问语义判定）→ 检索 → 生成 → 反馈。

    `utterance` 是教师本轮原话（跳过追问的语义判定只看本轮表述）；
    `intent` 是本轮生效的累积意图（由调用方按会话累积或全量分析得到）。
    """
    # 1. 澄清：连主题都没有时先问主题
    if not intent.topic:
        return TurnOutcome(
            content=TOPIC_QUESTION, clarifying=True, artifacts=None, intent=intent
        )

    # 2. 澄清：按追问粒度看还缺哪些要素；教师表示「信息够了」则跳过追问
    missing = missing_fields(intent, granularity)
    if missing and not await should_skip_clarification(utterance, missing):
        return TurnOutcome(
            content=f"还差一点信息：{build_question(missing)}{SKIP_HINT}",
            clarifying=True,
            artifacts=None,
            intent=intent,
        )

    # 3. 检索 + 生成：携带参考资料标识（检索加权 + 溯源）
    result = await orchestrate(intent, reference_doc_ids=reference_doc_ids)
    topic = result["intent"].get("topic", "")
    # 4. 反馈：回复文案 + 产物文件名回显（供前端直接下载/预览）
    content = _generate_reply(topic, result)
    result["ppt"]["filename"] = Path(result["ppt"]["path"]).name
    result["word"]["filename"] = Path(result["word"]["path"]).name
    return TurnOutcome(content=content, clarifying=False, artifacts=result, intent=intent)
