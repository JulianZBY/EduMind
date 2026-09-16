"""文件存储：保存上传的原始资料到本地目录。"""

import uuid
from pathlib import Path

from app.config import settings

UPLOAD_DIR = Path(settings.upload_dir)


def save_upload(content: bytes, filename: str) -> str:
    """保存上传文件，返回相对路径。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / stored_name
    dest.write_bytes(content)
    return str(dest)
