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


# 互动内容是模型生成的整页 HTML（含脚本）。直接以应用同源打开时，它能调用本应用的全部接口
# （接口没有认证），而脚本内容由模型决定、模型的输入又包含教师上传的资料。
# `sandbox` 不带 `allow-same-origin`：页面在独立的不透明源里运行，脚本照常可用，
# 但读不到本应用的存储、也发不出同源请求。弹窗 / 表单 / 指针锁是小游戏常用的能力，保留。
HTML_ISOLATION_HEADERS = {
    "Content-Security-Policy": "sandbox allow-scripts allow-modals allow-forms allow-pointer-lock",
    "X-Content-Type-Options": "nosniff",
}


def isolation_headers(filename: str) -> dict[str, str]:
    """按生成物文件名给出响应头：HTML 生成物加隔离头，其余格式不需要。"""
    if filename.lower().endswith((".html", ".htm")):
        return dict(HTML_ISOLATION_HEADERS)
    return {}


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
