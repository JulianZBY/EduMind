"""票 05 测试替身：语义网关（LLM 能力）与提示词观测助手。

替换的是**外部能力**（LLM 网关），经「能力注册表 + 配置选择」挂上（ADR-0003），
与票 02/03 的接缝口径一致：测试不替换内部函数，只替换能力实现。
夹具（install_semantic_llm / isolated_output_dir）在 `tests/conftest.py`。
"""

import json

from app.core.clarify import SKIP_JUDGEMENT_MARKER
from app.core.intent import MERGE_TEXT_SEPARATOR
from app.core.llm.base import ChatMessage, ChatResult, LLMProvider

TEST_LLM_PROVIDER = "session-test-llm"

# 课件 / 教案 / 提纲三个生成器都能解析的结构（与既有 API 缝测试同一假响应）
GENERATION_STRUCTURE = json.dumps(
    {
        "slides": [{"title": "s", "points": ["p"]}],
        "key_points": ["k"],
        "difficult_points": [],
        "process": [],
        "activities": [],
        "homework": [],
    },
    ensure_ascii=False,
)

INTENT_MARKER = "意图分析模块"
FULL_TEXT_SEPARATOR = "教师需求：\n"
ACCUMULATED_SEPARATOR = "已累积的意图：\n"


class SemanticLLM(LLMProvider):
    """语义网关替身：按提示词标记作答，并把每类提示词分别记账。

    - 意图分析（全量 / 增量）：按 `learned` 里教给它的「教师表述 → 要素」抽取；
      增量提示词从已累积意图起合并、只按本轮表述覆盖（与真网关同一契约）；
    - 跳过追问判定：把注入的语义判定结果（`skip`）回给调用方；
    - 其余（课件 / 教案 / 提纲 / 互动内容）：返回可解析的固定结构。
    """

    name = "semantic-test"

    def __init__(self, *, learned: dict[str, dict] | None = None, skip: bool = False) -> None:
        self.learned = dict(learned or {})
        self.skip = skip
        self.prompts: list[str] = []
        self.intent_prompts: list[str] = []  # 每轮意图分析的提示词（全量或增量）
        self.skip_prompts: list[str] = []  # 每次跳过追问判定的提示词

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        prompt = messages[-1].content
        self.prompts.append(prompt)
        if INTENT_MARKER in prompt:
            self.intent_prompts.append(prompt)
            return ChatResult(content=json.dumps(self._intent(prompt), ensure_ascii=False))
        if SKIP_JUDGEMENT_MARKER in prompt:
            self.skip_prompts.append(prompt)
            return ChatResult(content=json.dumps({"skip": self.skip}, ensure_ascii=False))
        return ChatResult(content=GENERATION_STRUCTURE)

    def _intent(self, prompt: str) -> dict:
        """抽取要素：增量提示词从「已累积的意图」起合并，全量提示词从整段需求起抽取。"""
        if MERGE_TEXT_SEPARATOR in prompt:
            accumulated, _, text = prompt.partition(MERGE_TEXT_SEPARATOR)
            previous = json.loads(accumulated.split(ACCUMULATED_SEPARATOR, 1)[1].strip())
        else:
            previous, text = {}, prompt.partition(FULL_TEXT_SEPARATOR)[2]
        merged = dict(previous)
        for utterance, fields in self.learned.items():
            if utterance in text:  # 最新表述覆盖旧值（与真网关同一口径）
                merged.update(fields)
        return merged


def analyzed_text(prompt: str) -> str:
    """从意图分析提示词里取出这次真正被分析的教师表述（增量提示词里只有本轮原话）。"""
    if MERGE_TEXT_SEPARATOR in prompt:
        return prompt.partition(MERGE_TEXT_SEPARATOR)[2].strip()
    return prompt.partition(FULL_TEXT_SEPARATOR)[2].strip()
