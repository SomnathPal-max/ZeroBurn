"""Pre-call cost estimation and atomic budget ledger management."""
from __future__ import annotations

import os
import json
import tempfile
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from zeroburn.config import ZeroBurnConfig, BudgetConfig
from zeroburn.errors import BudgetExhausted


class Decision(str, Enum):
    OK = "OK"
    DOWNSHIFT = "DOWNSHIFT"
    LIMIT = "LIMIT"


def get_default_ledger_path() -> Path:
    if custom := os.environ.get("ZEROBURN_HOME"):
        base = Path(custom)
    else:
        base = Path.home() / ".zeroburn"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        base = Path(".zeroburn")
        base.mkdir(parents=True, exist_ok=True)
    return base / "ledger.json"


def get_current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_next_month_reset_date() -> str:
    now = datetime.now(timezone.utc)
    if now.month == 12:
        return f"{now.year + 1}-01-01"
    return f"{now.year}-{now.month + 1:02d}-01"


def estimate_tokens_and_cost(
    messages: list[dict[str, Any]],
    max_tokens: int,
    model: str,
    prices: dict[str, list[float]],
    chars_per_token: int = 4,
) -> tuple[int, float]:
    """Estimate input tokens and total USD cost for a candidate model call.
    
    Formula:
    in_tokens = total_chars / chars_per_token
    cost = (in_tokens * price_in + max_tokens * price_out) / 1e6
    """
    total_chars = 0
    for m in messages:
        if content := m.get("content"):
            total_chars += len(content)
        if role := m.get("role"):
            total_chars += len(role)
        if tool_calls := m.get("tool_calls"):
            total_chars += len(str(tool_calls))

    in_tokens = max(1, total_chars // chars_per_token)
    
    model_prices = prices.get(model, [0.0, 0.0])
    price_in = model_prices[0]
    price_out = model_prices[1] if len(model_prices) > 1 else 0.0

    cost = (in_tokens * price_in + max_tokens * price_out) / 1_000_000.0
    return in_tokens, cost


class BudgetManager:
    def __init__(self, config: ZeroBurnConfig, ledger_path: Path | None = None) -> None:
        self.config = config
        self.ledger_path = ledger_path or get_default_ledger_path()
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def load_ledger(self) -> dict[str, Any]:
        if not self.ledger_path.is_file():
            return {}
        try:
            return json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_ledger_atomic(self, data: dict[str, Any]) -> None:
        """Atomic write via tempfile and replace to prevent corruption on crash."""
        parent = self.ledger_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=parent, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2)
            temp_name = tf.name
        os.replace(temp_name, self.ledger_path)

    def get_spent_usd(self, user: str, month: str | None = None) -> float:
        m = month or get_current_month()
        ledger = self.load_ledger()
        user_data = ledger.get(user, {}).get(m, {})
        return float(user_data.get("spent_usd", 0.0))

    def get_tokens(self, user: str, month: str | None = None) -> int:
        m = month or get_current_month()
        ledger = self.load_ledger()
        user_data = ledger.get(user, {}).get(m, {})
        return int(user_data.get("tokens", 0))

    def check(self, est_cost: float, model: str, user: str) -> Decision:
        """Check proposed cost against monthly budget thresholds.
        
        Local-model calls cost 0 and never trigger LIMIT.
        """
        # Local model is free and never triggers limit
        if model.startswith("ollama/") or self.config.prices_usd_per_million.get(model, [0, 0]) == [0.0, 0.0]:
            return Decision.OK

        spent = self.get_spent_usd(user)
        projected = spent + est_cost
        limit = self.config.budget.user_limit_usd
        warn_at = limit * self.config.budget.warn_at
        downshift_at = limit * self.config.budget.downshift_at

        if projected > limit:
            return Decision.LIMIT
        if projected >= downshift_at:
            return Decision.DOWNSHIFT
        return Decision.OK

    def commit(
        self,
        user: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Record actual tokens and actual cost into atomic monthly ledger."""
        model_prices = self.config.prices_usd_per_million.get(model, [0.0, 0.0])
        price_in = model_prices[0]
        price_out = model_prices[1] if len(model_prices) > 1 else 0.0

        actual_cost = (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000.0
        total_tokens = prompt_tokens + completion_tokens

        month = get_current_month()
        ledger = self.load_ledger()
        if user not in ledger:
            ledger[user] = {}
        if month not in ledger[user]:
            ledger[user][month] = {"spent_usd": 0.0, "tokens": 0}

        ledger[user][month]["spent_usd"] = round(ledger[user][month]["spent_usd"] + actual_cost, 6)
        ledger[user][month]["tokens"] += total_tokens

        self.save_ledger_atomic(ledger)
        return actual_cost
