"""设置 API（票 13）：读生效配置（Key 掩码）/ 写设置（即时生效）/ 可选目录，全部经 HTTP 缝。

三组断言口径：

1. **响应与数据变迁**：读回的值、来源（设置页 / 引导默认）、库内 `app_settings` 行；
2. **写穿即时生效**：写完立刻用别的端点或能力工厂观测到新实现（同一进程，不重启）——
   票 03 遗留的「设置写穿即时生效」就落在这里；
3. **任务级模型**：页面上「该任务实际用的模型」的可见值 + 它真的进了那条链路的每次对话。

隔离：每个用例前后清空设置库并回落引导默认——共享临时库里不留设置行，避免污染其它用例
（设置项会改进程内配置，漏清就会串到别的用例）。落盘隔离沿用 conftest。
引导默认另行**控制**成「本机没有 `.env`」的代码默认（`_isolated_bootstrap_defaults`）：
配置库优先于 `.env` 引导默认，所以有真 Key 的开发机上「设置库为空」并不等于「Key 都没配」，
凡断言「未配置 / 引导默认」的用例都必须先把引导默认钉住，才与本机环境无关。
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings, settings
from app.core import settings_store
from app.core.asr.factory import get_transcriber
from app.core.catalog import FIELDS, MANAGED_FIELDS
from app.core.errors import ProviderNotConfigured
from app.core.intent import analyze_intent
from app.core.llm.base import ChatResult, LLMProvider
from app.core.llm.factory import LLM_BUILDERS, get_llm
from app.core.llm.providers.openai_compat import OpenAICompatProvider
from app.core.parser.factory import get_pdf_parser
from app.core.search.factory import get_search
from app.core.settings_store import apply_stored_settings, clear_stored_settings
from app.db import SessionLocal, init_db
from app.db.models import AppSetting
from app.generate.outline import generate_outline
from app.knowledge.conflict import compare_content
from app.main import app

client = TestClient(app)
init_db()  # 幂等：设置表在临时库里就位

PLAINTEXT = "sk-live-2f7d9a41"
MASKED_TAIL = "9a41"

# 受控的引导默认：`Settings` 的代码默认值（无 `.env`、无环境变量）。
# `settings_store` 在导入时把本机 `.env` 存成 `_BOOTSTRAP` 快照，那份快照不是本文件要断言的
# 「引导默认」——有真 Key 的开发机上它带着真 Key（产品行为正确，`test_stored_settings_survive_a_restart`
# 覆盖了「配置库优先于 `.env`」）。
_BOOTSTRAP_WITHOUT_DEVELOPER_ENV = {
    name: str(Settings.model_fields[name].default or "") for name in MANAGED_FIELDS
}


@pytest.fixture(autouse=True)
def _isolated_bootstrap_defaults(_default_fake_llm, monkeypatch):
    """把引导默认换成「本机没有 `.env`」的代码默认，用例才对开发者环境密封。

    依赖 `_default_fake_llm` 保证在其之后运行：设置页测试要断言的是**未配置**状态，
    故再把对话供应商复位为空（假 LLM 替身留给需要它的测试文件）。
    换掉的是引导快照本身（`apply_stored_settings()` 读它回落未写过的项），进程内配置随之同步；
    用例结束恢复真值快照并再重放一次，不把受控值留给后面的测试文件。
    """
    monkeypatch.setattr(settings_store, "_BOOTSTRAP", dict(_BOOTSTRAP_WITHOUT_DEVELOPER_ENV))
    apply_stored_settings()
    from app.core.llm.factory import get_llm

    monkeypatch.setattr(settings, "llm_provider", "")
    get_llm.cache_clear()
    yield
    monkeypatch.undo()  # 恢复本机真值快照
    apply_stored_settings()  # 让进程内配置也跟着回落


@pytest.fixture(autouse=True)
def _clean_settings_store(_isolated_bootstrap_defaults):
    """用例前后都清空设置库与供应商实例表并回落引导默认（受控的引导默认，见上个夹具）。"""
    clear_stored_settings()
    _clear_provider_instances()
    yield
    _clear_provider_instances()
    clear_stored_settings()  # 实例先删：清理存量指针的兜底才有东西可清


@pytest.fixture(autouse=True)
def _offline_model_fetch(monkeypatch):
    """模型拉取在测试里钉死为本地假实现：不碰网络，返回固定清单。"""
    from app.core.llm import provider_instances

    monkeypatch.setattr(
        provider_instances,
        "fetch_model_ids",
        lambda instance: ["fake-model-a", "fake-model-b"],
    )


def _clear_provider_instances() -> None:
    """供应商实例与模型清单是设置页状态的一部分：用例间不共享（Key 与默认指针都不许串）。"""
    from sqlalchemy import delete

    from app.core.llm.provider_instances import clear_instance_cache
    from app.db.models import LLMProviderInstance, ProviderModel

    with SessionLocal() as db:
        db.execute(delete(ProviderModel))
        db.execute(delete(LLMProviderInstance))
        db.commit()
    clear_instance_cache()


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
    """没在设置页改过时，读回来的一切都是引导默认（受控为「本机无 .env」），Key 一个都没配。"""
    view = _get()

    # 未配置供应商：诚实的状态（不再是假数据兜底模式）
    assert view["provider"]["value"] == ""
    assert view["provider"]["label"] == "未配置"
    assert view["provider"]["source"] == "引导默认"
    assert view["provider"]["ready"] is False
    assert view["provider"]["reason"]
    assert view["provider_instances"] == []
    assert set(_by_name(view["items"])) == {
        "llm_base_url",
        "llm_model",
        "llm_vision_model",
        "embedding_base_url",
        "embedding_model",
    }
    assert all(item["source"] == "引导默认" for item in view["items"])
    # 引导默认已被夹具钉成无 Key 的代码默认：开发者 `.env` 里的真 Key 不该影响这条断言
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
    assert set(providers) == {
        "qwen",
        "deepseek",
        "moonshot",
        "zhipu",
        "minimax",
        "ark",
        "siliconflow",
        "custom",
    }
    assert providers["deepseek"]["key_field"] == "deepseek_api_key"
    assert providers["deepseek"]["chat_models"] == ["deepseek-flash", "deepseek-v4-pro"]
    assert providers["qwen"]["base_url"] == "https://maas.qianwenaiapi.com/compatible-mode/v1"
    assert providers["qwen"]["label"] == "千问（Qwen）"  # 面向教师叫千问
    assert providers["moonshot"]["key_field"] == "moonshot_api_key"
    assert providers["ark"]["accepts_any_model"] is True  # 豆包的 ep- 接入点放行
    assert providers["custom"]["accepts_any_model"] is True

    capabilities = _by_name(catalog["capabilities"], "key")
    assert {o["id"] for o in capabilities["asr_provider"]["options"]} == {"auto", "paraformer"}
    assert {o["id"] for o in capabilities["pdf_strategy"]["options"]} == {
        "mineru_then_pypdf",
        "pypdf",
        "mineru",
    }
    assert {o["id"] for o in capabilities["search_provider"]["options"]} == {
        "auto",
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
    # 未配置语音转写：抛 ProviderNotConfigured（产品没有假转写兜底）
    with pytest.raises(ProviderNotConfigured):
        get_transcriber()

    _put({"pdf_strategy": "pypdf"})
    assert type(get_pdf_parser()).__name__ == "PypdfParser"

    _put({"asr_provider": "paraformer", "asr_api_key": "sk-bailian-1234"})
    assert type(get_transcriber()).__name__ == "ParaformerTranscriber"

    _put({"search_provider": "bocha", "bocha_api_key": "sk-bocha-1234"})
    assert type(get_search()).__name__ == "BochaSearch"


def test_provider_switch_with_key_becomes_ready_without_restart():
    """目录选择 + 粘贴 Key：从未配置切到真实服务，读回来就是新供应商且已就绪。"""
    assert _get()["provider"]["value"] == ""
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
    assert llm.model == "deepseek-flash"
    assert llm.api_key == PLAINTEXT


def test_stored_settings_survive_a_restart():
    """配置库优先于引导默认：重启（进程内配置回到引导默认 + 启动钩子重放）后仍然是设置页的值。"""
    _put({"asr_provider": "paraformer", "asr_api_key": "sk-bailian-9f8a"})

    # 模拟新进程：进程内配置回到引导默认，缓存清掉
    settings.asr_provider = ""
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
            "llm_provider": "qwen",
            "llm_model": "qwen-plus",
            "qwen_api_key": "sk-qwen-1234",
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
        ({"llm_provider": "openai-x"}, "unknown_provider", "可选：qwen"),
        ({"llm_provider": "qwen", "llm_model": "gpt-4o"}, "unknown_model", "qwen-plus"),
        ({"llm_provider": "deepseek", "task_model_generate": "gpt-4o"}, "unknown_model", "deepseek-flash"),
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
            "task_model_generate": "deepseek-v4-pro",
        }
    )
    view = _put({"retrieval_strategy": "vector"})

    assert _stored_rows() == {
        "llm_provider": "deepseek",
        "deepseek_api_key": PLAINTEXT,
        "task_model_generate": "deepseek-v4-pro",
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
    """传空字符串 = 清除该项设置（回落引导默认），只影响这一项。"""
    # 清除后回落的是受控引导默认（无 `.env`），所以这里能断言「未配置」而非开发者那把 Key
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
    assert checked == 7  # 读设置 / 写设置 / 可选目录 + 供应商实例的增 / 改 / 删 / 刷新模型

def test_update_body_covers_every_managed_setting():
    """请求体字段与设置项登记表不许走散（少一个字段 = 那一项永远改不了）。"""
    from app.api.v1.settings import SettingsUpdate

    assert set(SettingsUpdate.model_fields) == set(FIELDS)


def test_every_managed_setting_exists_on_the_settings_object():
    """设置项必须真的落在 Settings 上：写穿靠 setattr 同步，字段名写错会当场报错而不是静默失效。"""
    assert set(FIELDS) <= set(Settings.model_fields)


# ---- 供应商实例（多供应商并存）----


def _add_provider(payload: dict) -> dict:
    response = client.post("/api/v1/settings/providers", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_add_provider_first_becomes_default_and_is_ready():
    """添加的第一家自动成为全局默认；回读带掩码与就绪状态（明文一个字节都不回显）。"""
    instance = _add_provider({"provider": "deepseek", "api_key": PLAINTEXT})
    assert instance["provider"] == "deepseek"
    assert instance["label"] == "DeepSeek"
    assert instance["is_default"] is True
    assert instance["ready"] is True
    assert instance["key_configured"] is True
    assert instance["key_masked"] == f"••••{MASKED_TAIL}"

    view = _get()
    assert len(view["provider_instances"]) == 1
    assert view["provider"]["label"] == "DeepSeek"  # legacy 单供应商视图由默认实例派生


def test_custom_service_lives_in_the_provider_list():
    """自定义 OpenAI 兼容服务也是「添加供应商」里的一家：同一列表、同一入口、可设为默认。"""
    first = _add_provider({"provider": "deepseek", "api_key": PLAINTEXT})
    second = _add_provider(
        {
            "provider": "custom",
            "label": "我的中转",
            "base_url": "https://example.com/v1",
            "model": "my-model",
            "api_key": PLAINTEXT,
        }
    )
    assert second["is_default"] is False
    assert second["models"] == ["fake-model-a", "fake-model-b"]  # 添加时同步拉取并缓存

    patched = client.patch(
        f"/api/v1/settings/providers/{second['id']}", json={"make_default": True}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_default"] is True

    # 全局默认模型由「全局默认」卡显式选：指默认实例 + 填模型，实际生效值就是它
    _put({"default_provider_instance": second["id"], "llm_model": "my-model"})
    items = _by_name(_get()["items"])
    assert items["llm_model"]["effective"] == "my-model"

    # 删掉默认的那家：默认回落到剩下的第一家，指针不悬空
    deleted = client.delete(f"/api/v1/settings/providers/{second['id']}")
    assert deleted.status_code == 200, deleted.text
    instances = _by_name(deleted.json()["provider_instances"], "id")
    assert instances[first["id"]]["is_default"] is True


def test_task_can_pick_provider_and_model_independently():
    """任务级 = 供应商实例 + 模型：不同任务可以各用一家（意图用 DeepSeek，生成用 Kimi）。"""
    deepseek = _add_provider({"provider": "deepseek", "api_key": PLAINTEXT})
    moonshot = _add_provider({"provider": "moonshot", "api_key": PLAINTEXT})

    view = _put(
        {
            "task_provider_intent": deepseek["id"],
            "task_model_intent": "deepseek-v4-pro",
            "task_provider_generate": moonshot["id"],
        }
    )
    tasks = _by_name(view["tasks"], "task")
    assert tasks["intent"]["model"] == "deepseek-v4-pro"
    assert tasks["intent"]["provider_label"] == "DeepSeek"
    assert tasks["intent"]["source"] == "任务级"
    # 指了实例没选模型：用该实例方言的默认模型（仍是任务级口径）
    assert tasks["generate"]["model"] == "kimi-latest"
    assert tasks["generate"]["provider_label"] == "Kimi（月之暗面）"
    # 冲突比对没指：跟随全局默认
    assert tasks["conflict"]["source"] == "全局默认"


def test_add_provider_validation_errors_are_explicit():
    """实例字段的目录校验：未知供应商 / 缺地址 / 缺 Key / 目录外模型，都给稳定 code。"""
    cases = [
        ({"provider": "openai"}, "unknown_provider"),
        ({"provider": "custom", "model": "my-model"}, "missing_base_url"),
        ({"provider": "custom", "base_url": "https://example.com/v1"}, "missing_key"),
        ({"provider": "deepseek"}, "missing_key"),
        ({"provider": "deepseek", "api_key": PLAINTEXT, "model": "gpt-4o"}, "unknown_model"),
    ]
    for payload, code in cases:
        response = client.post("/api/v1/settings/providers", json=payload)
        assert response.status_code == 400, f"{code}: {response.text}"
        assert response.json()["detail"]["code"] == code


def test_task_provider_pointer_must_reference_an_added_instance():
    """任务指向未添加的实例 id：400 unknown_provider_instance，库内一行不动。"""
    before = _stored_rows()
    response = client.put("/api/v1/settings", json={"task_provider_generate": "no-such-id"})
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "unknown_provider_instance"
    assert _stored_rows() == before


def test_refresh_models_endpoint_replaces_the_cache():
    """刷新模型清单：整表替换缓存，返回更新后的实例视图。"""
    instance = _add_provider({"provider": "deepseek", "api_key": PLAINTEXT})
    assert instance["models"] == ["fake-model-a", "fake-model-b"]

    from app.core.llm import provider_instances

    original = provider_instances.fetch_model_ids
    try:
        provider_instances.fetch_model_ids = lambda _row: ["brand-new-model"]
        refreshed = client.post(f"/api/v1/settings/providers/{instance['id']}/refresh-models")
    finally:
        provider_instances.fetch_model_ids = original
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["models"] == ["brand-new-model"]
    assert refreshed.json()["models_error"] == ""


def test_fetch_failure_keeps_old_models_and_allows_manual_model():
    """拉取失败：不落半行、原因可见；该家的模型走「手动填写」仍可被任务采用。"""
    from app.core.llm import provider_instances

    original = provider_instances.fetch_model_ids
    try:

        def _boom(_row) -> list[str]:
            raise RuntimeError("网络不通（测试替身）")

        provider_instances.fetch_model_ids = _boom
        instance = _add_provider({"provider": "moonshot", "api_key": PLAINTEXT})
    finally:
        provider_instances.fetch_model_ids = original

    assert instance["models"] == []
    assert "网络不通" in instance["models_error"]

    # 手动填模型 ID（实例路径不做硬编码目录校验）：任务可以照常采用
    view = _put({"task_provider_generate": instance["id"], "task_model_generate": "hand-typed-model"})
    tasks = _by_name(view["tasks"], "task")
    assert tasks["generate"]["model"] == "hand-typed-model"
    assert tasks["generate"]["source"] == "任务级"


def test_global_model_readback_matches_all_task_calls():
    from app.core.llm.task_routing import get_llm_for

    instance = _add_provider({"provider": "deepseek", "api_key": PLAINTEXT})
    view = _put({"default_provider_instance": instance["id"], "llm_model": "explicit-model"})
    assert {row["model"] for row in view["tasks"]} == {"explicit-model"}
    assert {get_llm_for(task).model for task in ("intent", "generate", "conflict")} == {"explicit-model"}


def test_instance_update_invalidates_default_factory():
    instance = _add_provider({"provider": "custom", "api_key": PLAINTEXT,
                              "base_url": "https://old.example/v1", "model": "my-model"})
    assert get_llm().base_url == "https://old.example/v1"
    response = client.patch(f"/api/v1/settings/providers/{instance['id']}",
                            json={"base_url": "https://new.example/v1"})
    assert response.status_code == 200, response.text
    assert get_llm().base_url == "https://new.example/v1"


def test_instance_model_default_is_reported_consistently():
    instance = _add_provider({"provider": "custom", "api_key": PLAINTEXT,
                              "base_url": "https://example.com/v1", "model": "my-model"})
    assert get_llm().model == "my-model"
    assert _by_name(_get()["items"])["llm_model"]["effective"] == "my-model"
    assert instance["ready"]


def test_instance_key_can_be_cleared_and_chat_returns_503():
    instance = _add_provider({"provider": "deepseek", "api_key": PLAINTEXT})
    get_llm()  # 先构造旧能力，清空必须使它失效
    response = client.patch(f"/api/v1/settings/providers/{instance['id']}", json={"api_key": ""})
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is False
    assert response.json()["key_masked"] == ""
    turn = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "备课"}]})
    assert turn.status_code == 503, turn.text
    assert turn.json()["detail"]["code"] == "provider_not_configured"


async def test_custom_model_capabilities_survive_refresh_and_control_requests(tmp_path):
    import httpx

    from app.core.llm.base import ChatMessage
    from app.core.llm.provider_instances import provider_of_instance
    from app.db.models import ProviderModel

    instance = _add_provider({"provider": "custom", "api_key": PLAINTEXT,
                              "base_url": "https://offline.example/v1", "model": "fake-model-a"})
    initial = {row["model_id"]: row for row in instance["model_details"]}
    assert initial["fake-model-a"]["capabilities"] == []
    assert initial["fake-model-a"]["source"] == "unknown"
    response = client.patch(f"/api/v1/settings/providers/{instance['id']}", json={
        "model_capabilities": {"fake-model-a": ["text", "vision"], "fake-model-b": ["embedding"]}})
    assert response.status_code == 200, response.text
    refreshed = client.post(f"/api/v1/settings/providers/{instance['id']}/refresh-models")
    details = {row["model_id"]: row for row in refreshed.json()["model_details"]}
    assert details["fake-model-a"]["capabilities"] == ["text", "vision"]
    assert details["fake-model-b"]["source"] == "manual"
    with SessionLocal() as db:
        row = db.query(ProviderModel).filter_by(instance_id=instance["id"], model_id="fake-model-b").one()
        assert row.capabilities == ["embedding"]
    provider = provider_of_instance(instance["id"], "fake-model-a")
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "真实协议响应（离线替身）"}}]})
    provider._transport = httpx.MockTransport(handle)
    image = tmp_path / "image.png"
    image.write_bytes(b"offline-image")
    await provider.vision(str(image), "识别图片")
    assert requests[0]["model"] == "fake-model-a"
    with pytest.raises(ProviderNotConfigured):
        await provider.chat([ChatMessage("user", "备课")], model="fake-model-b")
    assert len(requests) == 1  # 不向对话接口发送向量化模型
    cleared = client.patch(f"/api/v1/settings/providers/{instance['id']}",
                           json={"model_capabilities": {"fake-model-a": None}})
    details = {row["model_id"]: row for row in cleared.json()["model_details"]}
    assert details["fake-model-a"]["source"] == "unknown"


def test_invalid_model_capability_does_not_mutate_instance():
    instance = _add_provider({"provider": "deepseek", "api_key": PLAINTEXT})
    response = client.patch(f"/api/v1/settings/providers/{instance['id']}",
                            json={"label": "不得落库", "model_capabilities": {"m": ["imaginary"]}})
    assert response.status_code == 422
    assert _get()["provider_instances"][0]["label"] == "DeepSeek"


def test_global_vision_override_is_used_by_default_instance():
    instance = _add_provider({"provider": "deepseek", "api_key": PLAINTEXT})
    _put({"llm_vision_model": "deepseek-flash"})
    assert get_llm().vision_model == "deepseek-flash"
    assert instance["id"]


@pytest.mark.parametrize("provider", ["deepseek", "custom"])
def test_explicit_llm_without_key_has_configured_error(monkeypatch, provider):
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "llm_base_url", "https://offline.example/v1")
    monkeypatch.setattr(settings, "llm_model", "offline-model")
    get_llm.cache_clear()
    response = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "备课"}]})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_not_configured"


def test_explicit_search_without_key_returns_503():
    _put({"search_provider": "bocha"})
    response = client.post("/api/v1/knowledge/web-search", json={"query": "教学资料", "k": 1})
    assert response.status_code == 503


def test_explicit_transcription_without_key_rejects_upload_before_saving():
    _put({"asr_provider": "paraformer"})
    before = client.get("/api/v1/documents").json()
    response = client.post("/api/v1/documents/upload", files={"file": ("offline.wav", b"RIFF", "audio/wav")})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_not_configured"
    assert client.get("/api/v1/documents").json() == before


async def test_text_model_cannot_be_used_for_visual_calls(tmp_path):
    import httpx
    instance = _add_provider({"provider": "qwen", "api_key": PLAINTEXT})
    _put({"llm_vision_model": "qwen-plus"})  # 实例模型池允许手动 ID，运行时仍校验能力
    provider = get_llm()
    def no_request(_):
        raise AssertionError("纯文本模型不得调用视觉服务")
    provider._transport = httpx.MockTransport(no_request)
    with pytest.raises(ProviderNotConfigured, match="vision"):
        await provider.vision(str(tmp_path / "missing.png"), "识别图片")
    assert instance["id"]


def test_embedding_only_model_is_not_ready_for_chat():
    instance = _add_provider({"provider": "custom", "api_key": PLAINTEXT,
                              "base_url": "https://offline.example/v1", "model": "fake-model-a"})
    response = client.patch(f"/api/v1/settings/providers/{instance['id']}",
                            json={"model_capabilities": {"fake-model-a": ["embedding"]}})
    assert response.status_code == 200
    assert response.json()["ready"] is False
    with pytest.raises(ProviderNotConfigured):
        get_llm()


def test_model_capability_migration_preserves_legacy_rows(tmp_path):
    from sqlalchemy import create_engine

    from app.db.engine import _ensure_sqlite_columns

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE llm_provider_instances (id TEXT, api_key TEXT, models_error TEXT)")
        conn.exec_driver_sql("INSERT INTO llm_provider_instances VALUES ('old', 'offline-secret', '')")
        conn.exec_driver_sql("CREATE TABLE provider_models (model_id TEXT)")
        conn.exec_driver_sql("INSERT INTO provider_models VALUES ('old-model')")
    _ensure_sqlite_columns(engine)
    _ensure_sqlite_columns(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT api_key, model_capabilities FROM llm_provider_instances").one() == ("offline-secret", "{}")
        assert conn.exec_driver_sql("SELECT model_id, capabilities FROM provider_models").one() == ("old-model", "[]")
    engine.dispose()

