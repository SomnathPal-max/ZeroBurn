"""Agent execution loop coordinating routing, budgeting, failover, and tools."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zeroburn.config import ZeroBurnConfig, load_config
from zeroburn.errors import BudgetExhausted
from zeroburn.agent.prompts import SYSTEM_PROMPT
from zeroburn.agent.session import Session
from zeroburn.gateway.router import Router, assert_local_only
from zeroburn.gateway.budget import (
    BudgetManager,
    Decision,
    estimate_tokens_and_cost,
    get_next_month_reset_date,
)
from zeroburn.gateway.client import GatewayClient
from zeroburn.gateway.failover import call_with_chain
from zeroburn.gateway.usage import log_usage
from zeroburn.tools.registry import ToolRegistry
from zeroburn.policy.approval import ApprovalGate, Approver
from zeroburn.context.repo_map import generate_repo_map
from zeroburn.ui.console import print_task_footer, console


def run_task(
    task: str,
    repo: Path | str,
    mode: str = "zeroburn",
    config: ZeroBurnConfig | None = None,
    approver: Approver | None = None,
    client: GatewayClient | None = None,
    print_footer: bool = True,
) -> Session:
    """Run an autonomous task through the ZeroBurn agent loop."""
    repo_root = Path(repo).resolve()
    cfg = config or load_config(repo_root)

    session = Session(
        repo_root=repo_root,
        task_text=task,
        config=cfg,
        mode=mode,
    )

    gate = ApprovalGate(approver=approver)
    registry = ToolRegistry(gate=gate)
    router = Router(cfg)
    budget_mgr = BudgetManager(cfg)

    # 1. Initialize system prompt and user task
    session.messages.append({"role": "system", "content": SYSTEM_PROMPT})
    session.messages.append({"role": "user", "content": task})

    # In zeroburn mode, inject initial repo map; in naive mode, skip repo map
    if mode == "zeroburn":
        initial_map = generate_repo_map(
            repo_root=session.repo_root,
            task_text=task,
            max_tokens=cfg.agent.max_tokens_per_call,
            chars_per_token=cfg.budget.chars_per_token,
        )
        session.messages.append({"role": "user", "content": f"Repository map:\n{initial_map}"})

    # 2. Main Agent Execution Loop
    for step in range(cfg.agent.max_steps):
        session.step = step + 1

        # Check compaction hook if registered on session
        compact_fn = getattr(session, "compact_if_needed", None)
        if compact_fn and mode == "zeroburn":
            compact_fn()

        # Step 7: Tier selection (naive mode never uses light tier)
        if mode == "naive":
            tier = "heavy"
        else:
            tier = router.pick_tier(session)

        # Step 6: Pre-call budget estimation and ledger check
        initial_plan = router.plan(session, tier=tier, budget_decision=Decision.OK)
        target_model = initial_plan.chain[0]

        est_tokens, est_cost = estimate_tokens_and_cost(
            messages=session.messages,
            max_tokens=cfg.agent.max_tokens_per_call,
            model=target_model,
            prices=cfg.prices_usd_per_million,
            chars_per_token=cfg.budget.chars_per_token,
        )

        decision = budget_mgr.check(est_cost=est_cost, model=target_model, user=session.user)

        if decision == Decision.LIMIT:
            if cfg.budget.on_limit == "local_only":
                console.print(
                    "[bold yellow]Budget Notice: Monthly budget limit reached. Routing to local model (cost $0).[/bold yellow]"
                )
                plan = router.plan(session, tier=tier, budget_decision=Decision.LIMIT)
            else:
                spent = budget_mgr.get_spent_usd(session.user)
                reset_date = get_next_month_reset_date()
                raise BudgetExhausted(
                    f"Monthly budget limit of ${cfg.budget.user_limit_usd:.2f} reached "
                    f"(spent: ${spent:.4f}). Cannot make further calls. Limit resets on {reset_date}."
                )
        elif decision == Decision.DOWNSHIFT:
            plan = router.plan(session, tier="light", budget_decision=Decision.DOWNSHIFT)
        else:
            plan = initial_plan

        if session.confidential:
            assert_local_only(plan)

        # Step 8: Call model with failover chain
        res, failover_occurred, failover_reason = call_with_chain(
            plan=plan,
            session=session,
            tools=registry.get_schemas(),
            client=client,
        )

        # Record actual usage and update ledger
        actual_cost = budget_mgr.commit(
            user=session.user,
            model=res.served_model,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
        )

        # Update session totals
        session.total_prompt_tokens += res.prompt_tokens
        session.total_completion_tokens += res.completion_tokens
        session.total_cost_usd += actual_cost
        if res.served_model not in session.models_used:
            session.models_used.append(res.served_model)
        if failover_occurred:
            session.failovers_count += 1

        tool_names = [tc.name for tc in res.tool_calls]
        log_usage(
            session_id=session.session_id,
            user=session.user,
            step=session.step,
            vk=plan.vk_name,
            tier=plan.tier,
            requested_model=target_model,
            served_model=res.served_model,
            prompt_tokens=res.prompt_tokens,
            completion_tokens=res.completion_tokens,
            est_cost_usd=actual_cost,
            latency_ms=res.latency_ms,
            failover=failover_occurred,
            failover_reason=failover_reason,
            cache_stub_hits=session.cache_stub_hits,
            tool_calls=tool_names,
            mode=mode,
        )

        session.last_turn_tools = tool_names
        session.last_turn_had_error = False

        # If no tool calls returned, agent finished its output
        if not res.tool_calls:
            if res.content:
                session.messages.append({"role": "assistant", "content": res.content})
            break

        # Append assistant message with tool calls
        formatted_calls = []
        for tc in res.tool_calls:
            formatted_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.args),
                    },
                }
            )
        session.messages.append(
            {
                "role": "assistant",
                "content": res.content or "",
                "tool_calls": formatted_calls,
            }
        )

        # Execute each tool call
        finish_called = False
        for tc in res.tool_calls:
            tool_output = registry.execute(tc.name, tc.args, session)
            session.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_output,
                }
            )
            if "Tool execution failed" in tool_output or "Error:" in tool_output:
                session.last_turn_had_error = True

            # Freshness check hook (Step 11 integration)
            if tc.name == "run_shell":
                from zeroburn.freshness.tavily_client import maybe_freshness_lookup
                maybe_freshness_lookup(tool_output, session)

            if tc.name == "finish":
                finish_called = True
                break

        if finish_called:
            break

    if print_footer:
        print_task_footer(
            steps=session.step,
            prompt_tokens=session.total_prompt_tokens,
            completion_tokens=session.total_completion_tokens,
            cost_usd=session.total_cost_usd,
            models_used=session.models_used,
            failovers=session.failovers_count,
        )

    return session
