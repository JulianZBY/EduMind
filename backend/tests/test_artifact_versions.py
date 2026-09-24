"""生成物全版本留痕（票 07）：生成即入库 / 版本列表·详情·下载 / 以历史版本为基线修改。

只经 HTTP 缝断言**响应与数据变迁**（不断言任何内部函数调用）；「版本 ↔ 文件」一一对应
按真实落盘内容核验——落盘目录经 conftest 的 `isolated_output_dir` 重定向到临时目录。
LLM / 嵌入走无 Key 的 stub 兜底（`StubProvider`），本文件不替换任何内部函数。
"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pptx import Presentation
from sqlalchemy import select

import app.generate as generate_module
from app.db import SessionLocal, init_db
from app.db.models import ArtifactVersion
from app.main import app

client = TestClient(app)
init_db()  # 幂等：生成物版本表在临时库里就位

# stub 兜底对话的固定意图（见 core/llm/providers/stub.py），用于断言版本标题
STUB_TOPIC = "TCP 三次握手"
# 每次生成都能走完「检索 → 生成」的教师表述（stub 不跳过追问，但意图本身就完整）
TURN = "讲 TCP 三次握手，45 分钟，风格学术"
# 五类生成物（CONTEXT.md「生成物」）在版本中心里的固定展示次序
CLASSES = ("课件", "教案", "提纲", "试卷", "互动内容")


@pytest.fixture(autouse=True)
def _isolated_outputs(isolated_output_dir):
    """本模块每条用例都会产出落盘文件：重定向到临时目录（不写 backend/data/output）。"""
    return isolated_output_dir


# ---- HTTP 助手 ----


def _create(**payload) -> dict:
    r = client.post("/api/v1/sessions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _chat(session_id: str, content: str) -> dict:
    payload = {"session_id": session_id, "messages": [{"role": "user", "content": content}]}
    r = client.post("/api/v1/chat", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _versions(session_id: str) -> dict:
    r = client.get(f"/api/v1/sessions/{session_id}/artifacts")
    assert r.status_code == 200, r.text
    return r.json()


def _group(listing: dict, artifact_type: str) -> dict:
    """取某类生成物的版本组；没有时直接失败并说清是哪一类（避免下游 KeyError 掩盖原因）。"""
    groups = {group["artifact_type"]: group for group in listing["groups"]}
    assert artifact_type in groups, f"版本列表里没有「{artifact_type}」：{sorted(groups)}"
    return groups[artifact_type]


def _stored_bytes(filename: str) -> bytes:
    """读回该版本落盘文件的真实字节（测试里落盘已被重定向到临时目录）。"""
    return (generate_module.OUTPUT_DIR / filename).read_bytes()


def _slide_texts(data: bytes) -> list[str]:
    """回读 pptx 里各页的全部文本：证明下载拿到的确实是这一版的课件。"""
    pages: list[str] = []
    for slide in Presentation(BytesIO(data)).slides:
        texts = []
        for shape in slide.shapes:
            # 只有带文本框的形状有 text_frame（图、图表的形状没有）：按可读性探测
            frame = getattr(shape, "text_frame", None)
            if frame is not None and frame.text.strip():
                texts.append(frame.text)
        pages.append("\n".join(texts))
    return pages


def _version_rows(session_id: str) -> list[ArtifactVersion]:
    db = SessionLocal()
    try:
        # ORM 语句由 SQLAlchemy 编译成参数化查询，参数经绑定传入（非字符串拼接）
        rows = db.execute(
            select(ArtifactVersion)
            .where(ArtifactVersion.session_id == session_id)
            .order_by(ArtifactVersion.artifact_type, ArtifactVersion.version)
        )
        return list(rows.scalars().all())
    finally:
        db.close()


# ---- 生成即入库 + 版本号单调递增 ----


def test_each_generation_records_a_version_with_monotonic_numbers():
    """同一会话两次生成：每次产出都落一条版本记录，同一生成物的版本号从 1 单调递增。"""
    created = _create(granularity="快速")

    first = _chat(created["id"], TURN)
    second = _chat(created["id"], TURN)

    assert first["clarifying"] is False and second["clarifying"] is False
    listing = _versions(created["id"])
    assert listing["session_id"] == created["id"]

    for artifact_type in ("课件", "教案", "提纲"):
        group = _group(listing, artifact_type)
        assert [v["version"] for v in group["versions"]] == [1, 2]
        assert [v["label"] for v in group["versions"]] == ["第 1 版", "第 2 版"]
        assert group["current_version"] == 2
        assert group["current_version_id"] == group["versions"][-1]["id"]
        # 同一生成物的版本之间是「由哪一版衍生而来」的链：第 2 版由第 1 版派生
        assert group["versions"][0]["parent_id"] is None
        assert group["versions"][1]["parent_id"] == group["versions"][0]["id"]
        # 每次生成都是新文件，版本记录与落盘文件一一对应
        filenames = [v["filename"] for v in group["versions"]]
        assert len(set(filenames)) == 2
        assert all((generate_module.OUTPUT_DIR / name).is_file() for name in filenames)
        # 教师看到的标题来自版本记录（不是不可读的文件名）
        assert {v["title"] for v in group["versions"]} == {STUB_TOPIC}
        assert {v["origin"] for v in group["versions"]} == {"生成"}
        assert {v["artifact_type"] for v in group["versions"]} == {artifact_type}


def test_generation_versions_are_written_to_the_database():
    """数据变迁断言：版本记录真的落库（同一生成物的版本号不重复、单调递增）。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)
    _chat(created["id"], TURN)

    rows = _version_rows(created["id"])
    assert rows, "两次生成后库里应有版本记录"
    seen: dict[str, list[int]] = {}
    for row in rows:
        assert row.user_id == "default"
        assert row.filename and row.version >= 1
        seen.setdefault(row.artifact_type, []).append(row.version)
    assert set(seen) == {"课件", "教案", "提纲"}
    for versions in seen.values():
        assert versions == sorted(versions) and len(set(versions)) == len(versions)


