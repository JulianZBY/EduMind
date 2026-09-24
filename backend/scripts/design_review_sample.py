import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.generate.exam import render_exam
from app.generate.ppt import render_ppt
from app.generate.word import render_word
from app.main import app

parser = argparse.ArgumentParser()
parser.add_argument("--live-edit", action="store_true")
parser.add_argument("--env-file", default=".env")
args = parser.parse_args()
out = Path(__file__).resolve().parents[2] / "artifacts/design-review"
out.mkdir(parents=True, exist_ok=True)
slides = [
    {
        "role": "封面",
        "title": "TCP 三次握手",
        "points": ["计算机网络 · 大学一年级", "45 分钟 / 从建立连接到理解可靠通信"],
    },
    {
        "role": "目录",
        "title": "这堂课，我们一起弄清楚",
        "points": [
            "为什么通信前需要建立连接？",
            "三次握手分别传递了什么？",
            "两次握手为什么不够？",
            "用角色扮演还原握手过程",
        ],
    },
    {
        "role": "内容",
        "title": "建立连接的三个步骤",
        "points": [
            "客户端发送 SYN：我准备好了，可以连接吗？",
            "服务端回复 SYN + ACK：收到，我也准备好了。",
            "客户端发送 ACK：确认收到，现在开始通信。",
        ],
    },
    {
        "role": "内容",
        "title": "为什么需要第三次确认？",
        "points": [
            "服务端需要确认自己的回复已被客户端收到。",
            "第三次确认让双方都能判断对方的收发能力正常。",
        ],
    },
    {
        "role": "总结",
        "title": "带走三个关键认识",
        "points": [
            "建立连接前，需要确认双方的收发能力。",
            "SYN → SYN + ACK → ACK，完成连接建立。",
            "连接建立为可靠通信准备好初始状态。",
        ],
    },
]
render_ppt(slides, str(out / "sample-courseware.pptx"), "学术")
data = {
    "title": "TCP 三次握手 · 教学设计",
    "objectives": {
        "knowledge": ["理解 TCP 建立连接的三个步骤及各自作用。"],
        "ability": ["能用时序图解释三次握手，区分 SYN 与 ACK。"],
        "emotion": ["在角色扮演中形成严谨的通信协议思维。"],
    },
    "key_points": ["三次握手的报文顺序与确认关系。"],
    "difficult_points": ["解释为什么两次握手不足以确认双向通信。"],
    "process": [
        {
            "stage": "情境导入",
            "minutes": 5,
            "content": "用拨打电话的情境引导学生讨论：怎样确认双方都能听到对方？记录学生提出的确认方式。",
        },
        {
            "stage": "概念建构",
            "minutes": 15,
            "content": "依次展示 SYN、SYN + ACK、ACK，讲解发送方、接收方和确认对象。引导学生在纸上画出双方的消息时序。",
        },
        {
            "stage": "合作探究",
            "minutes": 15,
            "content": "两人分别扮演客户端与服务端，按顺序传递报文卡片。引入回复丢失的情境，讨论缺少第三次确认时服务端无法知道什么。",
        },
        {
            "stage": "评价与总结",
            "minutes": 10,
            "content": "请学生独立写出三次握手顺序，并用一句话解释最后一次 ACK 的作用。针对常见混淆进行反馈。",
        },
    ],
    "activities": ["双人报文卡片演练，交换角色后再次完成握手。"],
    "homework": [
        "绘制 TCP 三次握手时序图，标明报文方向和标志位。",
        "思考：确认消息丢失后，通信双方可以采取什么措施？",
    ],
}
render_word(data, str(out / "sample-lesson-plan.docx"))
render_exam(
    [
        {
            "type": "简答",
            "content": "用生活中的例子解释第三次确认的作用。",
            "answer": "确认服务端的回复已被客户端收到。",
            "knowledge_point": "三次握手",
        },
        {
            "type": "填空",
            "content": "三次握手的顺序为 SYN、____、ACK。",
            "answer": "SYN + ACK",
            "knowledge_point": "报文顺序",
        },
    ],
    str(out / "sample-exam.docx"),
)
if not args.live_edit:
    raise SystemExit(0)
local = Settings(_env_file=args.env_file)
settings.llm_provider = local.llm_provider
settings.dashscope_api_key = local.dashscope_api_key
settings.deepseek_api_key = local.deepseek_api_key
with TestClient(app) as client:
    r = client.post(
        "/api/v1/presentations/edit",
        files={"file": ("sample.pptx", (out / "sample-courseware.pptx").read_bytes())},
        data={
            "feedback": "只把第 1 页标题“TCP 三次握手”改成“TCP 连接是怎样建立的”，其他文字全部不变。"
        },
    )
    print("live edit status:", r.status_code)
    result = r.json()
    if r.status_code == 200:
        raw = client.get("/api/v1/files/" + result["filename"]).content
        (out / "sample-edited.pptx").write_bytes(raw)
        assert len(result["changes"]) == 1, result
        assert result["changes"][0]["after"] == "TCP 连接是怎样建立的", result
        (out / "live-edit-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("verified: one targeted title edit, downloadable PPTX")
    else:
        print(result)
