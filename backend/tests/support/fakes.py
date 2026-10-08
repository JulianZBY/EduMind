"""测试替身：只在 tests/ 里存在的假实现（产品里没有假数据）。

四个替身由原来的产品内假实现原样迁来——服务测试的离线、确定性、零成本；
与 `session_support.SemanticLLM` 同一接缝口径（能力注册表 / 工厂 monkeypatch）。
产品行为见 `app/core/errors.py`：未配置云端能力时抛 `ProviderNotConfigured`，
不再返回任何「看起来像真结果的占位内容」。
"""

import json

from app.core.asr.base import Transcriber
from app.core.embedding.base import Embedder
from app.core.llm.base import ChatMessage, ChatResult, LLMProvider
from app.core.search.base import WebSearch

# 测试假 LLM 在能力注册表里的名字（conftest / 各测试挂替身时用）
FAKE_LLM_PROVIDER = "test-fake-llm"


# ---- 对话替身（原产品内的假实现：按提示词标记返回固定结构） ----

FAKE_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>互动学习小游戏（测试替身）</title>
<style>
  body { font-family: "Microsoft YaHei", sans-serif; text-align: center; padding: 2rem; }
  .card { border: 2px solid #000; padding: 2rem; max-width: 480px; margin: 0 auto; }
</style>
</head>
<body>
<div class="card">
  <h1>互动学习小游戏</h1>
  <div id="counter">0</div>
  <button onclick="bump()">点击 +1</button>
</div>
<script>
  var n = 0;
  function bump() { n += 1; document.getElementById("counter").textContent = n; }
</script>
</body>
</html>"""

FAKE_EXAM_QUESTIONS = [
    {
        "type": "选择",
        "content": "测试替身题：TCP 三次握手的第一步是什么？",
        "options": ["A. SYN", "B. ACK", "C. FIN", "D. RST"],
        "answer": "A",
        "analysis": "客户端发送 SYN 发起连接。",
        "knowledge_point": "TCP三次握手",
    },
    {
        "type": "填空",
        "content": "测试替身填空：TCP 四次挥手需要 ____ 个 FIN 报文。",
        "answer": "2",
        "analysis": "双方各发一个 FIN。",
        "knowledge_point": "TCP四次挥手",
    },
    {
        "type": "简答",
        "content": "简述 TCP 滑动窗口的作用。",
        "answer": "实现流量控制与可靠传输。",
        "analysis": "窗口机制控制发送速率。",
        "knowledge_point": "TCP滑动窗口",
    },
]

FAKE_PPT_SLIDES = [
    {"role": "封面", "title": "测试课件", "points": ["测试替身课程"]},
    {"role": "目录", "title": "本课内容", "points": ["要点一", "要点二"]},
    {"role": "内容", "title": "要点一", "points": ["内容一", "内容二"]},
    {"role": "总结", "title": "本课小结", "points": ["总结一"]},
]

FAKE_INTENT = {
    "topic": "TCP 三次握手",
    "grade": "大二",
    "duration_minutes": 45,
    "objectives": ["理解测试目标"],
    "knowledge_points": ["TCP三次握手"],
    "key_points": ["测试重点"],
    "difficult_points": ["测试难点"],
    "style": "学术",
    "teaching_methods": ["讲授"],
    "interactivity": "无",
}

FAKE_MARK = "[测试替身提取]"


def _fake_summary(prompt: str) -> str:
    """从概要提示词里拆出资料正文，回显前两行拼成资料概要（确定性、内容相关）。"""
    _, _, body = prompt.partition("资料内容：\n")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    picked = "；".join(lines[:2]) if lines else "（资料没有可读正文）"
    return f"{FAKE_MARK} 资料概要：{picked}"


def _subject_list_from_prompt(prompt: str) -> list[str]:
    """从提取提示词里拆出学科清单（「学科清单」节里的「- 」行，到「知识点字段」止）。"""
    names: list[str] = []
    in_section = False
    for line in prompt.splitlines():
        if line.startswith("学科清单"):
            in_section = True
            continue
        if in_section:
            if line.startswith("知识点字段"):
                break
            name = line.strip().lstrip("-").strip()
            if name:
                names.append(name)
    return names


def _fake_knowledge(prompt: str) -> dict:
    """从提取提示词里拆出正文，取前 3 个非空行回显为节点/边（确定性、内容相关）。

    学科归类与产品提示词同一契约：subject 从提示词给的学科清单里按序轮转选取
    （清单内取值），chapter 尽力填写——清单注入缺失时两个留空（旧行为兼容）。
    """
    _, _, body = prompt.partition("教学内容：\n")
    seen: set[str] = set()
    picked: list[str] = []
    for raw in body.splitlines():
        line = raw.strip().lstrip("#*-•— \t")
        if not line:
            continue
        title = line[:12]
        if title in seen:
            continue
        seen.add(title)
        picked.append(line)
        if len(picked) == 3:
            break
    subjects = _subject_list_from_prompt(prompt)
    difficulties = ("基础", "进阶", "难点")
    importances = ("必修", "选修", "了解")
    nodes = [
        {
            "title": line[:12],
            "content": f"{FAKE_MARK} {line[:60]}",
            "difficulty": difficulties[i % 3],
            "importance": importances[i % 3],
            **(
                {"subject": subjects[i % len(subjects)], "chapter": f"第{i + 1}章"}
                if subjects
                else {}
            ),
        }
        for i, line in enumerate(picked)
    ]
    edges = [
        {"from": nodes[i]["title"], "to": nodes[i + 1]["title"], "relation_type": "相关关联"}
        for i in range(len(nodes) - 1)
    ]
    return {"nodes": nodes, "edges": edges}


class FakeLLM(LLMProvider):
    """对话替身：按提示词标记作答，内容只服务测试断言（与产品行为无关）。"""

    name = "fake-test"

    def knowledge_payload(self, prompt: str) -> dict:
        """知识提取的作答口径；特殊归类场景（清单外 / 缺失）由子类覆写。"""
        return _fake_knowledge(prompt)

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        last = messages[-1].content if messages else ""
        if "资料概要编写助手" in last:
            return ChatResult(content=_fake_summary(last))
        if "意图分析模块" in last:
            return ChatResult(content=json.dumps(FAKE_INTENT, ensure_ascii=False))
        if "教学知识图谱构建助手" in last:
            return ChatResult(content=json.dumps(self.knowledge_payload(last), ensure_ascii=False))
        if "判断两段知识描述是否相互矛盾" in last:
            return ChatResult(
                content=json.dumps(
                    {"conflict": False, "description": "无矛盾（测试替身）"}, ensure_ascii=False
                )
            )
        if "备课会话的语义判定器" in last:
            return ChatResult(content=json.dumps({"skip": False}, ensure_ascii=False))
        if "HTML5 互动学习小游戏" in last:
            return ChatResult(content=FAKE_HTML)
        if "你是教学课件设计师" in last:
            return ChatResult(content=json.dumps({"slides": FAKE_PPT_SLIDES}, ensure_ascii=False))
        if "你是出题专家" in last:
            return ChatResult(
                content=json.dumps({"questions": FAKE_EXAM_QUESTIONS}, ensure_ascii=False)
            )
        return ChatResult(content=f"[测试替身] 收到你的消息：{last[:50]}")

    async def vision(self, image_path: str, prompt: str) -> str:
        return f"{FAKE_MARK}（占位解读）测试替身的多模态返回，与画面内容无关。"


class OffListSubjectLLM(FakeLLM):
    """清单外学科替身：模型无视学科清单、自造清单外学科名。

    测「未分类」兜底（票 08）：无论提示词怎么约束，
    全部知识点都带同一个清单外的 subject 回来。
    """

    def __init__(self, subject: object = "考古学") -> None:
        self._subject = subject

    def knowledge_payload(self, prompt: str) -> dict:
        payload = _fake_knowledge(prompt)
        for node in payload["nodes"]:
            node["subject"] = self._subject
        return payload


class PromptCapturingLLM(FakeLLM):
    """记录收到的提示词的替身：断言提示词约束（学科清单注入、硬约束文案）用。"""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        self.prompts.append(messages[-1].content if messages else "")
        return await super().chat(messages, **kwargs)


# ---- 向量化替身（原产品内的假实现：以文本长度为特征的确定性向量） ----

FAKE_EMBED_DIM = 8


class FakeEmbedder(Embedder):
    name = "fake-test"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[len(t) * 1.0] * FAKE_EMBED_DIM for t in texts]


# ---- 搜索替身（原产品内的假实现：带标记的占位结果） ----

FAKE_SEARCH_MARK = "（测试替身网络搜索）"


class FakeSearch(WebSearch):
    name = "fake-test"

    async def search(self, query: str, count: int = 5, summary: bool = False) -> list[dict]:
        n = max(1, min(count, 5))
        return [
            {
                "title": f"{FAKE_SEARCH_MARK}{query} 相关结果 {i + 1}",
                "url": f"https://example.com/fake/{i + 1}",
                "snippet": f"{FAKE_SEARCH_MARK}测试替身占位内容。",
            }
            for i in range(n)
        ]


# ---- 转写替身（原产品内的假实现：固定文字稿） ----

FAKE_TRANSCRIPT = "（测试替身录音转写）本段录音讲解计算机网络概述与 TCP 三次握手。"


class FakeTranscriber(Transcriber):
    """转写替身：默认返回固定文字稿；需要唯一正文的用例（如文献笔记）传 transcript 覆盖。"""

    name = "fake-test"

    def __init__(self, transcript: str | None = None) -> None:
        self._transcript = transcript if transcript is not None else FAKE_TRANSCRIPT

    async def transcribe(self, file_path: str) -> str:
        return self._transcript


class TitleVectorEmbedder(Embedder):
    """标题空间回归替身：记录调用，可模拟模型／实际维度切换与服务失败。"""

    name = "title-vector-test"

    def __init__(self, dimension: int = 8, model: str = "model-a") -> None:
        self.dimensions = dimension
        self.model = model
        self.base_url = "https://example.test/v1"
        self.calls: list[list[str]] = []
        self.fail = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError("标题向量服务失败。")
        return [[1.0] + [0.0] * (self.dimensions - 1) for _ in texts]


class ContradictingLLM(FakeLLM):
    """定义冲突回归：只让冲突比对返回矛盾，其余沿用离线提取。"""

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        if "判断两段知识描述是否相互矛盾" in messages[-1].content:
            return ChatResult(content='{"conflict": true, "description": "定义矛盾。"}')
        return await super().chat(messages, **kwargs)
