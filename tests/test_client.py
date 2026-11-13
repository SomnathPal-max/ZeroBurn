"""Unit tests for GatewayClient error mapping and chat parsing."""
from __future__ import annotations

import httpx
import pytest
from unittest.mock import MagicMock, patch
from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    BadRequestError,
    AuthenticationError,
    RateLimitError,
    InternalServerError,
)
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage

from zeroburn.gateway.client import GatewayClient, LLMResult, ToolCall
from zeroburn.errors import (
    RateLimited,
    ProviderDown,
    BudgetBlocked,
    GatewayPolicyBlocked,
    BadRequest,
    AuthError,
)


@pytest.fixture
def client() -> GatewayClient:
    return GatewayClient(base_url="http://localhost:8080/v1")


def test_success_chat(client: GatewayClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_completion = ChatCompletion(
        id="chatcmpl-123",
        created=1677652288,
        model="openai/gpt-4o-mini",
        object="chat.completion",
        choices=[
            Choice(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content="Hello world",
                ),
            )
        ],
        usage=CompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    with patch("openai.resources.chat.completions.Completions.create", return_value=fake_completion):
        res = client.chat(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": "hello"}],
            vk="sk-bf-standard",
        )
        assert res.content == "Hello world"
        assert res.prompt_tokens == 10
        assert res.completion_tokens == 5
        assert res.served_model == "openai/gpt-4o-mini"
        assert res.tool_calls == []
        assert res.latency_ms >= 0


def test_success_with_tool_calls(client: GatewayClient) -> None:
    fake_completion = ChatCompletion(
        id="chatcmpl-123",
        created=1677652288,
        model="ollama/llama3.1:8b",
        object="chat.completion",
        choices=[
            Choice(
                finish_reason="tool_calls",
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        {
                            "id": "call_abc",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "README.md"}',
                            },
                        }
                    ],
                ),
            )
        ],
        usage=CompletionUsage(prompt_tokens=25, completion_tokens=10, total_tokens=35),
    )

    with patch("openai.resources.chat.completions.Completions.create", return_value=fake_completion):
        res = client.chat(
            model="ollama/llama3.1:8b",
            messages=[{"role": "user", "content": "read README.md"}],
            vk="sk-bf-confidential",
        )
        assert res.content is None
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0].name == "read_file"
        assert res.tool_calls[0].args == {"path": "README.md"}
        assert res.served_model == "ollama/llama3.1:8b"


def _make_status_error(status: int, body_text: str) -> APIStatusError:
    req = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")
    resp = httpx.Response(status, text=body_text, request=req)
    return APIStatusError(f"HTTP {status}", response=resp, body={"message": body_text})


def test_error_mapping_rate_limited(client: GatewayClient) -> None:
    err = _make_status_error(429, "Too many requests per minute, slow down")
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(RateLimited):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_budget_blocked_429(client: GatewayClient) -> None:
    err = _make_status_error(429, "Virtual key monthly budget limit exceeded")
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(BudgetBlocked):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_budget_blocked_403(client: GatewayClient) -> None:
    err = _make_status_error(403, "Budget quota exceeded for virtual key")
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(BudgetBlocked):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_gateway_policy_blocked_403(client: GatewayClient) -> None:
    err = _make_status_error(
        403,
        '{"is_bifrost_error": true, "error": {"message": "Virtual key sk-bf-confidential is restricted to provider [ollama]; access to provider [openai] is denied"}}',
    )
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(GatewayPolicyBlocked):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_gateway_policy_blocked_400(client: GatewayClient) -> None:
    err = _make_status_error(400, "provider is not allowed for this virtual key")
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(GatewayPolicyBlocked):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_bad_request(client: GatewayClient) -> None:
    err = _make_status_error(400, "Invalid JSON schema: messages must be a non-empty list")
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(BadRequest):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_auth_error(client: GatewayClient) -> None:
    err = _make_status_error(401, "Invalid virtual key or unauthorized")
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(AuthError):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_provider_down_5xx(client: GatewayClient) -> None:
    err = _make_status_error(503, "Upstream provider returned HTTP 503 Service Unavailable")
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(ProviderDown):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_timeout(client: GatewayClient) -> None:
    req = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")
    err = APITimeoutError(request=req)
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(ProviderDown):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])


def test_error_mapping_connection_error(client: GatewayClient) -> None:
    req = httpx.Request("POST", "http://localhost:8080/v1/chat/completions")
    err = APIConnectionError(request=req, message="Connection refused")
    with patch("openai.resources.chat.completions.Completions.create", side_effect=err):
        with pytest.raises(ProviderDown):
            client.chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])
