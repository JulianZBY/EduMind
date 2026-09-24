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

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="edumind-test-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ.setdefault("VECTORS_DB_PATH", str(_tmp / "vectors.db"))
os.environ.setdefault("UPLOAD_DIR", str(_tmp / "uploads"))


# ---- 票 05 的公共接缝：LLM 能力替身与生成物落盘隔离（app 模块在函数体内导入，
# 保证上面的环境变量先落地；见文件头的不变式）----


@pytest.fixture
def install_semantic_llm(monkeypatch):
    """把语义网关替身注册进 LLM 能力表并选中它（测试结束清缓存，不污染其他用例）。"""
    from app.config import settings
    from app.core.llm.factory import LLM_BUILDERS, get_llm
    from tests.session_support import TEST_LLM_PROVIDER, SemanticLLM

    def _install(*, learned: dict | None = None, skip: bool = False) -> SemanticLLM:
        llm = SemanticLLM(learned=learned, skip=skip)
        monkeypatch.setitem(LLM_BUILDERS, TEST_LLM_PROVIDER, lambda cfg: llm)
        monkeypatch.setattr(settings, "llm_provider", TEST_LLM_PROVIDER)
        get_llm.cache_clear()
        return llm

    yield _install
    get_llm.cache_clear()


@pytest.fixture
def isolated_output_dir(monkeypatch, tmp_path):
    """备课生成物落盘重定向到临时目录：测试不写 `backend/data/output`。"""
    import app.generate as generate_module

    monkeypatch.setattr(generate_module, "OUTPUT_DIR", tmp_path / "output")
