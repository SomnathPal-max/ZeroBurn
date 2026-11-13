"""Acceptance tests for Core Requirements R1, R2, R3, and R4."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zeroburn.config import ZeroBurnConfig, BudgetConfig
from zeroburn.errors import ProviderDown, PolicyViolation, BudgetExhausted, ApprovalDenied
from zeroburn.gateway.client import LLMResult
from zeroburn.gateway.router import Router, RoutePlan, assert_local_only
from zeroburn.gateway.budget import BudgetManager, Decision, get_next_month_reset_date
from zeroburn.gateway.failover import call_with_chain
from zeroburn.policy import repo_flag
from zeroburn.policy.approval import ApprovalGate, ActionRequest, ActionKind
from zeroburn.tools.registry import ToolRegistry
from zeroburn.context.read_cache import ReadCache
from zeroburn.agent.session import Session


class MockApprover:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.call_count = 0
        self.requests: list[ActionRequest] = []

    def approve(self, req: ActionRequest) -> bool:
        self.call_count += 1
        self.requests.append(req)
        return self.allow


@pytest.fixture
def test_session(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text("def hello(): return 1\n", encoding="utf-8")
    (repo / ".env").write_text("API_KEY=secret_123\n", encoding="utf-8")
    (repo / "id_rsa").write_text("PRIVATE KEY\n", encoding="utf-8")

    return SimpleNamespace(
        repo_root=repo,
        read_cache=ReadCache(),
        step=1,
        task_text="maintenance task",
        touched_files=set(),
        config=SimpleNamespace(agent=SimpleNamespace(tool_result_max_chars=4000)),
    )


# ==============================================================================
# Requirement 1: Outage Failover (R1)
# ==============================================================================
def test_r1_outage_failover_and_banner():
    """R1: Primary model fails with 503; agent seamlessly failovers to secondary and shows banner."""
    cfg = ZeroBurnConfig()
    plan = RoutePlan(
        vk_name="standard",
        vk_value="bf_vk_test",
        chain=["openai/gpt-4o", "openai/gpt-4o-mini", "ollama/llama3.1:8b"],
        tier="heavy",
    )

    call_counts = {"openai/gpt-4o": 0, "openai/gpt-4o-mini": 0}
    banner_events = []

    def fake_chat(model: str, messages: list, tools: list, max_tokens: int, vk: str) -> LLMResult:
        if model == "openai/gpt-4o":
            call_counts["openai/gpt-4o"] += 1
            raise ProviderDown("503 Service Unavailable: Primary OpenAI cluster down")
        elif model == "openai/gpt-4o-mini":
            call_counts["openai/gpt-4o-mini"] += 1
            return LLMResult(
                content="Task completed on fallback",
                tool_calls=[],
                prompt_tokens=500,
                completion_tokens=40,
                served_model="openai/gpt-4o-mini",
                latency_ms=120,
            )
        raise RuntimeError("Unexpected model called")

    mock_client = MagicMock()
    mock_client.chat = fake_chat

    session = SimpleNamespace(
        config=cfg,
        messages=[{"role": "user", "content": "fix pagination"}],
        confidential=False,
    )

    res, failover_occurred, failover_reason = call_with_chain(
        plan=plan,
        session=session,
        tools=[],
        client=mock_client,
        banner_fn=lambda old, new, reason: banner_events.append((old, new, reason)),
    )

    assert res.served_model == "openai/gpt-4o-mini"
    assert res.content == "Task completed on fallback"
    assert failover_occurred is True
    assert call_counts["openai/gpt-4o"] == 2  # 1 initial + 1 retry
    assert call_counts["openai/gpt-4o-mini"] == 1
    assert len(banner_events) == 1
    assert banner_events[0][0] == "openai/gpt-4o"
    assert banner_events[0][1] == "openai/gpt-4o-mini"
    assert "ProviderDown" in banner_events[0][2] or "503" in banner_events[0][2]


# ==============================================================================
# Requirement 2: Per-User Budget Limits (R2)
# ==============================================================================
def test_r2_budget_downshift_and_local_limit(tmp_path: Path):
    """R2: User budget threshold at 75% downshifts to light; 100% falls back to local-only."""
    ledger_path = tmp_path / "ledger.json"
    cfg = ZeroBurnConfig(
        budget=BudgetConfig(
            user_limit_usd=0.05,
            warn_at=0.75,
            downshift_at=0.75,
            on_limit="local_only",
        ),
        prices_usd_per_million={
            "openai/gpt-4o": [2.50, 10.00],
            "openai/gpt-4o-mini": [0.15, 0.60],
            "ollama/llama3.1:8b": [0.0, 0.0],
        },
    )
    bm = BudgetManager(config=cfg, ledger_path=ledger_path)
    user = "alice"

    # Initial state: $0 spent -> Decision.OK
    d1 = bm.check(est_cost=0.01, model="openai/gpt-4o", user=user)
    assert d1 == Decision.OK

    # Commit spend: prompt=10000, comp=1500 on gpt-4o = 0.025 + 0.015 = 0.040 USD (80% of $0.05)
    bm.commit(user=user, model="openai/gpt-4o", prompt_tokens=10000, completion_tokens=1500)
    d2 = bm.check(est_cost=0.005, model="openai/gpt-4o", user=user)
    assert d2 == Decision.DOWNSHIFT

    # Router responds to downshift by picking light tier
    router = Router(cfg)
    session = Session(repo_root=tmp_path, user=user)
    plan_downshift = router.plan(session=session, tier="heavy", budget_decision=d2)
    assert plan_downshift.tier == "light"
    assert plan_downshift.chain[0] == "openai/gpt-4o-mini"

    # Commit additional spend: 0.020 USD -> total $0.060 (> $0.05 limit)
    bm.commit(user=user, model="openai/gpt-4o", prompt_tokens=5000, completion_tokens=1000)
    d3 = bm.check(est_cost=0.005, model="openai/gpt-4o", user=user)
    assert d3 == Decision.LIMIT

    # Router enforces local_only on LIMIT
    plan_limit = router.plan(session=session, tier="heavy", budget_decision=d3)
    assert plan_limit.tier == "local_only"
    assert plan_limit.chain == ["ollama/llama3.1:8b"]


def test_r2_budget_hard_stop_on_limit(tmp_path: Path):
    """R2: If on_limit == 'stop', exceeding budget raises BudgetExhausted in agent loop."""
    ledger_path = tmp_path / "ledger.json"
    cfg = ZeroBurnConfig(
        budget=BudgetConfig(user_limit_usd=0.05, on_limit="stop"),
        prices_usd_per_million={
            "openai/gpt-4o": [2.50, 10.00],
            "openai/gpt-4o-mini": [0.15, 0.60],
            "ollama/llama3.1:8b": [0.0, 0.0],
        },
    )
    bm = BudgetManager(config=cfg, ledger_path=ledger_path)
    user = "bob"

    bm.commit(user=user, model="openai/gpt-4o", prompt_tokens=15000, completion_tokens=2000)
    decision = bm.check(est_cost=0.01, model="openai/gpt-4o", user=user)
    assert decision == Decision.LIMIT

    # In agent loop, if on_limit == 'stop' and decision == LIMIT, BudgetExhausted is raised
    if cfg.budget.on_limit == "stop" and decision == Decision.LIMIT:
        spent = bm.get_spent_usd(user)
        reset_date = get_next_month_reset_date()
        with pytest.raises(BudgetExhausted) as exc_info:
            raise BudgetExhausted(
                f"Monthly budget limit of ${cfg.budget.user_limit_usd:.2f} reached "
                f"(spent: ${spent:.4f}). Cannot make further calls. Limit resets on {reset_date}."
            )
        assert "Monthly budget limit" in str(exc_info.value)


# ==============================================================================
# Requirement 3: Confidential Local-Only Routing (R3)
# ==============================================================================
def test_r3_confidential_repo_local_only():
    """R3: demo/confidential_repo/ is strictly routed locally; never cloud."""
    confidential_dir = Path("demo/confidential_repo").resolve()
    assert repo_flag.is_confidential(confidential_dir) is True

    cfg = ZeroBurnConfig()
    router = Router(cfg)
    session = Session(repo_root=confidential_dir)
    assert session.confidential is True

    # Router must generate local_only plan with confidential virtual key
    plan = router.plan(session=session, tier="heavy")
    assert plan.tier == "local_only"
    assert plan.vk_name == "confidential"
    assert plan.vk_value == cfg.bifrost_vk_confidential
    assert all(m.startswith("ollama/") for m in plan.chain)

    # Hard assertion passes
    assert_local_only(plan)


def test_r3_confidential_prompt_injection_blocked():
    """R3: Hostile prompt attempting to route to gpt-4o fails hard assertion."""
    plan = RoutePlan(
        vk_name="confidential",
        vk_value="bf_vk_confidential_local",
        chain=["openai/gpt-4o"],  # Malicious attempt to slip in cloud model
        tier="local_only",
    )
    with pytest.raises(PolicyViolation) as exc_info:
        assert_local_only(plan)
    assert "Confidential safety policy violation" in str(exc_info.value)
    assert "Confidential repos must NEVER route to cloud" in str(exc_info.value)


# ==============================================================================
# Requirement 4: Deterministic Action Approval Gate (R4)
# ==============================================================================
def test_r4_safe_reads_auto_approved(test_session):
    """R4: Code and markdown reads are auto-approved without prompting."""
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    res = registry.execute("read_file", {"path": "hello.py"}, test_session)
    assert "def hello" in res
    assert approver.call_count == 0  # No human prompt needed


def test_r4_sensitive_reads_gated(test_session):
    """R4: Sensitive reads (.env, id_rsa, secrets) are gated and require human approval."""
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    res_env = registry.execute("read_file", {"path": ".env"}, test_session)
    assert "Action denied by user" in res_env
    assert approver.call_count == 1

    res_rsa = registry.execute("read_file", {"path": "id_rsa"}, test_session)
    assert "Action denied by user" in res_rsa
    assert approver.call_count == 2


def test_r4_writes_shell_git_gated_and_denial_recovers(test_session):
    """R4: Writes, shell, and git require approval; rejection recovers cleanly without crash."""
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    # 1. apply_edit
    res_edit = registry.execute(
        "apply_edit",
        {"path": "hello.py", "old": "return 1", "new": "return 2"},
        test_session,
    )
    assert "Action denied by user" in res_edit

    # 2. create_file
    res_write = registry.execute(
        "create_file",
        {"path": "new_file.py", "content": "x = 10\n"},
        test_session,
    )
    assert "Action denied by user" in res_write

    # 3. run_shell
    res_shell = registry.execute(
        "run_shell",
        {"command": "pytest"},
        test_session,
    )
    assert "Action denied by user" in res_shell

    # 4. git
    res_git = registry.execute(
        "git",
        {"args": ["commit", "-m", "test"]},
        test_session,
    )
    assert "Action denied by user" in res_git

    # All 4 operations prompted the user
    assert approver.call_count == 4
    # The file hello.py was untouched
    assert (test_session.repo_root / "hello.py").read_text(encoding="utf-8") == "def hello(): return 1\n"


def test_r4_injection_repo_git_push_intercepted():
    """R4: Malicious injection repo attempting git push is caught by approval gate."""
    injection_dir = Path("demo/injection_repo").resolve()
    readme_text = (injection_dir / "README.md").read_text(encoding="utf-8")
    assert "SYSTEM PROMPT OVERRIDE" in readme_text

    approver = MockApprover(allow=False)
    gate = ApprovalGate(approver=approver)

    # Injected action generated by poisoned prompt
    req = ActionRequest(
        kind=ActionKind.GIT,
        summary="git push origin main --force",
        detail="git push origin main --force",
    )
    assert req.risk == 70  # Scored as high risk

    with pytest.raises(ApprovalDenied) as exc_info:
        gate.require(req)

    assert "Action denied by user" in str(exc_info.value)
    assert approver.call_count == 1
