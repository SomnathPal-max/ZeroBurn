"""Unit tests for failover chain, retry logic, and user notifications."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace

from zeroburn.config import ZeroBurnConfig, FailoverConfig
from zeroburn.errors import (
    ProviderDown,
    RateLimited,
    BudgetBlocked,
    PolicyViolation,
)
from zeroburn.gateway.client import LLMResult
from zeroburn.gateway.router import RoutePlan
from zeroburn.gateway.failover import call_with_chain


@pytest.fixture
def session():
    cfg = ZeroBurnConfig(
        failover=FailoverConfig(retries_per_model=1, backoff_seconds=0.01),
    )
    return SimpleNamespace(
        messages=[{"role": "user", "content": "hello"}],
        config=cfg,
    )


def test_503_failover_banner_and_success(session) -> None:
    plan = RoutePlan(
        vk_name="standard",
        vk_value="sk-bf-standard",
        chain=["openai/gpt-4o", "openai/gpt-4o-mini"],
        tier="heavy",
    )

    banners_printed: list[tuple[str, str, str]] = []
    def mock_banner(old_m: str, new_m: str, reason: str) -> None:
        banners_printed.append((old_m, new_m, reason))

    mock_client = MagicMock()
    # gpt-4o fails twice (initial + 1 retry) with ProviderDown (503)
    # gpt-4o-mini succeeds
    res_b = LLMResult(
        content="success from mini",
        tool_calls=[],
        prompt_tokens=10,
        completion_tokens=5,
        served_model="openai/gpt-4o-mini",
        latency_ms=100,
    )
    mock_client.chat.side_effect = [
        ProviderDown("HTTP 503 Service Unavailable"),
        ProviderDown("HTTP 503 Service Unavailable"),
        res_b,
    ]

    res, failover_occurred, reason = call_with_chain(
        plan=plan,
        session=session,
        client=mock_client,
        banner_fn=mock_banner,
    )

    assert res.served_model == "openai/gpt-4o-mini"
    assert res.content == "success from mini"
    assert failover_occurred is True
    assert "ProviderDown" in str(reason)
    assert len(banners_printed) == 1
    assert banners_printed[0][0] == "openai/gpt-4o"
    assert banners_printed[0][1] == "openai/gpt-4o-mini"
    assert mock_client.chat.call_count == 3


def test_429_retried_before_switching(session) -> None:
    plan = RoutePlan(
        vk_name="standard",
        vk_value="sk-bf-standard",
        chain=["openai/gpt-4o", "ollama/llama3.1:8b"],
        tier="heavy",
    )

    mock_client = MagicMock()
    res_local = LLMResult(
        content="success from local",
        tool_calls=[],
        prompt_tokens=10,
        completion_tokens=5,
        served_model="ollama/llama3.1:8b",
        latency_ms=50,
    )

    # 429 once, 429 twice (exhausted retries on gpt-4o), then local succeeds
    mock_client.chat.side_effect = [
        RateLimited("HTTP 429 Too Many Requests"),
        RateLimited("HTTP 429 Too Many Requests"),
        res_local,
    ]

    res, failover_occurred, _ = call_with_chain(
        plan=plan,
        session=session,
        client=mock_client,
        banner_fn=lambda *args, **kwargs: None,
    )

    assert res.served_model == "ollama/llama3.1:8b"
    assert failover_occurred is True
    # 2 calls to gpt-4o, 1 call to llama
    assert mock_client.chat.call_count == 3


def test_all_models_down_raises_readable_error(session) -> None:
    plan = RoutePlan(
        vk_name="standard",
        vk_value="sk-bf-standard",
        chain=["openai/gpt-4o", "ollama/llama3.1:8b"],
        tier="heavy",
    )

    mock_client = MagicMock()
    mock_client.chat.side_effect = ProviderDown("Connection failed")

    with pytest.raises(ProviderDown, match="All models in fallback chain"):
        call_with_chain(
            plan=plan,
            session=session,
            client=mock_client,
            banner_fn=lambda *args, **kwargs: None,
        )


def test_confidential_chain_never_contains_cloud_model(session) -> None:
    # Attempting to call with cloud model in confidential plan
    bad_conf_plan = RoutePlan(
        vk_name="confidential",
        vk_value="sk-bf-confidential",
        chain=["openai/gpt-4o"],  # Cloud model!
        tier="local_only",
    )

    mock_client = MagicMock()
    with pytest.raises(PolicyViolation, match="Confidential safety policy violation"):
        call_with_chain(plan=bad_conf_plan, session=session, client=mock_client)

    # Assert client was never called
    assert not mock_client.chat.called


def test_budget_blocked_does_not_failover(session) -> None:
    plan = RoutePlan(
        vk_name="standard",
        vk_value="sk-bf-standard",
        chain=["openai/gpt-4o", "openai/gpt-4o-mini"],
        tier="heavy",
    )

    mock_client = MagicMock()
    mock_client.chat.side_effect = BudgetBlocked("Monthly budget reached")

    with pytest.raises(BudgetBlocked):
        call_with_chain(plan=plan, session=session, client=mock_client)

    # Must NOT failover to next model
    assert mock_client.chat.call_count == 1
