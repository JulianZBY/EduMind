"""课件生成引擎：PPT / Word / 试卷 / 创意内容。"""

import uuid
from pathlib import Path

OUTPUT_DIR = Path("data/output")


def unique_output_path(stem: str, suffix: str) -> str:
    """统一随机命名：固定前缀 + 8 位随机后缀，连续生成同类产物互不覆盖。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return str(OUTPUT_DIR / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}")
