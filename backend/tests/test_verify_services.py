"""仅配置一个服务时仍独立验证，失败返回非通过状态。"""

from app.core.errors import ProviderNotConfigured
from scripts.verify_services import run_check


async def test_missing_service_does_not_block_next_service(capsys):
    async def missing():
        raise ProviderNotConfigured("搜索未配置")

    async def available():
        return None

    assert await run_check("search", missing) is None
    assert await run_check("chat", available) is True
    assert "SKIP search" in capsys.readouterr().out


async def test_service_failure_is_not_pass_and_private_detail_is_not_printed(capsys):
    async def failed():
        raise RuntimeError("private-key")

    assert await run_check("chat", failed) is False
    output = capsys.readouterr().out
    assert "FAIL chat" in output and "private-key" not in output
