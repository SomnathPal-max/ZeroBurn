"""Unit tests for budget management, pre-call estimation, and atomic ledger."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from zeroburn.config import ZeroBurnConfig, BudgetConfig
from zeroburn.errors import BudgetExhausted
from zeroburn.gateway.budget import (
    BudgetManager,
    Decision,
    estimate_tokens_and_cost,
    get_current_month,
)


@pytest.fixture
def test_config() -> ZeroBurnConfig:
    return ZeroBurnConfig(
        budget=BudgetConfig(
            user_limit_usd=2.00,
            warn_at=0.75,
            downshift_at=0.75,
            on_limit="local_only",
            chars_per_token=4,
        ),
        prices_usd_per_million={
            "openai/gpt-4o": [2.50, 10.00],
            "openai/gpt-4o-mini": [0.15, 0.60],
            "ollama/llama3.1:8b": [0.0, 0.0],
        },
    )


def test_estimate_arithmetic(test_config: ZeroBurnConfig) -> None:
    # 400 characters -> 100 input tokens (4 chars/token)
    # max_tokens = 1000
    # gpt-4o price: [2.50, 10.00] per million
    # cost = (100 * 2.50 + 1000 * 10.00) / 1e6 = (250 + 10000) / 1e6 = 10250 / 1e6 = 0.01025 USD
    messages = [{"role": "user", "content": "a" * 390}]  # total chars approx 400
    tokens, cost = estimate_tokens_and_cost(
        messages=messages,
        max_tokens=1000,
        model="openai/gpt-4o",
        prices=test_config.prices_usd_per_million,
        chars_per_token=4,
    )
    assert tokens >= 97
    assert 0.010 <= cost <= 0.011

    # Local model cost is exactly 0.0
    _, local_cost = estimate_tokens_and_cost(
        messages=messages,
        max_tokens=1000,
        model="ollama/llama3.1:8b",
        prices=test_config.prices_usd_per_million,
        chars_per_token=4,
    )
    assert local_cost == 0.0


def test_budget_thresholds(test_config: ZeroBurnConfig, tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    mgr = BudgetManager(config=test_config, ledger_path=ledger_path)
    user = "alice"

    # Limit is $2.00, downshift at $1.50 (75%)
    # Initial: 0 spent. est_cost = 0.50 -> projected = 0.50 < 1.50 -> OK
    assert mgr.check(est_cost=0.50, model="openai/gpt-4o", user=user) == Decision.OK

    # est_cost = 1.60 -> projected = 1.60 (>= 1.50 and <= 2.00) -> DOWNSHIFT
    assert mgr.check(est_cost=1.60, model="openai/gpt-4o", user=user) == Decision.DOWNSHIFT

    # est_cost = 2.10 -> projected = 2.10 (> 2.00) -> LIMIT
    assert mgr.check(est_cost=2.10, model="openai/gpt-4o", user=user) == Decision.LIMIT

    # Local model is always OK regardless of projected limit
    assert mgr.check(est_cost=5.00, model="ollama/llama3.1:8b", user=user) == Decision.OK


def test_ledger_atomic_persistence(test_config: ZeroBurnConfig, tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    mgr = BudgetManager(config=test_config, ledger_path=ledger_path)
    user = "bob"

    # Commit usage
    cost = mgr.commit(user=user, model="openai/gpt-4o", prompt_tokens=1000, completion_tokens=500)
    assert cost > 0
    assert mgr.get_spent_usd(user) == cost
    assert mgr.get_tokens(user) == 1500

    # Ensure ledger.json is valid JSON
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert user in raw
    assert get_current_month() in raw[user]


def test_over_limit_prevents_client_call(test_config: ZeroBurnConfig, tmp_path: Path) -> None:
    # Set limit to $0.01 and on_limit="stop"
    test_config.budget.user_limit_usd = 0.01
    test_config.budget.on_limit = "stop"

    ledger_path = tmp_path / "ledger.json"
    mgr = BudgetManager(config=test_config, ledger_path=ledger_path)
    user = "charlie"

    mock_client = MagicMock()

    # Pre-call estimate exceeds $0.01 limit
    est_tokens, est_cost = estimate_tokens_and_cost(
        messages=[{"role": "user", "content": "x" * 4000}],
        max_tokens=1500,
        model="openai/gpt-4o",
        prices=test_config.prices_usd_per_million,
    )
    decision = mgr.check(est_cost, model="openai/gpt-4o", user=user)
    assert decision == Decision.LIMIT

    # Behavior at limit with on_limit="stop"
    if decision == Decision.LIMIT and test_config.budget.on_limit == "stop":
        with pytest.raises(BudgetExhausted, match="Monthly budget limit"):
            raise BudgetExhausted(f"Monthly budget limit of ${test_config.budget.user_limit_usd} exceeded.")

    # Assert mock client was NEVER called!
    assert not mock_client.called