def test_generation_message_carries_version_ids():
    """生成回复的产物带上版本标识：会话工作台据此与版本中心取同一份数据。"""
    created = _create(granularity="快速")

    body = _chat(created["id"], TURN)

    ppt = body["artifacts"]["ppt"]
    word = body["artifacts"]["word"]
    outline = body["artifacts"]["outline"]
    assert ppt["version"] == 1 and word["version"] == 1 and outline["version"] == 1
    listing = _versions(created["id"])
    assert _group(listing, "课件")["versions"][0]["id"] == ppt["version_id"]
    assert _group(listing, "教案")["versions"][0]["id"] == word["version_id"]
    assert _group(listing, "提纲")["versions"][0]["id"] == outline["version_id"]


# ---- 版本列表 / 详情 / 下载 ----


def test_version_detail_and_download_return_that_versions_own_file():
    """按版本取回正确文件：详情带该版本内容快照，下载拿到的是这一版落盘文件（不是最新那版）。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)
    _chat(created["id"], TURN)

    group = _group(_versions(created["id"]), "课件")
    older, newest = group["versions"]
    assert older["filename"] != newest["filename"]

    detail = client.get(f"/api/v1/artifacts/{older['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["version"] == 1 and body["filename"] == older["filename"]
    assert body["content"]["slides"]  # 这一版的内容快照
    assert body["parent_id"] is None

    downloaded = client.get(f"/api/v1/artifacts/{older['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == _stored_bytes(older["filename"])
    # 回读文件本身：确实是这一版的课件（每页文本与第 1 版内容快照的标题一一对应）
    pages = _slide_texts(downloaded.content)
    assert len(pages) == len(body["content"]["slides"])
    for page, slide in zip(pages, body["content"]["slides"], strict=True):
        assert slide["title"] in page


def test_download_supports_inline_for_interactive_content():
    """互动内容按版本内联打开：inline=true 时不附下载头（与既有文件端点同口径）。"""
    created = _create()
    payload = {"intent": {"topic": "TCP"}, "session_id": created["id"]}
    r = client.post("/api/v1/interactive/generate", json=payload)
    assert r.status_code == 200, r.text
    version_id = r.json()["version_id"]

    opened = client.get(f"/api/v1/artifacts/{version_id}/download", params={"inline": "true"})
    assert opened.status_code == 200
    assert opened.text.lstrip().startswith("<!DOCTYPE")
    assert "互动学习小游戏" in opened.text
    assert "attachment" not in (opened.headers.get("content-disposition") or "")


def test_artifact_type_filter_and_unknown_versions():
    """列表可按生成物类别过滤；未知会话 / 未知版本不静默返回空，而是 404。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)

    filtered = client.get(
        f"/api/v1/sessions/{created['id']}/artifacts", params={"artifact_type": "课件"}
    )
    assert filtered.status_code == 200
    assert [g["artifact_type"] for g in filtered.json()["groups"]] == ["课件"]

    empty = client.get(
        f"/api/v1/sessions/{created['id']}/artifacts", params={"artifact_type": "试卷"}
    )
    assert empty.status_code == 200
    assert empty.json() == {"session_id": created["id"], "groups": []}

    assert client.get("/api/v1/sessions/not-a-session/artifacts").status_code == 404
    assert client.get("/api/v1/artifacts/not-a-version").status_code == 404
    assert client.get("/api/v1/artifacts/not-a-version/download").status_code == 404
    bad_filter = client.get(
        f"/api/v1/sessions/{created['id']}/artifacts", params={"artifact_type": "不存在的类别"}
    )
    assert bad_filter.status_code == 422


