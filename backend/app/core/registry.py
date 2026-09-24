"""能力注册表：配置名 → 构造器。

五项云端能力（对话 / 向量化 / 语音转写 / PDF 解析 / 网络搜索）共用一个口径：
每个能力一份注册表，选择只发生在工厂；调用方只依赖接口，新增实现只往注册表
加一行（调用方零改动）。
"""

from collections.abc import Callable, Mapping
from typing import TypeVar

from app.config import Settings

T = TypeVar("T")

Builder = Callable[[Settings], T]


def build(registry: Mapping[str, Builder[T]], name: str, cfg: Settings, kind: str) -> T:
    """按配置名构造实现；未注册的名字给出可选项清单。"""
    key = (name or "").strip().lower()
    builder = registry.get(key)
    if builder is None:
        raise ValueError(f"未实现的{kind}: {name}（可选：{', '.join(sorted(registry))}）")
    return builder(cfg)


def register(registry: dict[str, Builder[T]], name: str, builder: Builder[T]) -> Builder[T]:
    """注册一个实现（新增能力实现只调这一句）。"""
    registry[name.strip().lower()] = builder
    return builder
