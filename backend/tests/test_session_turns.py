"""备课会话一轮对话的行为测试（票 05）：持久化 + 状态机收编 + 意图增量累积 + 语义跳过。

只断言 HTTP 响应与数据变迁（ADR-0002 与 spec 的测试决策），不断言内部函数调用；
被替换的只是 LLM 能力替身（见 `tests/session_support.py`）。
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api as api_package
from app.db import SessionLocal, init_db
from app.db.models import PrepSession
from app.main import app
from tests.session_support import analyzed_text

client = TestClient(app)
init_db()  # 幂等：会话与消息表在临时库里就位


@pytest.fixture(autouse=True)
def _isolated_outputs(isolated_output_dir):
    """本模块每条用例都会产出备课文件：落盘重定向到临时目录（不写 backend/data）。"""
    return isolated_output_dir

# 教师两轮表述 + 语义网关据此抽取的要素（网关按「最新表述覆盖旧值」合并，见 session_support）
FIRST_TURN = "给初二讲一次函数，时长 40 分钟，教学目标是理解一次函数的图象"
FIRST_FIELDS = {
    "topic": "一次函数",
    "grade": "初二",
    "duration_minutes": 40,
    "objectives": ["理解一次函数的图象"],
}
SECOND_TURN = "补充一下：风格是情境导入，重点是斜率与图象"
SECOND_FIELDS = {"style": "情境导入", "key_points": ["斜率与图象"]}
LEARNED = {FIRST_TURN: FIRST_FIELDS, SECOND_TURN: SECOND_FIELDS}
# 关键字段：增量累积与全量重析必须在这几项上一致
KEY_FIELDS = ("topic", "grade", "duration_minutes", "style", "objectives", "key_points")


def _create(**payload) -> dict:
    r = client.post("/api/v1/sessions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _chat(session_id: str | None, content: str) -> dict:
    payload: dict = {"messages": [{"role": "user", "content": content}]}
    if session_id is not None:
        payload["session_id"] = session_id
    r = client.post("/api/v1/chat", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _session_row(session_id: str) -> PrepSession | None:
    db = SessionLocal()
    try:
        return db.get(PrepSession, session_id)
    finally:
        db.close()


# ---- 会话内一轮对话：落库 + 换设备回看 ----


def test_session_turns_persist_history_for_other_devices(install_semantic_llm):
    """多轮对话全程落库：换设备（新客户端、无本地状态）打开会话，历史与两种回复形态都在。"""
    install_semantic_llm(learned=LEARNED)
    created = _create()

    first = _chat(created["id"], FIRST_TURN)
    second = _chat(created["id"], SECOND_TURN)

    assert first["clarifying"] is True and first["artifacts"] is None  # 缺风格与重点 → 澄清回复
    assert second["clarifying"] is False and second["artifacts"] is not None  # 信息够 → 生成回复
    assert first["session_id"] == created["id"] == second["session_id"]

    fresh_client = TestClient(app)  # 另一台设备：不依赖任何本地状态
    history = fresh_client.get(f"/api/v1/sessions/{created['id']}").json()

    assert [m["seq"] for m in history["messages"]] == [1, 2, 3, 4]
    assert [m["role"] for m in history["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [m["kind"] for m in history["messages"]] == [
        None,
        "澄清回复",
        None,
        "生成回复",
    ]
    generate_message = history["messages"][-1]
    assert generate_message["artifacts"]["ppt"]["slides"]  # 生成物随消息回看
    assert history["session"]["message_count"] == 4
    # 首轮教师需求自动充当会话标题
    assert history["session"]["title"] == FIRST_TURN[:30]
    # 累积意图落库：下一轮无需重析全部历史（数据变迁断言）
    row = _session_row(created["id"])
    assert row is not None and row.intent is not None
    assert row.intent["topic"] == "一次函数" and row.intent["style"] == "情境导入"


def test_chat_with_session_uses_session_granularity(install_semantic_llm):
    """追问粒度以会话设置为准：同一句话在快速档直接出结果，在标准档继续追问。"""
    install_semantic_llm(learned={"给初二讲一次函数，时长 40 分钟，风格是情境导入": {
        "topic": "一次函数",
        "grade": "初二",
        "duration_minutes": 40,
        "style": "情境导入",
    }})
    utterance = "给初二讲一次函数，时长 40 分钟，风格是情境导入"
    quick = _create(granularity="快速")
    standard = _create(granularity="标准")

    assert _chat(quick["id"], utterance)["clarifying"] is False  # 快速档只要时长与风格
    assert _chat(standard["id"], utterance)["clarifying"] is True  # 标准档还要目标与重点

    # 会话内切粒度立即影响后续对话
    patched = client.patch(f"/api/v1/sessions/{standard['id']}", json={"granularity": "快速"})
    assert patched.status_code == 200
    assert _chat(standard["id"], "就这样")["clarifying"] is False


def test_chat_with_unknown_session_returns_404():
    """未知会话不静默降级成无状态，而是 404（前端据此提示会话已不存在）。"""
    r = client.post(
        "/api/v1/chat",
        json={"session_id": "not-a-session", "messages": [{"role": "user", "content": "讲一次函数"}]},
    )
    assert r.status_code == 404
    assert "会话不存在" in r.json()["detail"]


def test_chat_with_session_needs_a_teacher_message():
    """带会话时本轮需求取自最后一条教师消息：只有助手消息的回显请求被拒（422），不落任何消息。"""
    created = _create()
    r = client.post(
        "/api/v1/chat",
        json={"session_id": created["id"], "messages": [{"role": "assistant", "content": "好的"}]},
    )

    assert r.status_code == 422
    history = client.get(f"/api/v1/sessions/{created['id']}").json()
    assert history["session"]["message_count"] == 0
    assert history["messages"] == []


def test_chat_without_session_stays_stateless(install_semantic_llm):
    """不传会话标识时保持无状态既有行为：不落库、不回显会话 id。"""
    install_semantic_llm(learned=LEARNED)
    before = len(client.get("/api/v1/sessions").json()["sessions"])

    body = _chat(None, FIRST_TURN)

    assert body["session_id"] is None
    assert body["clarifying"] is True
    assert len(client.get("/api/v1/sessions").json()["sessions"]) == before


# ---- 跳过追问：语义判定（正反例） ----


def test_skip_clarification_accepts_a_synonym_phrasing(install_semantic_llm):
    """正例：换一种说法表达「信息够了」也算跳过追蹤——旧词表一个都没命中，现在按语义判定。"""
    install_semantic_llm(learned=LEARNED, skip=True)
    created = _create()
    _chat(created["id"], FIRST_TURN)  # 缺风格与重点 → 先澄清

    synonym = "需求都清楚了，别再问了，直接给我结果"
    for old_word in ("开始生成", "就这样", "生成吧", "够了", "可以了", "直接生成"):
        assert old_word not in synonym  # 旧子串词表抓不到这句话

    outcome = _chat(created["id"], synonym)

    assert outcome["clarifying"] is False and outcome["artifacts"] is not None


def test_negated_generation_is_not_treated_as_skip(install_semantic_llm):
    """反例：字面像跳过但语义相反时继续追问——旧子串判定会把「可以了」当跳过。"""
    llm = install_semantic_llm(learned=LEARNED, skip=False)
    created = _create()
    _chat(created["id"], FIRST_TURN)

    negated = "现在可以了，不过我还想补充教学目标"
    assert "可以了" in negated  # 旧词表命中，但语义上教师仍在补充

    outcome = _chat(created["id"], negated)

    assert outcome["clarifying"] is True and outcome["artifacts"] is None
    # 判定输入是本轮原话本身（语义判定），不是词表匹配
    assert llm.skip_prompts and negated in llm.skip_prompts[-1]


# ---- 意图按会话增量累积 ----


def test_session_intent_accumulation_matches_full_reanalysis(install_semantic_llm):
    """行为对比：会话内增量累积出的意图，与整段重析在关键字段上一致，且不丢前几轮的要素。"""
    install_semantic_llm(learned=LEARNED)
    created = _create()
    _chat(created["id"], FIRST_TURN)
    incremental = _chat(created["id"], SECOND_TURN)["artifacts"]["intent"]

    full = client.post(
        "/api/v1/chat",
        json={
            "messages": [
                {"role": "user", "content": FIRST_TURN},
                {"role": "user", "content": SECOND_TURN},
            ]
        },
    ).json()["artifacts"]["intent"]

    assert {field: incremental[field] for field in KEY_FIELDS} == {
        field: full[field] for field in KEY_FIELDS
    }
    # 累积结果 = 两轮要素的合并（第一轮的要素没被第二轮的增量冲掉）
    assert incremental["topic"] == "一次函数" and incremental["grade"] == "初二"
    assert incremental["duration_minutes"] == 40
    assert incremental["objectives"] == ["理解一次函数的图象"]
    assert incremental["style"] == "情境导入" and incremental["key_points"] == ["斜率与图象"]


def test_incremental_intent_analyzes_only_the_new_turn(install_semantic_llm):
    """调用证据：每轮只分析本轮原话（不再把全部历史重析一遍），分析文本量随之下降。"""
    llm = install_semantic_llm(learned=LEARNED)
    created = _create()
    _chat(created["id"], FIRST_TURN)
    _chat(created["id"], SECOND_TURN)

    # 每轮恰好一次意图分析：收编前路由与编排器各析一次，一次生成要花两次
    assert len(llm.intent_prompts) == 2
    incremental_texts = [analyzed_text(prompt) for prompt in llm.intent_prompts]
    assert incremental_texts[0] == FIRST_TURN
    assert incremental_texts[1] == SECOND_TURN  # 第二轮只喂本轮新增，不带第一轮表述
    assert FIRST_TURN not in incremental_texts[1]

    # 对照：无状态全量重析把整段历史都喂进去，分析文本量明显更大
    client.post(
        "/api/v1/chat",
        json={
            "messages": [
                {"role": "user", "content": FIRST_TURN},
                {"role": "user", "content": SECOND_TURN},
            ]
        },
    )
    full_prompt = llm.intent_prompts[-1]
    full_text = analyzed_text(full_prompt)
    assert FIRST_TURN in full_text and SECOND_TURN in full_text
    assert sum(len(text) for text in incremental_texts) < len(full_text)


# ---- 口径与不变式 ----


def test_api_layer_holds_no_clarify_or_skip_judgement():
    """守卫：澄清与追问判断不在路由层——api/ 不出现缺失要素、追问话术与跳过词表（ADR-0002）。"""
    forbidden = (
        "missing_fields",
        "build_question",
        "FIELD_QUESTIONS",
        "GRANULARITY_FIELDS",
        "should_skip_clarification",
        "_SKIP_WORDS",
        "analyze_intent",
        "orchestrate",
    )
    api_dir = Path(api_package.__file__).resolve().parent
    offenders = [
        (path.name, token)
        for path in api_dir.rglob("*.py")
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_db_models_docstring_points_to_existing_docs():
    """票 01 登记的断链已修：模型文件的文档指针指向仓库内真实存在的文件。"""
    repo_root = Path(api_package.__file__).resolve().parents[3]
    source = (repo_root / "backend" / "app" / "db" / "models.py").read_text(encoding="utf-8")

    assert "DESIGN.md" not in source
    pointers = re.findall(r"`([^`]+\.md)`", source)
    assert pointers, "模型文件应说明表结构出处"
    for pointer in pointers:
        assert (repo_root / pointer).exists(), f"文档指针断链: {pointer}"
