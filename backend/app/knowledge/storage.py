"""文件存储：保存上传的原始资料到本地目录。

资料文件路径的读写统一经 `normalize_stored_path` 规范化为 POSIX 分隔符：整库自 Windows
迁来时 `documents.file_path` 曾残留 `data\\uploads\\...` 形态，票 02 清理后存量已空，
这里守住的是防御线（写入口 + 引擎迁移链，见 `app/db/engine.py`）。
"""

import uuid
from pathlib import Path

from app.config import settings

UPLOAD_DIR = Path(settings.upload_dir)


def normalize_stored_path(path: str) -> str:
    """把落库的资料文件路径统一为 POSIX 分隔符：反斜杠一律转正斜杠（幂等）。"""
    return path.replace("\\", "/")


def save_upload(content: bytes, filename: str) -> str:
    """保存上传文件，返回 POSIX 分隔符的路径。"""
    upload_dir = Path(normalize_stored_path(str(UPLOAD_DIR)))
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = upload_dir / stored_name
    dest.write_bytes(content)
    return normalize_stored_path(str(dest))
