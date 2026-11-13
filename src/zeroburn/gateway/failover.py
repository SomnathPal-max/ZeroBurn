"""Session-safe model failover chain with retry and visible user notifications."""
from __future__ import annotations

import time
from typing import Any, Callable

from zeroburn.gateway.router import RoutePlan, assert_local_only
from zeroburn.gateway.client import GatewayClient, LLMResult
from zeroburn.ui.console import print_model_switch_banner
from zeroburn.errors import (
    RateLimited,
    ProviderDown,
    BudgetBlocked,
    GatewayPolicyBlocked,
    BadRequest,
    AuthError,
)


def call_with_chain(
    plan: RoutePlan,
    session: Any,
    tools: list[dict[str, Any]] | None = None,
    client: GatewayClient | None = None,
    banner_fn: Callable[[str, str, str], None] | None = None,
) -> tuple[LLMResult, bool, str | None]:
    """Execute model call across plan.chain with retry and failover.
    
    Returns (LLMResult, failover_flag, failover_reason).
    """
    # If confidential, hard assert again on every call
    if plan.vk_name == "confidential":
        assert_local_only(plan)

    cfg = getattr(session, "config", None)
    retries_per_model = cfg.failover.retries_per_model if cfg else 1
    backoff_seconds = cfg.failover.backoff_seconds if cfg else 1.0
    max_tokens = cfg.agent.max_tokens_per_call if cfg else 1500

    gw_client = client or GatewayClient(
        base_url=cfg.bifrost_url if cfg else "http://localhost:8080/v1",
        timeout_s=cfg.failover.request_timeout_s if cfg else 60.0,
    )
    banner = banner_fn or print_model_switch_banner

    failover_occurred = False
    failover_reason: str | None = None

    chain = plan.chain
    for idx, model in enumerate(chain):
        # Try model up to 1 + retries_per_model times
        for attempt in range(1 + retries_per_model):
            try:
                result = gw_client.chat(
                    model=model,
                    messages=session.messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    vk=plan.vk_value,
                )
                return result, failover_occurred, failover_reason

            except (RateLimited, ProviderDown) as exc:
                is_last_attempt = attempt == retries_per_model
                if not is_last_attempt:
                    time.sleep(backoff_seconds)
                    continue

                # Model exhausted
                failover_occurred = True
                failover_reason = f"{exc.__class__.__name__}: {exc}"

                has_next = idx + 1 < len(chain)
                if has_next:
                    next_model = chain[idx + 1]
                    banner(model, next_model, failover_reason)

                    # Check context limits for the next model
                    if cfg and next_model in cfg.context_limits:
                        next_limit = cfg.context_limits[next_model]
                        # Trigger compaction if compact_if_needed hook exists on session
                        compact_fn = getattr(session, "compact_if_needed", None)
                        if compact_fn:
                            compact_fn(target_token_limit=next_limit)
                    break
                else:
                    # No more models
                    if plan.vk_name == "confidential":
                        raise ProviderDown(
                            "All local models failed in confidential session. Cannot failover to cloud."
                        ) from exc
                    raise ProviderDown(
                        f"All models in fallback chain {chain} failed. Last error: {exc}"
                    ) from exc

            except (BudgetBlocked, GatewayPolicyBlocked, BadRequest, AuthError):
                # These are NOT failover triggers; propagate immediately
                raise
            except Exception as exc:
                raise ProviderDown(f"Unexpected error calling model {model}: {exc}") from exc

    raise ProviderDown(f"Failed to obtain response across chain: {chain}")
