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


def remove_output_files(filenames: list[str]) -> int:
    """删除落盘的生成物文件，返回实际删掉的个数。

    只认文件名（不含目录），且只在生成物目录内删除；文件已不在时跳过——
    调用方是「删除备课会话」这类清理路径，单个文件删不掉不应让整个操作失败。
    """
    removed = 0
    for name in filenames:
        if not name or Path(name).name != name:
            continue
        path = OUTPUT_DIR / name
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def unique_output_path(stem: str, suffix: str) -> str:
    """统一随机命名：固定前缀 + 8 位随机后缀，连续生成同类产物互不覆盖。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return str(OUTPUT_DIR / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}")
