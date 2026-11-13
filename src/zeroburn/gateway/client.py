"""Bifrost gateway client wrapping OpenAI SDK with typed error mapping."""
from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
from typing import Any
import openai
from openai import OpenAI
from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    BadRequestError,
    AuthenticationError,
    RateLimitError,
    InternalServerError,
)

from zeroburn.errors import (
    RateLimited,
    ProviderDown,
    BudgetBlocked,
    GatewayPolicyBlocked,
    BadRequest,
    AuthError,
)


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResult:
    content: str | None
    tool_calls: list[ToolCall]
    prompt_tokens: int
    completion_tokens: int
    served_model: str
    latency_ms: int


class GatewayClient:
    def __init__(self, base_url: str = "http://localhost:8080/v1", timeout_s: float = 60.0):
        # Normalize base_url to include /v1 if missing
        url = base_url.rstrip("/")
        if not url.endswith("/v1") and not url.endswith("/v1/"):
            url = f"{url}/v1"
        self.base_url = url
        self.timeout_s = timeout_s

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        vk: str = "sk-bf-standard",
    ) -> LLMResult:
        # Client pointed to Bifrost gateway with virtual key headers
        client = OpenAI(
            base_url=self.base_url,
            api_key=vk,
            default_headers={"x-bf-vk": vk},
            timeout=self.timeout_s,
        )

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools

        start_time = time.monotonic()
        try:
            response = client.chat.completions.create(**kwargs)
        except (APITimeoutError, APIConnectionError) as exc:
            raise ProviderDown(f"Connection/Timeout error to gateway or provider: {exc}") from exc
        except APIStatusError as exc:
            self._map_api_error(exc)
        except Exception as exc:
            raise ProviderDown(f"Unexpected transport error: {exc}") from exc

        latency_ms = int((time.monotonic() - start_time) * 1000)

        choice = response.choices[0]
        content = choice.message.content

        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                parsed_args: dict[str, Any] = {}
                try:
                    if tc.function.arguments:
                        parsed_args = json.loads(tc.function.arguments)
                except Exception:
                    parsed_args = {"_raw": tc.function.arguments}
                tool_calls.append(
                    ToolCall(
                        id=tc.id or "",
                        name=tc.function.name,
                        args=parsed_args,
                    )
                )

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        served_model = response.model or model

        return LLMResult(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            served_model=served_model,
            latency_ms=latency_ms,
        )

    def _map_api_error(self, exc: APIStatusError) -> None:
        status = exc.status_code
        err_text = ""
        try:
            if hasattr(exc, "response") and exc.response is not None:
                err_text = exc.response.text
            elif hasattr(exc, "body"):
                err_text = json.dumps(exc.body)
            else:
                err_text = str(exc)
        except Exception:
            err_text = str(exc)

        err_lower = err_text.lower()
        has_budget_word = any(w in err_lower for w in ["budget", "quota exceeded", "balance", "insufficient_quota"])
        has_policy_word = any(
            w in err_lower
            for w in [
                "gateway_policy_blocked",
                "provider is not allowed",
                "restricted to provider",
                "provider_disallowed",
                "access denied",
                "not allowed",
                "provider refusal",
            ]
        )

        if status == 401:
            raise AuthError(f"Authentication failed: {err_text}") from exc

        if status == 429:
            if has_budget_word:
                raise BudgetBlocked(f"Gateway budget limit reached: {err_text}") from exc
            raise RateLimited(f"Upstream provider rate limit: {err_text}") from exc

        if status == 403:
            if has_budget_word:
                raise BudgetBlocked(f"Gateway budget limit reached: {err_text}") from exc
            raise GatewayPolicyBlocked(f"Gateway policy rejected request: {err_text}") from exc

        if status == 400:
            if has_policy_word:
                raise GatewayPolicyBlocked(f"Gateway policy rejected request: {err_text}") from exc
            raise BadRequest(f"Bad request sent to gateway: {err_text}") from exc

        if status >= 500:
            raise ProviderDown(f"Gateway or upstream provider 5xx error ({status}): {err_text}") from exc

        # Default fallback
        raise ProviderDown(f"HTTP {status} error: {err_text}") from exc
