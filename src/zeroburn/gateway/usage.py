"""Usage logging appending JSON lines to usage.jsonl."""
from __future__ import annotations

import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any


def get_default_usage_path() -> Path:
    if custom := os.environ.get("ZEROBURN_HOME"):
        base = Path(custom)
    else:
        base = Path.home() / ".zeroburn"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        base = Path(".zeroburn")
        base.mkdir(parents=True, exist_ok=True)
    return base / "usage.jsonl"


def log_usage(
    session_id: str,
    user: str,
    step: int,
    vk: str,
    tier: str,
    requested_model: str,
    served_model: str,
    prompt_tokens: int,
    completion_tokens: int,
    est_cost_usd: float,
    latency_ms: int,
    failover: bool = False,
    failover_reason: str | None = None,
    cache_stub_hits: int = 0,
    tool_calls: list[str] | None = None,
    mode: str = "zeroburn",
    usage_path: Path | None = None,
) -> dict[str, Any]:
    """Append a structured usage record to usage.jsonl."""
    target_path = usage_path or get_default_usage_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_id": session_id,
        "user": user,
        "step": step,
        "vk": vk,
        "tier": tier,
        "requested_model": requested_model,
        "served_model": served_model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "est_cost_usd": round(est_cost_usd, 6),
        "latency_ms": latency_ms,
        "failover": failover,
        "failover_reason": failover_reason,
        "cache_stub_hits": cache_stub_hits,
        "tool_calls": tool_calls or [],
        "mode": mode,
    }

    line = json.dumps(record) + "\n"
    with open(target_path, "a", encoding="utf-8") as f:
        f.write(line)

    return record


def read_usage(usage_path: Path | None = None) -> list[dict[str, Any]]:
    path = usage_path or get_default_usage_path()
    if not path.is_file():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    return records
