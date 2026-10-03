"""服务响应、TLS 和 JSON 边界的离线契约。"""

import ssl

import httpx
import pytest

from app.core.errors import ProviderRequestFailed
from app.core.http import tls_context
from app.core.llm.base import ChatMessage
from app.core.llm.parsing import parse_json
from app.core.llm.providers.openai_compat import OpenAICompatProvider


@pytest.mark.parametrize("status", [401, 403, 429, 400, 500])
async def test_provider_status_is_safe_and_actionable(status):
    provider = OpenAICompatProvider(
        base_url="https://example.invalid",
        model="m",
        api_key="secret-key",
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text="secret-body")),
    )
    with pytest.raises(ProviderRequestFailed) as caught:
        await provider.chat([ChatMessage(role="user", content="hi")])
    assert caught.value.status_code == 502
    assert "secret" not in str(caught.value)


async def test_provider_timeout_is_504():
    def timeout(request):
        raise httpx.ReadTimeout("private detail", request=request)

    provider = OpenAICompatProvider(
        base_url="https://example.invalid",
        model="m",
        api_key="k",
        transport=httpx.MockTransport(timeout),
    )
    with pytest.raises(ProviderRequestFailed) as caught:
        await provider.chat([ChatMessage(role="user", content="hi")])
    assert caught.value.status_code == 504


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        ["invalid"],
        {"choices": [{"message": {"content": {"unexpected": "object"}}}]},
    ],
)
async def test_invalid_success_response_is_not_generation(payload):
    provider = OpenAICompatProvider(
        base_url="https://example.invalid",
        model="m",
        api_key="k",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)),
    )
    with pytest.raises(ProviderRequestFailed):
        await provider.chat([ChatMessage(role="user", content="hi")])


def test_tls_keeps_certificate_and_hostname_verification():
    context = tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


@pytest.mark.parametrize("text", ["[]", "null", '"text"', "123", "{bad"])
def test_json_parser_returns_only_objects(text):
    assert parse_json(text) == {}
