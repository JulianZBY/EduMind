"""桩 provider：无 key 可跑，返回可预测假响应，供骨架阶段联调。"""

import json

from app.core.llm.base import ChatMessage, ChatResult, LLMProvider

# 创意内容提示词（HTML5 互动学习小游戏）命中时返回的固定单文件 HTML，
# 保证 stub 模式下互动内容产物可解析（无外部依赖，内联 CSS + JS）。
_STUB_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>互动学习小游戏（stub）</title>
<style>
  body { font-family: "Microsoft YaHei", sans-serif; text-align: center; padding: 2rem; background: #f5f7fa; }
  .card { background: #fff; border-radius: 12px; padding: 2rem; max-width: 480px; margin: 0 auto; box-shadow: 0 2px 8px rgba(0,0,0,.1); }
  #counter { font-size: 2rem; color: #1a73e8; margin: 1rem 0; }
  button { padding: .6rem 1.5rem; font-size: 1rem; border: none; border-radius: 8px; background: #1a73e8; color: #fff; cursor: pointer; }
</style>
</head>
<body>
<div class="card">
  <h1>互动学习小游戏</h1>
  <p>点击按钮开始互动：</p>
  <div id="counter">0</div>
  <button onclick="bump()">点击 +1</button>
</div>
<script>
  var n = 0;
  function bump() { n += 1; document.getElementById("counter").textContent = n; }
</script>
</body>
</html>"""

# 试卷提示词（出题专家）命中时返回的固定题目 JSON：题型覆盖选择/填空/简答，
# 每题带考查知识点标注，保证 stub 模式下按需生成端点返回可解析的题目数组。
_STUB_EXAM_QUESTIONS = [
    {
        "type": "选择",
        "content": "TCP 建立连接需要完成几次握手？",
        "options": ["A. 2 次", "B. 3 次", "C. 4 次", "D. 1 次"],
        "answer": "B",
        "analysis": "三次握手：SYN → SYN+ACK → ACK，用于同步双方初始序号。",
        "knowledge_point": "TCP三次握手",
    },
    {
        "type": "填空",
        "content": "TCP 释放连接需要完成____次挥手。",
        "answer": "四",
        "analysis": "四次挥手确保双向数据传输都完成后才释放连接。",
        "knowledge_point": "TCP四次挥手",
    },
    {
        "type": "简答",
        "content": "简述 TCP 滑动窗口机制的作用。",
        "answer": "滑动窗口允许发送方在未收到确认前连续发送多个报文段，实现流量控制并提高传输效率。",
        "analysis": "接收方通过通告窗口大小控制发送速率，防止接收缓冲区溢出。",
        "knowledge_point": "TCP滑动窗口",
    },
]


# 课件提示词（教学课件设计师）命中时返回的固定结构：每页带 role 角色标注（封面/目录/内容/总结），
# 且满足 prompt 排版约定（title ≤15字、要点 ≤5条每条 ≤30字），保证 stub 模式下
# 生成结构满足角色约定、渲染器可按角色差异化排版。
_STUB_PPT_SLIDES = [
    {
        "role": "封面",
        "title": "TCP 协议入门",
        "points": ["计算机网络基础课程", "面向本科二年级"],
    },
    {
        "role": "目录",
        "title": "本课内容",
        "points": ["TCP 三次握手", "TCP 四次挥手", "滑动窗口机制"],
    },
    {
        "role": "内容",
        "title": "TCP 三次握手",
        "points": ["SYN → SYN+ACK → ACK", "同步双方初始序号", "防止失效连接请求突然到达"],
    },
    {
        "role": "内容",
        "title": "滑动窗口机制",
        "points": ["允许连续发送多个报文段", "接收方通告窗口控制速率"],
    },
    {
        "role": "总结",
        "title": "本课小结",
        "points": ["三次握手建立可靠连接", "四次挥手释放连接", "滑动窗口实现流量控制"],
    },
]


# 意图分析提示词命中时返回的固定完整意图：字段齐全（含 objectives/key_points/
# interactivity/teaching_methods），使各追问粒度的 missing_fields 均为空，
# stub 模式下备课主链路（澄清 → 检索 → 生成）可一次走通。
_STUB_INTENT = {
    "topic": "TCP 三次握手",
    "grade": "大二",
    "duration_minutes": 45,
    "objectives": ["理解三次握手过程", "掌握滑动窗口机制"],
    "knowledge_points": ["TCP三次握手", "滑动窗口"],
    "key_points": ["三次握手报文交互"],
    "difficult_points": ["为什么是三次而不是两次"],
    "style": "学术",
    "teaching_methods": ["讲授", "案例"],
    "interactivity": "无",
}


# 图谱提取提示词（教学知识图谱构建助手）命中时：回显正文前几行作为演示知识点
# （内容打上 stub 标记），避免与上传资料无关的固定假数据误导用户；正文为空返回空图。
_STUB_MARK = "[stub 演示提取]"

# 视觉提取（图片 / 视频帧）的 stub 返回：无云端多模态能力时不再抛 NotImplementedError
# （ADR-0003 的「必有 stub」），而是给出**确定性**的占位解读，并照抄 stub 文本对话的标记风格
# 打上「stub 视觉提取」标记——教师看到的解析分块必须能一眼看出这不是真实识别结果
# （CONTEXT.md 措辞纪律：说「stub 视觉提取」）。
_STUB_VISION_MARK = "[stub 视觉提取]"
_STUB_VISION_TEXT = (
    f"{_STUB_VISION_MARK}（占位解读，不是真实识别结果）本次运行没有可用的云端多模态能力，"
    "图片与视频帧的解读由 stub 返回固定内容，不反映画面实际内容。"
    "画面要点：教学示意图（占位）；可提取知识点：接入云端多模态能力后由真实识别给出。"
)


def _stub_knowledge(prompt: str) -> dict:
    """从提取提示词中拆出正文，取前 3 个非空行回显为节点/边（确定性、内容相关）。"""
    _, _, body = prompt.partition("教学内容：\n")
    seen_titles: set[str] = set()
    picked: list[str] = []
    for raw in body.splitlines():
        line = raw.strip().lstrip("#*-•— \t")
        if not line:
            continue
        title = line[:12]
        if title in seen_titles:  # 同前缀行去重，避免边自环
            continue
        seen_titles.add(title)
        picked.append(line)
        if len(picked) == 3:
            break
    difficulties = ("基础", "进阶", "难点")
    importances = ("必修", "选修", "了解")
    nodes = [
        {
            "title": line[:12],
            "content": f"{_STUB_MARK} {line[:60]}",
            "difficulty": difficulties[i % len(difficulties)],
            "importance": importances[i % len(importances)],
        }
        for i, line in enumerate(picked)
    ]
    edges = [
        {"from": nodes[i]["title"], "to": nodes[i + 1]["title"], "relation_type": "相关关联"}
        for i in range(len(nodes) - 1)
    ]
    return {"nodes": nodes, "edges": edges}


class StubProvider(LLMProvider):
    name = "stub"

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        last = messages[-1].content if messages else ""
        if "意图分析模块" in last:
            return ChatResult(content=json.dumps(_STUB_INTENT, ensure_ascii=False))
        if "教学知识图谱构建助手" in last:
            return ChatResult(content=json.dumps(_stub_knowledge(last), ensure_ascii=False))
        if "判断两段知识描述是否相互矛盾" in last:
            return ChatResult(
                content=json.dumps(
                    {"conflict": False, "description": "无矛盾（stub）"}, ensure_ascii=False
                )
            )
        # 跳过追问的语义判定（提示词见 core/clarify.py 的 SKIP_JUDGEMENT_MARKER）：
        # stub 不做语义判断，一律不跳过——追问与否仍由意图完整性决定，不会误跳过追问。
        if "备课会话的语义判定器" in last:
            return ChatResult(content=json.dumps({"skip": False}, ensure_ascii=False))
        if "HTML5 互动学习小游戏" in last:
            return ChatResult(content=_STUB_HTML)
        if "你是教学课件设计师" in last:
            return ChatResult(content=json.dumps({"slides": _STUB_PPT_SLIDES}, ensure_ascii=False))
        if "你是出题专家" in last:
            return ChatResult(
                content=json.dumps({"questions": _STUB_EXAM_QUESTIONS}, ensure_ascii=False)
            )
        return ChatResult(content=f"[stub] 收到你的消息：{last[:50]}")

    async def vision(self, image_path: str, prompt: str) -> str:
        """stub 视觉提取：返回确定性占位解读，带「stub 视觉提取」标记。

        入参按接口签名保留但不使用：stub 既没有云端多模态可读图，也不需要 prompt——
        输出与入参无关、每次相同，教师侧看到的分块内容因此能稳定识别为「不是真实识别结果」。
        """
        return _STUB_VISION_TEXT
