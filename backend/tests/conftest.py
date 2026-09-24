"""测试隔离：整场测试会话共用一个临时目录，不污染开发库/开发数据。

必须在任何 app 模块导入前设置环境变量（pydantic-settings 中环境变量优先于 .env）：
- DATABASE_URL：主库（SQLAlchemy）
- VECTORS_DB_PATH：向量库（sqlite-vec，否则冲突检测等内部默认构造会写进 data/vectors.db）
- UPLOAD_DIR：上传文件落盘目录
外部显式指定时以其为准（setdefault）。
"""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="edumind-test-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ.setdefault("VECTORS_DB_PATH", str(_tmp / "vectors.db"))
os.environ.setdefault("UPLOAD_DIR", str(_tmp / "uploads"))
