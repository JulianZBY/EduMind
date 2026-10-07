"""测试隔离：整场测试会话共用一个临时目录，不污染开发库/开发数据；
且不依赖开发者的 `backend/.env`（真实 Key / 真实 provider 一律不参与测试）。

必须在任何 app 模块导入前设置环境变量（pydantic-settings 中环境变量优先于 .env）：

**落盘隔离**
- DATABASE_URL：主库（SQLAlchemy）
- VECTORS_DB_PATH：向量库（sqlite-vec，否则冲突检测等内部默认构造会写进 data/vectors.db）
- UPLOAD_DIR：上传文件落盘目录
- OUTPUT_DIR：生成物落盘目录（否则每跑一轮测试就往 backend/data/output 写入几十个文件，
  和教师的真实生成物混在一起；`isolated_output_dir` 夹具只覆盖显式声明它的用例）

**密封隔离**（票 14 收口，产品不再有假数据兜底后沿用）：云端 provider 一律不配（代码默认空），
环境变量优先级高于 `.env`，因此即使开发者 `.env` 里写着 `LLM_PROVIDER=qwen` + 真实 Key，
测试仍不会调用真实服务；需要 LLM / 转写 / 搜索的用例挂 `tests/support` 里的替身
（离线、确定、零成本）。检索 / 分块策略仍钉默认档——少钉一个都会出现
「本机全绿、CI 或换台机器红」的假失败（票 13 报告口径）。
"""

import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="edumind-test-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ.setdefault("VECTORS_DB_PATH", str(_tmp / "vectors.db"))
os.environ.setdefault("UPLOAD_DIR", str(_tmp / "uploads"))
os.environ.setdefault("OUTPUT_DIR", str(_tmp / "output"))
# 供应商扩展配置文件：测试一律不读开发机上的 providers.json（要测扩展的用例自己指定路径）
os.environ.setdefault("PROVIDERS_CONFIG", "")
# ---- 密封：能力 provider 与 Key（见文件头「密封隔离」）----
# 云端 provider 一律不配（代码默认空）：产品无假数据兜底，未配置时相关能力抛
# ProviderNotConfigured。测试需要 LLM / 转写 / 搜索时挂 tests/support 里的替身
# （FakeLLM / FakeTranscriber / FakeSearch / FakeEmbedder），离线、确定、零成本。
# 检索/分块策略仍钉在代码默认档（断言口径与「本机无 .env」一致）。
for _name, _value in (
    ("RETRIEVAL_STRATEGY", "vector_graph"),  # 检索策略默认档
    ("CHUNK_STRATEGY", "paragraph"),  # 分块策略默认档
):
    os.environ.setdefault(_name, _value)

# 云端 Key 一律清空：万一某条用例把 provider 改成真实实现，也不会带着 `.env`
# 里的真 Key 打真实网络。
for _name in (
    "QWEN_API_KEY",
    "DEEPSEEK_API_KEY",
    "MOONSHOT_API_KEY",
    "ZHIPU_API_KEY",
    "MINIMAX_API_KEY",
    "ARK_API_KEY",
    "SILICONFLOW_API_KEY",
    "MINERU_TOKEN",
    "BOCHA_API_KEY",
    "ASR_API_KEY",
    "LLM_API_KEY",
    "EMBEDDING_API_KEY",
):
    os.environ.setdefault(_name, "")


# ---- 票 05 的公共接缝：LLM 能力替身与生成物落盘隔离（app 模块在函数体内导入，
# 保证上面的环境变量先落地；见文件头的不变式）----
# ---- 默认假 LLM：所有测试默认挂 tests/support 里的替身（离线、确定、零成本）----
# 需要「未配置」状态的用例（如设置页测试）自行把 llm_provider 设回空并清缓存。


@pytest.fixture(autouse=True)
def _default_fake_llm(monkeypatch):
    from app.config import settings
    from app.core.llm.factory import LLM_BUILDERS, get_llm
    from tests.support.fakes import FAKE_LLM_PROVIDER, FakeLLM

    llm = FakeLLM()
    monkeypatch.setitem(LLM_BUILDERS, FAKE_LLM_PROVIDER, lambda cfg: llm)
    monkeypatch.setattr(settings, "llm_provider", FAKE_LLM_PROVIDER)
    get_llm.cache_clear()
    yield llm
    get_llm.cache_clear()


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
