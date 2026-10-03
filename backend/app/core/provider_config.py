"""声明式供应商配置：不改代码就能加一家 OpenAI 兼容服务商。

读 `PROVIDERS_CONFIG` 指向的 JSON 文件（默认 `backend/providers.json`；文件不存在 = 没有扩展），
把里面的条目并入方言表与供应商目录。加一家服务商从此只改配置：内置方言表（`dialects.py`）
只留给「官方平台」这类需要默认模型口径的家。

文件格式（数组，或 `{"providers": [...]}`；模板见 `providers.example.json`）::

    [
      {
        "id": "my-gateway",                          # 必填：方言 id（也是 LLM_PROVIDER 的取值）
        "label": "我的中转",                          # 必填：面向教师的名称
        "base_url": "https://api.example.com/v1",     # 必填：http(s) 地址
        "api_key_env": "MY_GATEWAY_API_KEY",          # 可选：Key 从哪个环境变量读
        "chat_models": ["m1", "m2"],                  # 可选：对话模型清单（不填 = 放行任意模型）
        "vision_models": ["m1"],                      # 可选：其中支持视觉的
        "embed_models": [],                           # 可选：向量化模型（空 = 该家不提供）
        "chat_model": "m1",                           # 可选：默认对话模型（缺省取 chat_models[0]）
        "vision_model": "m1",                         # 可选：默认视觉模型（缺省取 vision_models[0]）
        "embed_model": "",                            # 可选：默认向量化模型
        "embed_dimensions": 0,                        # 可选：embedding 请求携带的 dimensions
        "note": "公司中转"                             # 可选：设置页里的一句话说明
      }
    ]

三条纪律：

1. **Key 不落这个文件**：`api_key_env` 指向环境变量（写 `.env`），或者在设置页「添加供应商」
   里粘贴（Key 存在供应商实例行上，回读只有掩码）。
2. **坏配置不拖垮应用**：条目非法（缺 id/label/base_url、地址不是 http(s)、id 重复）只跳过
   并留一条告警——和「设置库里的存量值不该成为应用起不来的原因」是同一条纪律。
3. **显式配置优先**：与内置方言同名 = 覆盖内置，日志会写一行。

合并是**进程级一次性**且幂等的：能力工厂与目录在各自模块 import 时各调一次 `ensure_merged()`。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import dotenv_values

from app.config import Settings
from app.core.dialects import DIALECTS, Dialect

logger = logging.getLogger(__name__)

ENV_VAR = "PROVIDERS_CONFIG"
DEFAULT_CONFIG_PATH = "providers.json"

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

_merged = False


def _environment_value(name: str) -> str | None:
    """进程环境优先（包括显式清空），其次读取与 Settings 相同的 .env 文件。"""
    if name in os.environ:
        return os.environ[name]
    paths = Settings.model_config.get("env_file") or ()
    if isinstance(paths, (str, Path)):
        paths = (paths,)
    values = {}
    for path in paths:
        if Path(path).is_file():
            values.update(dotenv_values(path, encoding="utf-8"))
    return values.get(name)


def _config_path() -> Path | None:
    """配置文件路径：`PROVIDERS_CONFIG` 说了算；设成空字符串 = 明确关闭扩展。"""
    raw = _environment_value(ENV_VAR)
    if raw is None:
        return Path(DEFAULT_CONFIG_PATH)
    raw = raw.strip()
    return Path(raw) if raw else None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize(item: Any, index: int, taken: set[str]) -> dict[str, Any] | None:
    """校验并归一化一条配置；不合法返回 None（只留告警）。"""
    if not isinstance(item, dict):
        logger.warning("供应商配置第 %d 条不是对象，已跳过", index + 1)
        return None
    provider_id = _text(item.get("id")).lower()
    label = _text(item.get("label"))
    base_url = _text(item.get("base_url")).rstrip("/")
    if not provider_id or not _ID_PATTERN.match(provider_id):
        logger.warning(
            "供应商配置第 %d 条缺 id 或 id 不合法（只要小写字母/数字/._-）：%r",
            index + 1,
            item.get("id"),
        )
        return None
    if provider_id in taken:
        logger.warning("供应商配置里 id 重复：%s（第 %d 条已跳过）", provider_id, index + 1)
        return None
    if not label:
        logger.warning("供应商配置 %s 缺 label（面向教师的名称），已跳过", provider_id)
        return None
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        logger.warning(
            "供应商配置 %s 的 base_url 不是 http(s) 完整地址，已跳过：%r", provider_id, base_url
        )
        return None
    chat_models = _text_list(item.get("chat_models"))
    vision_models = _text_list(item.get("vision_models"))
    embed_models = _text_list(item.get("embed_models"))
    dimensions = item.get("embed_dimensions")
    return {
        "id": provider_id,
        "label": label,
        "base_url": base_url,
        "api_key_env": _text(item.get("api_key_env")),
        "chat_model": _text(item.get("chat_model")) or (chat_models[0] if chat_models else ""),
        "vision_model": _text(item.get("vision_model"))
        or (vision_models[0] if vision_models else ""),
        "embed_model": _text(item.get("embed_model")) or (embed_models[0] if embed_models else ""),
        "chat_models": chat_models,
        "vision_models": vision_models,
        "embed_models": embed_models,
        "embed_dimensions": dimensions if isinstance(dimensions, int) else 0,
        # 没声明模型清单 = 放行任意模型 ID（服务商自己说了算，与 `/v1/models` 拉取口径一致）
        "accepts_any_model": bool(item.get("accepts_any_model", not chat_models)),
        "note": _text(item.get("note")) or "由 providers.json 声明的服务商。",
    }


def load_entries(path: Path | None = None) -> list[dict[str, Any]]:
    """读并校验配置条目；文件不存在、读不动、格式不对都只返回空表（留告警，不抛）。"""
    target = path if path is not None else _config_path()
    if target is None:
        return []
    if not target.is_file():
        if path is not None:
            logger.warning("供应商配置文件不存在：%s", target)
        return []
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        logger.warning("供应商配置文件读不动（%s）：%s", target, error)
        return []
    items = raw.get("providers") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        logger.warning('供应商配置文件顶层要是数组或 {"providers": [...]}：%s', target)
        return []
    entries: list[dict[str, Any]] = []
    taken: set[str] = set()
    for index, item in enumerate(items):
        entry = _normalize(item, index, taken)
        if entry is not None:
            taken.add(entry["id"])
            entries.append(entry)
    return entries


def dialect_of(entry: dict[str, Any]) -> Dialect:
    """配置条目 → 方言（Key 走 `api_key_env`，名称与说明也随方言带过去）。"""
    return Dialect(
        name=entry["id"],
        base_url=entry["base_url"],
        chat_model=entry["chat_model"],
        api_key_field="",
        api_key_env=entry["api_key_env"],
        vision_model=entry["vision_model"],
        embed_model=entry["embed_model"],
        embed_dimensions=entry["embed_dimensions"],
        extra_chat_models=tuple(entry["chat_models"]),
        extra_vision_models=tuple(entry["vision_models"]),
        extra_embed_models=tuple(entry["embed_models"]),
        accepts_any_model=entry["accepts_any_model"],
        configured=True,
        label=entry["label"],
        note=entry["note"],
    )


def merge_entries(entries: list[dict[str, Any]]) -> list[str]:
    """把条目并入方言表（并尽量同步目录），返回并入了哪些 id（同名覆盖内置）。"""
    if not entries:
        return []
    merged: list[str] = []
    for entry in entries:
        overwriting = entry["id"] in DIALECTS
        DIALECTS[entry["id"]] = dialect_of(entry)
        merged.append(entry["id"])
        logger.info(
            "已并入配置供应商：%s（%s）%s",
            entry["label"],
            entry["base_url"],
            "，覆盖同名内置方言" if overwriting else "",
        )
    _sync_catalog(merged)
    return merged


def _sync_catalog(merged: list[str]) -> None:
    """把并入的家同步进供应商目录（catalog 还没建好目录时跳过——它自己会从方言表建全）。"""
    try:
        from app.core.catalog import PROVIDERS, build_spec_from_dialect
    except ImportError:  # pragma: no cover - 只在 catalog 尚在 import 中时发生
        return
    for provider_id in merged:
        PROVIDERS[provider_id] = build_spec_from_dialect(DIALECTS[provider_id])


def env_api_key(dialect: Dialect) -> str:
    """配置声明的家的 Key：从 `api_key_env` 指向的环境变量读；没声明或没设就是空串。"""
    if not dialect.api_key_env:
        return ""
    return (_environment_value(dialect.api_key_env) or "").strip()


def ensure_merged() -> None:
    """进程级一次性并入（幂等）：能力工厂与目录各在 import 时调一次。"""
    global _merged
    if _merged:
        return
    _merged = True
    merge_entries(load_entries())


def reset_for_tests() -> None:
    """测试用：忘掉「已并入」标记，让用例可以自己决定并入什么（不会撤销已并入的项）。"""
    global _merged
    _merged = False
