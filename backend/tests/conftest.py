"""测试隔离：整场测试会话共用一个临时目录，不污染开发库/开发数据；
且不依赖开发者的 `backend/.env`（真实 Key / 真实 provider 一律不参与测试）。

必须在任何 app 模块导入前设置环境变量（pydantic-settings 中环境变量优先于 .env）：

**落盘隔离**
- DATABASE_URL：主库（SQLAlchemy）
- VECTORS_DB_PATH：向量库（sqlite-vec，否则冲突检测等内部默认构造会写进 data/vectors.db）
- UPLOAD_DIR：上传文件落盘目录

**密封隔离**（票 14 收口）：把云端能力的 provider 钉在 stub 一档。
环境变量优先级高于 `.env`，因此即使开发者 `.env` 里写着 `LLM_PROVIDER=dashscope` + 真实 Key，
测试仍跑在 stub 模式：不花真钱、不走网络、耗时稳定，断言的都是代码默认档的行为。
少钉一个都会出现「本机全绿、CI 或换台机器红」的假失败（票 13 报告：`RETRIEVAL_STRATEGY`
被 `.env` 改成 `vector` 时，断言默认档 `vector_graph` 的两条用例会红）。

外部显式指定时以其为准（setdefault）：想在真实 provider 上跑一次时，直接 `$env:LLM_PROVIDER="dashscope"`。
"""

import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="edumind-test-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ.setdefault("VECTORS_DB_PATH", str(_tmp / "vectors.db"))
os.environ.setdefault("UPLOAD_DIR", str(_tmp / "uploads"))

# ---- 密封：能力 provider 与 Key（见文件头「密封隔离」）----
# 取值 = 各项的**代码默认档**，因此测试断言的口径与「本机无 .env」完全一致。
for _name, _value in (
    ("LLM_PROVIDER", "stub"),  # 对话 / 多模态理解
    ("EMBEDDING_PROVIDER", "stub"),  # 向量化
    ("ASR_PROVIDER", "stub"),  # 录音转写
    ("SEARCH_PROVIDER", "stub"),  # 网络搜索
    ("RETRIEVAL_STRATEGY", "vector_graph"),  # 检索策略默认档
    ("CHUNK_STRATEGY", "paragraph"),  # 分块策略默认档
):
    os.environ.setdefault(_name, _value)

# 云端 Key 一律清空：provider 已钉住，这里只是**双保险**——
# 万一某条用例把 provider 改成真实实现，也不会带着 `.env` 里的真 Key 打真实网络。
for _name in (
    "DASHSCOPE_API_KEY",
    "DEEPSEEK_API_KEY",
    "SILICONFLOW_API_KEY",
    "MINERU_TOKEN",
    "BOCHA_API_KEY",
    "LLM_API_KEY",
    "EMBEDDING_API_KEY",
):
    os.environ.setdefault(_name, "")


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
