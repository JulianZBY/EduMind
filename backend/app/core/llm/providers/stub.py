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


# 知识图谱提取提示词命中时返回的固定节点/边：与 stub 课件主题（TCP）一致，
# 保证 stub 模式下上传解析后知识图谱有节点可展示。
_STUB_KNOWLEDGE = {
    "nodes": [
        {
            "title": "TCP 三次握手",
            "content": "通过 SYN/SYN+ACK/ACK 三步报文交互建立可靠连接",
            "difficulty": "基础",
            "importance": "必修",
        },
        {
            "title": "滑动窗口机制",
            "content": "接收方通告窗口控制速率，允许连续发送多个报文段",
            "difficulty": "进阶",
            "importance": "必修",
        },
        {
            "title": "四次挥手",
            "content": "通过 FIN/ACK 四步报文交互释放连接",
            "difficulty": "基础",
            "importance": "选修",
        },
    ],
    "edges": [
        {"from": "TCP 三次握手", "to": "滑动窗口机制", "relation_type": "相关关联"},
        {"from": "TCP 三次握手", "to": "四次挥手", "relation_type": "相关关联"},
    ],
}


class StubProvider(LLMProvider):
    name = "stub"

    async def chat(self, messages: list[ChatMessage], **kwargs) -> ChatResult:
        last = messages[-1].content if messages else ""
        if "意图分析模块" in last:
            return ChatResult(content=json.dumps(_STUB_INTENT, ensure_ascii=False))
        if "教学知识图谱构建助手" in last:
            return ChatResult(content=json.dumps(_STUB_KNOWLEDGE, ensure_ascii=False))
        if "判断两段知识描述是否相互矛盾" in last:
            return ChatResult(
                content=json.dumps(
                    {"conflict": False, "description": "无矛盾（stub）"}, ensure_ascii=False
                )
            )
        if "HTML5 互动学习小游戏" in last:
            return ChatResult(content=_STUB_HTML)
        if "你是教学课件设计师" in last:
            return ChatResult(content=json.dumps({"slides": _STUB_PPT_SLIDES}, ensure_ascii=False))
        if "你是出题专家" in last:
            return ChatResult(
                content=json.dumps({"questions": _STUB_EXAM_QUESTIONS}, ensure_ascii=False)
            )
        return ChatResult(content=f"[stub] 收到你的消息：{last[:50]}")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 确定性假向量：以文本长度为特征（len * 1.0 转浮点，不引入可抛出转换）
        return [[len(t) * 1.0] * 8 for t in texts]
