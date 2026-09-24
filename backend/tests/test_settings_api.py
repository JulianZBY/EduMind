"""设置 API（票 13）：读生效配置（Key 掩码）/ 写设置（即时生效）/ 可选目录，全部经 HTTP 缝。

三组断言口径：

1. **响应与数据变迁**：读回的值、来源（设置页 / 引导默认）、库内 `app_settings` 行；
2. **写穿即时生效**：写完立刻用别的端点或能力工厂观测到新实现（同一进程，不重启）——
   票 03 遗留的「设置写穿即时生效」就落在这里；
3. **任务级模型**：页面上「该任务实际用的模型」的可见值 + 它真的进了那条链路的每次对话。

隔离：每个用例前后清空设置库并回落引导默认——共享临时库里不留设置行，避免污染其它用例
（设置项会改进程内配置，漏清就会串到别的用例）。落盘隔离沿用 conftest。
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings, settings
from app.core.asr.factory import get_transcriber
from app.core.catalog import FIELDS
from app.core.intent import analyze_intent
from app.core.llm.base import ChatResult, LLMProvider
from app.core.llm.factory import LLM_BUILDERS, get_llm
from app.core.llm.providers.openai_compat import OpenAICompatProvider
from app.core.parser.factory import get_pdf_parser
from app.core.search.factory import get_search
from app.core.settings_store import clear_stored_settings
from app.db import SessionLocal, init_db
from app.db.models import AppSetting
from app.generate.outline import generate_outline
from app.knowledge.conflict import compare_content
from app.main import app

client = TestClient(app)
init_db()  # 幂等：设置表在临时库里就位

PLAINTEXT = "sk-live-2f7d9a41"
MASKED_TAIL = "9a41"


@pytest.fixture(autouse=True)
def _clean_settings_store():
    """用例前后都清空设置库并回落引导默认。"""
    clear_stored_settings()
    yield
    clear_stored_settings()


def _get() -> dict:
    response = client.get("/api/v1/settings")
    assert response.status_code == 200, response.text
    return response.json()


def _put(payload: dict) -> dict:
    response = client.put("/api/v1/settings", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _stored_rows() -> dict[str, str]:
    with SessionLocal() as db:
        return {row.key: row.value for row in db.execute(select(AppSetting)).scalars()}


def _by_name(rows: list[dict], key: str = "name") -> dict[str, dict]:
    return {row[key]: row for row in rows}


# ---- 读取：引导默认 -


def test_read_starts_from_bootstrap_defaults():
    """没在设置页改过时，读回来的一切都是 .env 引导默认，Key 一个都没配。"""
    view = _get()

    assert view["provider"]["value"] == "stub"
    assert view["provider"]["label"] == "stub 模式"
    assert view["provider"]["source"] == "引导默认"
    assert view["provider"]["ready"] is True
    assert set(_by_name(view["items"])) == {
        "llm_base_url",
        "llm_model",
        "llm_vision_model",
        "embedding_base_url",
        "embedding_model",
    }
    assert all(item["source"] == "引导默认" for item in view["items"])
    assert all(not key["configured"] and key["masked"] == "" for key in view["keys"])
    assert {cap["key"] for cap in view["capabilities"]} == {
        "asr_provider",
        "pdf_strategy",
        "search_provider",
        "embedding_provider",
        "retrieval_strategy",
        "chunk_strategy",
    }
    assert all(cap["source"] == "引导默认" for cap in view["capabilities"])


def test_catalog_lists_providers_implementations_and_tasks():
    """可选目录就是「能选什么」的唯一出处：供应商目录 + 各能力实现 + 任务清单。"""
    response = client.get("/api/v1/settings/catalog")
    assert response.status_code == 200, response.text
    catalog = response.json()

    providers = _by_name(catalog["providers"], "id")
    assert set(providers) == {"stub", "dashscope", "deepseek", "siliconflow", "custom"}
    assert providers["deepseek"]["key_field"] == "deepseek_api_key"
    assert providers["deepseek"]["chat_models"] == ["deepseek-chat", "deepseek-reasoner"]
    assert providers["dashscope"]["base_url"].startswith("https://")
    assert providers["stub"]["key_field"] == ""  # stub 模式不需要 Key
    assert providers["custom"]["accepts_any_model"] is True

    capabilities = _by_name(catalog["capabilities"], "key")
    assert {o["id"] for o in capabilities["asr_provider"]["options"]} == {"stub", "paraformer"}
    assert {o["id"] for o in capabilities["pdf_strategy"]["options"]} == {
        "mineru_then_pypdf",
        "pypdf",
        "mineru",
    }
    assert {o["id"] for o in capabilities["search_provider"]["options"]} == {
        "auto",
        "stub",
        "bocha",
    }
    assert [task["id"] for task in catalog["tasks"]] == ["intent", "generate", "conflict"]


# ---- 写穿：即时生效（不重启）----


def test_capability_switch_takes_effect_without_restart():
    """检索策略经设置页改成 vector 后，紧接着的检索端点就按新策略跑（同进程，无重启）。"""
    assert _get()["capabilities"]  # 读一次，确认起点是引导默认
    view = _put({"retrieval_strategy": "vector"})
    switched = _by_name(view["capabilities"], "key")["retrieval_strategy"]
    assert switched["value"] == "vector"
    assert switched["value_label"] == "纯向量"
    assert switched["source"] == "设置页"

    # 既有端点当场用新策略：这是「写穿」在 HTTP 上的证据
    retrieved = client.post(
        "/api/v1/knowledge/retrieve", json={"intent": {"topic": "导数"}, "k": 1}
    )
    assert retrieved.status_code == 200, retrieved.text
    assert retrieved.json()["strategy"] == "vector"

    _put({"retrieval_strategy": "vector_graph"})
    back = client.post("/api/v1/knowledge/retrieve", json={"intent": {"topic": "导数"}, "k": 1})
    assert back.json()["strategy"] == "vector_graph"


def test_capability_switch_changes_the_factory_immediately():
    """语音转写 / PDF 解析 / 网络搜索三档：写库后工厂当场换实现（lru_cache 已失效）。"""
    assert type(get_pdf_parser()).__name__ == "FallbackPdfParser"
    assert type(get_transcriber()).__name__ == "StubTranscriber"

    _put({"pdf_strategy": "pypdf"})
    assert type(get_pdf_parser()).__name__ == "PypdfParser"

    _put({"asr_provider": "paraformer", "dashscope_api_key": "sk-dashscope-1234"})
    assert type(get_transcriber()).__name__ == "ParaformerTranscriber"

    _put({"search_provider": "bocha", "bocha_api_key": "sk-bocha-1234"})
    assert type(get_search()).__name__ == "BochaSearch"


def test_provider_switch_with_key_becomes_ready_without_restart():
    """目录选择 + 粘贴 Key：从 stub 模式切到真实服务，读回来就是新供应商且已就绪。"""
    assert _get()["provider"]["value"] == "stub"
    view = _put({"llm_provider": "deepseek", "deepseek_api_key": PLAINTEXT})

    assert view["provider"]["value"] == "deepseek"
    assert view["provider"]["label"] == "DeepSeek"
    assert view["provider"]["key_field"] == "deepseek_api_key"
    assert view["provider"]["source"] == "设置页"
    assert view["provider"]["ready"] is True
    assert view["provider"]["reason"] == ""

    # 工厂当场按新配置构造（不重启）：地址与模型取方言预设，Key 取刚粘贴的那把
    llm = get_llm()
    assert isinstance(llm, OpenAICompatProvider)
    assert llm.base_url == "https://api.deepseek.com"
    assert llm.model == "deepseek-chat"
    assert llm.api_key == PLAINTEXT


def test_stored_settings_survive_a_restart():
    """配置库优先于 .env 引导默认：重启（进程内配置回到引导默认 + 启动钩子重放）后仍然生效。"""
    _put({"asr_provider": "paraformer", "dashscope_api_key": "sk-dashscope-9f8a"})

    # 模拟新进程：进程内配置回到引导默认，缓存清掉
    settings.asr_provider = "stub"
    get_transcriber.cache_clear()

    with TestClient(app):  # 真实启动路径：init_db() + 设置启动钩子
        view = client.get("/api/v1/settings").json()

    asr = _by_name(view["capabilities"], "key")["asr_provider"]
    assert asr["value"] == "paraformer"
    assert asr["source"] == "设置页"
    assert asr["ready"] is True


# ---- 自定义 OpenAI 兼容服务 ----


def test_custom_openai_compatible_service_can_be_configured():
    """目录之外的服务商：填 base_url + 模型 ID + Key 即可用，当场生效。"""
    view = _put(
        {
            "llm_provider": "custom",
            "llm_base_url": "https://my-llm.example.com/v1",
            "llm_model": "my-model",
            "llm_api_key": "sk-custom-1234",
        }
    )

    assert view["provider"]["value"] == "custom"
    assert view["provider"]["label"] == "自定义 OpenAI 兼容服务"
    assert view["provider"]["ready"] is True
    items = _by_name(view["items"])
    assert items["llm_base_url"]["effective"] == "https://my-llm.example.com/v1"
    assert items["llm_model"]["effective"] == "my-model"

    llm = get_llm()
    assert isinstance(llm, OpenAICompatProvider)
    assert llm.base_url == "https://my-llm.example.com/v1"
    assert llm.model == "my-model"
    assert llm.api_key == "sk-custom-1234"


def test_custom_service_without_key_reports_why_it_is_not_ready():
    """缺 Key 不是错误响应：写入照样成功，但读回来明确说「还不能用」与原因。"""
    view = _put(
        {
            "llm_provider": "custom",
            "llm_base_url": "https://my-llm.example.com/v1",
            "llm_model": "my-model",
        }
    )

    assert view["provider"]["ready"] is False
    assert "LLM_API_KEY" in view["provider"]["reason"]


# ---- 任务级模型 ----


def test_task_models_fall_back_to_the_global_default():
    """任务级模型逐任务可选；没设的任务回落全局默认，页面能看到「实际用的模型」与来源。"""
    _put(
        {
            "llm_provider": "dashscope",
            "llm_model": "qwen-plus",
            "dashscope_api_key": "sk-dashscope-1234",
        }
    )
    tasks = _by_name(_get()["tasks"], "task")
    for task in ("intent", "generate", "conflict"):
        assert tasks[task]["model"] == "qwen-plus"
        assert tasks[task]["source"] == "全局默认"
        assert tasks[task]["selected"] == ""

    view = _put({"task_model_generate": "qwen-max"})
    tasks = _by_name(view["tasks"], "task")
    assert tasks["generate"]["label"] == "生成"
    assert tasks["generate"]["selected"] == "qwen-max"
    assert tasks["generate"]["model"] == "qwen-max"
    assert tasks["generate"]["source"] == "任务级"
    assert tasks["intent"]["model"] == "qwen-plus"  # 其它任务不受影响
    assert tasks["intent"]["source"] == "全局默认"
    assert tasks["conflict"]["model"] == "qwen-plus"


class _RecordingLLM(LLMProvider):
    """记录每次对话带上的模型档位（`None` = 没带，即由 provider 自身承担全局默认）。"""

    name = "recording"

    def __init__(self) -> None:
        self.models: list[str | None] = []

    async def chat(self, messages, **kwargs) -> ChatResult:
        self.models.append(kwargs.get("model"))
        return ChatResult(content="{}")


async def test_task_level_models_reach_each_call_site(monkeypatch):
    """任务级模型不只是页面上好看：意图分析 / 生成 / 冲突比对三条链各自带上自己的档位。"""
    recorder = _RecordingLLM()
    monkeypatch.setitem(LLM_BUILDERS, "custom", lambda cfg: recorder)
    _put(
        {
            "llm_provider": "custom",
            "llm_base_url": "https://my-llm.example.com/v1",
            "llm_model": "global-model",
            "llm_api_key": "sk-custom-1234",
            "task_model_intent": "intent-model",
            "task_model_generate": "generate-model",
            "task_model_conflict": "conflict-model",
        }
    )

    await analyze_intent("讲一次函数")
    await generate_outline({"topic": "一次函数"}, "知识内容")
    await compare_content("旧描述", "新描述")

    assert recorder.models == ["intent-model", "generate-model", "conflict-model"]

    # 清掉任务档位后回落全局默认：不再往调用里塞模型档位（由 provider 自身的全局默认承担）
    _put({"task_model_intent": "", "task_model_generate": "", "task_model_conflict": ""})
    recorder.models.clear()
    await analyze_intent("讲一次函数")
    assert recorder.models == [None]
    assert _by_name(_get()["tasks"], "task")["intent"]["source"] == "全局默认"


# ---- 无效配置：明确错误码与信息 ----


@pytest.mark.parametrize(
    ("payload", "code", "hint"),
    [
        ({"llm_provider": "openai-x"}, "unknown_provider", "可选：stub"),
        ({"llm_provider": "dashscope", "llm_model": "gpt-4o"}, "unknown_model", "qwen-plus"),
        ({"task_model_generate": "没有这个模型"}, "unknown_model", "自定义 OpenAI 兼容服务"),
        ({"asr_provider": "whisper"}, "unknown_capability_impl", "paraformer"),
        ({"llm_base_url": "example.com/v1"}, "invalid_base_url", "http(s)"),
        ({"embedding_base_url": "ftp://example.com/v1"}, "invalid_base_url", "http(s)"),
    ],
)
def test_invalid_config_returns_explicit_error_code(payload, code, hint):
    """未知供应商 / 未知模型 / 未实现的实现 / 格式不对的 base_url：400 + 稳定码 + 可读信息。"""
    response = client.put("/api/v1/settings", json=payload)

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code
    assert detail["field"] in payload
    assert hint in detail["message"]
    assert _stored_rows() == {}  # 无效写入一行都不落


def test_partial_write_keeps_the_other_items():
    """界面一次只改一件事（一次 PUT 只带一个字段）：没带的字段一律不动，Key 也不会被抹掉。"""
    _put(
        {
            "llm_provider": "deepseek",
            "deepseek_api_key": PLAINTEXT,
            "task_model_generate": "deepseek-reasoner",
        }
    )
    view = _put({"retrieval_strategy": "vector"})

    assert _stored_rows() == {
        "llm_provider": "deepseek",
        "deepseek_api_key": PLAINTEXT,
        "task_model_generate": "deepseek-reasoner",
        "retrieval_strategy": "vector",
    }
    assert view["provider"]["value"] == "deepseek"
    key = _by_name(view["keys"], "field")["deepseek_api_key"]
    assert key["configured"] is True and key["masked"] == f"••••{MASKED_TAIL}"


def test_invalid_write_leaves_earlier_settings_untouched():
    """无效写入不改变任何既有设置：库内还是上一次的成功写入。"""
    _put({"retrieval_strategy": "vector"})

    response = client.put("/api/v1/settings", json={"pdf_strategy": "不存在的策略"})
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "unknown_capability_impl"

    assert _stored_rows() == {"retrieval_strategy": "vector"}
    assert _by_name(_get()["capabilities"], "key")["retrieval_strategy"]["value"] == "vector"


# ---- 掩码：任何响应都不回显明文 ----


def test_key_is_masked_in_every_response():
    """写入接收明文，回读只有掩码；任何响应体里都不得出现明文 Key。"""
    response = client.put("/api/v1/settings", json={"deepseek_api_key": PLAINTEXT})
    assert response.status_code == 200, response.text
    assert PLAINTEXT not in response.text  # 写入响应本身也不回显

    read = client.get("/api/v1/settings")
    assert PLAINTEXT not in read.text
    key = _by_name(read.json()["keys"], "field")["deepseek_api_key"]
    assert key["configured"] is True
    assert key["masked"] == f"••••{MASKED_TAIL}"
    assert key["source"] == "设置页"
    # 库内保存的是原文（要拿去调用），掩码只发生在回读
    assert _stored_rows()["deepseek_api_key"] == PLAINTEXT


def test_short_key_is_masked_completely():
    """短 Key 连尾部都不给：掩码不能变成「泄露一位也算泄露」的借口。"""
    view = _put({"bocha_api_key": "sk-12"})
    key = _by_name(view["keys"], "field")["bocha_api_key"]
    assert key["masked"] == "••••"
    assert "sk-12" not in json.dumps(view, ensure_ascii=False)


def test_empty_value_clears_the_item_back_to_bootstrap():
    """传空字符串 = 清除该项设置（回落 .env 引导默认），只影响这一项。"""
    _put({"deepseek_api_key": PLAINTEXT, "retrieval_strategy": "vector"})

    view = _put({"deepseek_api_key": ""})
    key = _by_name(view["keys"], "field")["deepseek_api_key"]
    assert key["configured"] is False
    assert key["masked"] == ""
    assert key["source"] == "引导默认"
    assert _stored_rows() == {"retrieval_strategy": "vector"}


# ---- 契约守卫 ----


def test_settings_operations_all_declare_a_response_model():
    """票 04 指出 16 个操作只有 6 个带 response_model（前端生成类型退化成 unknown）；本票不许再缺。"""
    schema = app.openapi()
    checked = 0
    for path, item in schema["paths"].items():
        if "/settings" not in path:
            continue
        for method, operation in item.items():
            ok = operation.get("responses", {}).get("200", {})
            media = ok.get("content", {}).get("application/json", {})
            assert media.get("schema", {}).get("$ref"), f"{method.upper()} {path} 缺 response_model"
            checked += 1
    assert checked == 3  # 读设置 / 写设置 / 可选目录


def test_update_body_covers_every_managed_setting():
    """请求体字段与设置项登记表不许走散（少一个字段 = 那一项永远改不了）。"""
    from app.api.v1.settings import SettingsUpdate

    assert set(SettingsUpdate.model_fields) == set(FIELDS)


def test_every_managed_setting_exists_on_the_settings_object():
    """设置项必须真的落在 Settings 上：写穿靠 setattr 同步，字段名写错会当场报错而不是静默失效。"""
    assert set(FIELDS) <= set(Settings.model_fields)
