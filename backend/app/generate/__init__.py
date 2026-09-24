"""课件生成引擎：PPT / Word / 试卷 / 创意内容。"""

import uuid
from pathlib import Path

OUTPUT_DIR = Path("data/output")


def output_dir() -> Path:
    """生成物落盘目录（调用时读取模块属性，测试可重定向；生产下即 `data/output`）。"""
    return OUTPUT_DIR


def unique_output_path(stem: str, suffix: str) -> str:
    """统一随机命名：固定前缀 + 8 位随机后缀，连续生成同类产物互不覆盖。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return str(OUTPUT_DIR / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}")
