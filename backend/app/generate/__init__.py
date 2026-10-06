"""课件生成引擎：PPT / Word / 试卷 / 创意内容。"""

import uuid
from pathlib import Path

from app.config import settings

# 生成物落盘目录：唯一事实源是 settings.output_dir（默认 backend/data/output）。
# 测试用 conftest 的 isolated_output_dir 重定向本模块属性；生产从配置读（M3）。
OUTPUT_DIR = Path(settings.output_dir)


def output_dir() -> Path:
    """生成物落盘目录（调用时读取模块属性，测试可重定向；生产下即 settings.output_dir）。"""
    return OUTPUT_DIR


def unique_output_path(stem: str, suffix: str) -> str:
    """统一随机命名：固定前缀 + 8 位随机后缀，连续生成同类产物互不覆盖。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return str(OUTPUT_DIR / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}")
