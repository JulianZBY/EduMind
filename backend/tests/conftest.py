"""测试隔离：整场测试会话共用一个临时 SQLite 库，不污染开发库 backend/edumind.db。

必须在任何 app 模块导入前设置 DATABASE_URL（pydantic-settings 中环境变量优先于 .env）。
外部显式指定 DATABASE_URL 时以其为准（setdefault）。
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{Path(tempfile.mkdtemp(prefix='edumind-test-')) / 'test.db'}",
)