def test_versions_and_files_are_one_to_one():
    """一一对应：每条版本记录都有唯一落盘文件，文件与版本互相可反查。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)
    _chat(created["id"], TURN)
    _chat(created["id"], TURN)

    rows = _version_rows(created["id"])
    filenames = [row.filename for row in rows]
    assert len(filenames) == len(set(filenames))
    listing = client.get(f"/api/v1/sessions/{created['id']}/artifacts").json()
    for row in rows:
        assert (generate_module.OUTPUT_DIR / row.filename).is_file()
        # 由文件反查版本：列表里每个版本都带 filename，同一个文件只属于一个版本
        listed = [
            v for g in listing["groups"] for v in g["versions"] if v["filename"] == row.filename
        ]
        assert [v["id"] for v in listed] == [row.id]


def test_deleting_a_session_removes_its_version_records():
    """删会话连同其版本记录一起清掉（不留无主版本行）；落盘文件不在本票范围（无文件回收）。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)
    assert _version_rows(created["id"])

    deleted = client.delete(f"/api/v1/sessions/{created['id']}")

    assert deleted.status_code == 200
    assert _version_rows(created["id"]) == []
    assert client.get(f"/api/v1/sessions/{created['id']}/artifacts").status_code == 404


# ---- 以历史版本为基线继续修改 ----


