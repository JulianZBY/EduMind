"""声明式供应商配置（`providers.json`）：校验、并入目录、Key 走环境变量、坏配置不拖垮应用。

只断言「配置写了什么就生效什么」这条接缝：文件解析与并入是对外行为，
不替换任何内部函数（工厂 / 目录都是真实实现，Key 用假值、不打网络）。
"""

import json

import pytest

from app.core import provider_config
from app.core.catalog import PROVIDERS, validate_patch
from app.core.dialects import DIALECTS
from app.core.embedding.factory import EMBEDDING_BUILDERS
from app.core.errors import ProviderNotConfigured
from app.core.llm.factory import LLM_BUILDERS, get_llm

ENTRY = {
    "id": "my-gateway",
    "label": "我的中转",
    "base_url": "https://api.example.edu/v1",
    "api_key_env": "MY_GATEWAY_API_KEY",
    "chat_models": ["edu-chat-32b", "edu-chat-8b"],
    "vision_models": ["edu-vl-8b"],
    "note": "公司中转",
}


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch):
    """不读开发机上的 providers.json；用例并入的供应商在用例结束时从目录里摘掉。"""
    monkeypatch.setenv(provider_config.ENV_VAR, "")
    monkeypatch.delenv(ENTRY["api_key_env"], raising=False)
    provider_config.reset_for_tests()
    snapshots = [
        (table, dict(table)) for table in (DIALECTS, PROVIDERS, LLM_BUILDERS, EMBEDDING_BUILDERS)
    ]
    get_llm.cache_clear()
    yield
    for table, before in snapshots:
        table.clear()
        table.update(before)
    get_llm.cache_clear()
    provider_config.reset_for_tests()


def _write(tmp_path, payload) -> str:
    path = tmp_path / "providers.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ---- 解析与校验 ----


def test_load_normalizes_a_valid_entry(tmp_path):
    """合法条目：清单里的第一个模型成为默认档；缺省值补齐。"""
    from pathlib import Path

    entries = provider_config.load_entries(Path(_write(tmp_path, [ENTRY])))

    assert len(entries) == 1
    entry = entries[0]
    assert entry["id"] == "my-gateway"
    assert entry["chat_model"] == "edu-chat-32b"  # 缺省取 chat_models[0]
    assert entry["vision_model"] == "edu-vl-8b"
    assert entry["accepts_any_model"] is False  # 声明了清单就不再放行任意模型


def test_load_without_model_lists_accepts_any_model(tmp_path):
    """没声明模型清单 = 放行任意模型 ID（服务商给什么用什么）。"""
    from pathlib import Path

    entries = provider_config.load_entries(
        Path(
            _write(
                tmp_path, [{"id": "gateway", "label": "网关", "base_url": "https://a.example/v1"}]
            )
        )
    )

    assert entries[0]["accepts_any_model"] is True
    assert entries[0]["chat_models"] == []


def test_load_accepts_the_providers_wrapper(tmp_path):
    """顶层既可以是数组，也可以是 {"providers": [...]}。"""
    from pathlib import Path

    entries = provider_config.load_entries(Path(_write(tmp_path, {"providers": [ENTRY]})))

    assert [entry["id"] for entry in entries] == ["my-gateway"]


def test_load_skips_bad_rows_and_keeps_good_ones(tmp_path):
    """坏条目（缺 id / 缺 label / 地址不是 http(s) / id 重复 / 不是对象）只跳过。"""
    from pathlib import Path

    entries = provider_config.load_entries(
        Path(
            _write(
                tmp_path,
                [
                    "不是一个对象",
                    {"label": "没有 id", "base_url": "https://a.example/v1"},
                    {"id": "no-label", "base_url": "https://a.example/v1"},
                    {"id": "bad-url", "label": "地址不对", "base_url": "ftp://a.example/v1"},
                    ENTRY,
                    {**ENTRY, "label": "重复 id"},
                ],
            )
        )
    )

    assert [entry["id"] for entry in entries] == ["my-gateway"]


def test_missing_file_and_broken_json_are_not_fatal(tmp_path):
    """文件不存在 / 不是合法 JSON：返回空表，不抛（坏配置不该让应用起不来）。"""
    from pathlib import Path

    assert provider_config.load_entries(Path(tmp_path / "nope.json")) == []
    broken = tmp_path / "broken.json"
    broken.write_text("{不是 JSON", encoding="utf-8")
    assert provider_config.load_entries(Path(broken)) == []