def test_revise_from_a_historical_version_creates_a_new_version_and_keeps_the_old_one():
    """以历史版本为基线修改：产出更高版本号的新版本，原版本保持可取回、内容不变。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)
    _chat(created["id"], TURN)  # 当前版本 = 第 2 版
    baseline = _group(_versions(created["id"]), "课件")["versions"][0]  # 拿回第 1 版
    original_bytes = _stored_bytes(baseline["filename"])

    revised_slides = [
        {"role": "封面", "title": "改过的封面", "points": ["从第 1 版出发迭代"]},
        {"role": "总结", "title": "改过的小结", "points": ["保留其余页"]},
    ]
    r = client.post(
        "/api/v1/revise",
        json={
            "slides": revised_slides,
            "feedback": "封面与小结改得更简洁",
            "style": "简约",
            "session_id": created["id"],
            "base_version_id": baseline["id"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version_id"] and body["version"] == 3  # 新版本号更高，不覆盖旧版
    assert body["session_id"] == created["id"]

    group = _group(_versions(created["id"]), "课件")
    assert [v["version"] for v in group["versions"]] == [1, 2, 3]
    newest = group["versions"][-1]
    assert newest["id"] == body["version_id"]
    assert newest["parent_id"] == baseline["id"]  # 由第 1 版衍生
    assert newest["origin"] == "修改"
    assert newest["filename"] == body["filename"]

    # 原版本仍可取回：文件字节未变，详情与下载都还指回第 1 版的内容
    assert _stored_bytes(baseline["filename"]) == original_bytes
    old_download = client.get(f"/api/v1/artifacts/{baseline['id']}/download")
    assert old_download.status_code == 200
    assert old_download.content == original_bytes
    assert client.get(f"/api/v1/artifacts/{baseline['id']}").json()["version"] == 1
    # 新版本取回的是修改后的文件（按版本取回正确文件，而不是「最新那个文件」的别名）
    new_download = client.get(f"/api/v1/artifacts/{newest['id']}/download")
    revised_pages = _slide_texts(new_download.content)
    assert len(revised_pages) == len(revised_slides)
    for page, slide in zip(revised_pages, revised_slides, strict=True):
        assert slide["title"] in page
    assert new_download.content != old_download.content


def test_revise_word_from_a_historical_version_records_a_version():
    """教案修改同模式：以历史教案版本为基线再修改，产出新版本且原版本保持可取。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)
    baseline = _group(_versions(created["id"]), "教案")["versions"][0]

    r = client.post(
        "/api/v1/revise/word",
        json={
            "word": {"objectives": {"knowledge": ["能说出三次握手的过程"]}},
            "feedback": "目标再具体一点",
            "references": ["讲义.pdf"],
            "base_version_id": baseline["id"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2 and body["session_id"] == created["id"]
    assert body["version_id"]

    group = _group(_versions(created["id"]), "教案")
    assert [v["version"] for v in group["versions"]] == [1, 2]
    assert group["versions"][-1]["parent_id"] == baseline["id"]
    assert client.get(f"/api/v1/artifacts/{baseline['id']}/download").status_code == 200


def test_revise_without_session_keeps_existing_behaviour():
    """不带会话标识时保持既有语义：只返回新文件，不落版本记录、不回显版本字段。"""
    created = _create(granularity="快速")

    r = client.post(
        "/api/v1/revise",
        json={"slides": [{"title": "改过的课件", "bullets": ["a"]}], "feedback": "更简洁"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slides"][0]["title"] == "改过的课件"
    assert body["filename"].endswith(".pptx")
    assert body.get("version_id") is None and body.get("version") is None
    assert _versions(created["id"])["groups"] == []  # 没传会话 = 不记版本


def test_revise_rejects_unknown_or_mismatched_baseline():
    """基线必须存在且同类：未知版本 404，类别不符 422（不静默换一类生成物）。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)
    word_version = _group(_versions(created["id"]), "教案")["versions"][0]
    payload = {"slides": [{"title": "改过的课件"}], "feedback": "更简洁"}

    unknown = client.post("/api/v1/revise", json={**payload, "base_version_id": "not-a-version"})
    assert unknown.status_code == 404
    assert "生成物版本不存在" in unknown.json()["detail"]

    mismatched = client.post(
        "/api/v1/revise", json={**payload, "base_version_id": word_version["id"]}
    )
    assert mismatched.status_code == 422
    assert "教案" in mismatched.json()["detail"] and "课件" in mismatched.json()["detail"]

    unknown_session = client.post("/api/v1/revise", json={**payload, "session_id": "not-a-session"})
    assert unknown_session.status_code == 404
    assert "会话不存在" in unknown_session.json()["detail"]


def test_revise_uses_current_version_when_only_session_is_given():
    """只给会话时以当前版本为基线（列表与预览默认打开的那一版），版本号继续递增。"""
    created = _create(granularity="快速")
    _chat(created["id"], TURN)
    current = _group(_versions(created["id"]), "课件")["versions"][-1]

    r = client.post(
        "/api/v1/revise",
        json={
            "slides": [{"title": "改过的封面"}],
            "feedback": "换主题",
            "session_id": created["id"],
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    group = _group(_versions(created["id"]), "课件")
    assert group["versions"][-1]["parent_id"] == current["id"]


def test_revise_on_session_without_that_artifact_returns_404():
    """会话里还没有该生成物时不给「无基线的修改」：404 说明先生成一次。"""
    created = _create(granularity="快速")

    r = client.post(
        "/api/v1/revise",
        json={
            "slides": [{"title": "改过的封面"}],
            "feedback": "换主题",
            "session_id": created["id"],
        },
    )

    assert r.status_code == 404
    assert "基线" in r.json()["detail"]


# ---- 试卷 / 互动内容也走同一条版本入库路径 ----


def test_exam_and_interactive_generation_record_versions():
    """试卷与互动内容按会话生成时同样落版本：五类生成物都在版本中心里可回看、可下载。"""
    created = _create()
    payload = {
        "intent": {"topic": "TCP", "grade": "大二", "duration_minutes": 45},
        "n": 3,
        "session_id": created["id"],
    }

    first_exam = client.post("/api/v1/exam/generate", json=payload)
    second_exam = client.post("/api/v1/exam/generate", json=payload)
    assert first_exam.status_code == 200, first_exam.text
    assert second_exam.status_code == 200, second_exam.text
    assert (first_exam.json()["version"], second_exam.json()["version"]) == (1, 2)

    exam_group = _group(_versions(created["id"]), "试卷")
    assert [v["version"] for v in exam_group["versions"]] == [1, 2]
    assert [v["filename"] for v in exam_group["versions"]] == [
        first_exam.json()["filename"],
        second_exam.json()["filename"],
    ]
    detail = client.get(f"/api/v1/artifacts/{first_exam.json()['version_id']}").json()
    assert detail["content"]["questions"][0]["content"]  # 这一版的题目快照
    assert detail["title"] == "TCP"
    assert (
        client.get(f"/api/v1/artifacts/{first_exam.json()['version_id']}/download").status_code
        == 200
    )


def test_exam_generation_without_session_keeps_existing_behaviour():
    """不带会话标识的生成保持既有语义：照旧出题入库落盘，不落版本记录。"""
    created = _create()

    r = client.post("/api/v1/exam/generate", json={"intent": {"topic": "TCP"}, "n": 3})

    assert r.status_code == 200, r.text
    assert r.json()["bank_saved"] >= 3
    assert r.json().get("version_id") is None
    assert r.json().get("version") is None
    assert _versions(created["id"])["groups"] == []


def test_generation_with_unknown_session_returns_404():
    """带了不存在的会话时不静默丢弃版本记录，而是 404（与对话路径同一口径）。"""
    r = client.post(
        "/api/v1/exam/generate",
        json={"intent": {"topic": "TCP"}, "n": 3, "session_id": "not-a-session"},
    )
    assert r.status_code == 404
    assert "会话不存在" in r.json()["detail"]


# ---- 接口纪律：新端点不得缺 response_model（票 04 的欠账）----


def test_new_endpoints_declare_a_response_model():
    """票 04 指出 16 个操作只有 6 个带 response_model：本票新增 / 改动的 JSON 端点一律不得缺。"""
    schema = app.openapi()

    def _has_model(path: str, method: str) -> bool:
        media = schema["paths"][path][method]["responses"]["200"]["content"]
        body = media["application/json"]["schema"]
        if "$ref" in body:
            return True
        return bool(body.get("properties") or body.get("allOf") or body.get("items"))

    for path, method in (
        ("/api/v1/sessions/{session_id}/artifacts", "get"),
        ("/api/v1/artifacts/{version_id}", "get"),
        ("/api/v1/artifacts/{version_id}/download", "get"),
        ("/api/v1/revise", "post"),
        ("/api/v1/revise/word", "post"),
        ("/api/v1/exam/generate", "post"),
        ("/api/v1/interactive/generate", "post"),
    ):
        if path.endswith("/download"):
            # 二进制文件流：与既有 GET /files/{filename} 同口径，只能注解 responses 而不是 response_model
            media = schema["paths"][path][method]["responses"]["200"]["content"]
            assert "application/octet-stream" in media
            continue
        assert _has_model(path, method), f"{method.upper()} {path} 缺 response_model"


def test_artifact_endpoints_are_documented_with_examples():
    """接口纪律：新端点的 summary / 描述 / 示例 / 错误码 / tag 齐备（生成物分组）。"""
    schema = app.openapi()["paths"]

    listing = schema["/api/v1/sessions/{session_id}/artifacts"]["get"]
    assert listing["summary"] and listing["description"]
    assert listing["tags"] == ["生成物"]
    assert listing["responses"]["200"]["content"]["application/json"]["example"]
    assert "404" in listing["responses"]

    for path, method in (
        ("/api/v1/artifacts/{version_id}", "get"),
        ("/api/v1/artifacts/{version_id}/download", "get"),
    ):
        operation = schema[path][method]
        assert operation["summary"] and operation["description"]
        assert operation["tags"] == ["生成物"]
        assert any(code.startswith(("4", "5")) for code in operation["responses"])