# ---- 并入目录与工厂 ----


def test_merge_puts_the_provider_into_the_catalog():
    """并入后：设置页能列出这家，写设置时也不再是「未知供应商」。"""
    merged = provider_config.merge_entries([_entry()])

    assert merged == ["my-gateway"]
    spec = PROVIDERS["my-gateway"]
    assert spec.label == "我的中转"
    assert spec.base_url == "https://api.example.edu/v1"
    assert list(spec.chat_models) == ["edu-chat-32b", "edu-chat-8b"]
    assert list(spec.vision_models) == ["edu-vl-8b"]
    assert DIALECTS["my-gateway"].api_key_env == "MY_GATEWAY_API_KEY"
    validate_patch({"llm_provider": "my-gateway"}, {}, {})  # 不抛 = 目录里有这家


def test_legacy_path_reads_the_key_from_the_env_var(monkeypatch):
    """没加实例时的 legacy 路径：Key 从 api_key_env 指向的环境变量读。"""
    from app.config import settings

    provider_config.merge_entries([_entry()])
    monkeypatch.setattr(settings, "llm_provider", "my-gateway")
    monkeypatch.setenv("MY_GATEWAY_API_KEY", "sk-from-env")
    get_llm.cache_clear()

    provider = get_llm()

    assert provider.base_url == "https://api.example.edu/v1"
    assert provider.model == "edu-chat-32b"
    assert provider.api_key == "sk-from-env"
    assert provider.vision_model == "edu-vl-8b"


def test_legacy_path_without_key_names_the_env_var(monkeypatch):
    """环境变量也空着：报错指名该设哪个变量（面向教师的引导里看得见）。"""
    from app.config import settings

    provider_config.merge_entries([_entry()])
    monkeypatch.setattr(settings, "llm_provider", "my-gateway")
    get_llm.cache_clear()

    with pytest.raises(ProviderNotConfigured, match="MY_GATEWAY_API_KEY"):
        get_llm()


def _entry() -> dict:
    """走一遍真实的解析路径（含缺省值补齐），而不是手搓一个字典。"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        entries = provider_config.load_entries(Path(_write(Path(tmp), [ENTRY])))
    assert len(entries) == 1
    return entries[0]


def test_catalog_keeps_arbitrary_model_policy():
    entry = _entry()
    entry["accepts_any_model"] = True
    provider_config.merge_entries([entry])
    assert PROVIDERS[entry["id"]].accepts_any_model is True
    validate_patch({"llm_provider": entry["id"], "llm_model": "manual-id"}, {}, {})


def test_catalog_keeps_all_embedding_and_vision_models():
    entry = _entry()
    entry.update(
        embed_model="embed-a",
        embed_models=["embed-a", "embed-b"],
        vision_model="",
        vision_models=["vision-only"],
    )
    provider_config.merge_entries([entry])
    spec = PROVIDERS[entry["id"]]
    assert spec.embed_models == ("embed-a", "embed-b")
    assert spec.vision_models == ("vision-only",)


def test_explicit_override_does_not_append_builtin_models():
    entry = _entry()
    entry["id"] = "deepseek"
    provider_config.merge_entries([entry])
    spec = PROVIDERS["deepseek"]
    assert spec.chat_models == ("edu-chat-32b", "edu-chat-8b")
    assert spec.vision_models == ("edu-vl-8b",)


def test_declared_key_and_path_are_loaded_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write(tmp_path, [ENTRY])
    (tmp_path / ".env").write_text(
        f"PROVIDERS_CONFIG={path}\nMY_GATEWAY_API_KEY=offline-dotenv-key\n", encoding="utf-8"
    )
    monkeypatch.delenv("PROVIDERS_CONFIG", raising=False)
    monkeypatch.delenv("MY_GATEWAY_API_KEY", raising=False)
    entries = provider_config.load_entries()
    assert [entry["id"] for entry in entries] == [ENTRY["id"]]
    assert (
        provider_config.env_api_key(provider_config.dialect_of(entries[0])) == "offline-dotenv-key"
    )
    monkeypatch.setenv("MY_GATEWAY_API_KEY", "process-wins")
    assert provider_config.env_api_key(provider_config.dialect_of(entries[0])) == "process-wins"
    monkeypatch.setenv("MY_GATEWAY_API_KEY", "")
    assert provider_config.env_api_key(provider_config.dialect_of(entries[0])) == ""


def test_non_utf8_config_is_skipped(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff\xfe")
    assert provider_config.load_entries(path) == []
