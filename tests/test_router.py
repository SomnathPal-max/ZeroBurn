"""Unit tests for deterministic routing and confidential safety assertions."""
from __future__ import annotations

import pytest
from types import SimpleNamespace

from zeroburn.config import ZeroBurnConfig, ModelsConfig
from zeroburn.errors import PolicyViolation
from zeroburn.gateway.budget import Decision
from zeroburn.gateway.router import Router, RoutePlan, assert_local_only


@pytest.fixture
def config() -> ZeroBurnConfig:
    return ZeroBurnConfig(
        models=ModelsConfig(
            local="ollama/llama3.1:8b",
            light_chain=["openai/gpt-4o-mini", "ollama/llama3.1:8b"],
            heavy_chain=["openai/gpt-4o", "openai/gpt-4o-mini", "ollama/llama3.1:8b"],
        ),
        bifrost_vk_standard="sk-bf-standard",
        bifrost_vk_confidential="sk-bf-confidential",
    )


def test_confidential_session_strictly_local(config: ZeroBurnConfig) -> None:
    router = Router(config)
    session = SimpleNamespace(confidential=True, last_turn_tools=[], last_turn_had_error=False)

    for budget_decision in (Decision.OK, Decision.DOWNSHIFT, Decision.LIMIT):
        for tier in ("heavy", "light", "local_only"):
            plan = router.plan(session, tier=tier, budget_decision=budget_decision)
            assert plan.vk_name == "confidential"
            assert plan.vk_value == "sk-bf-confidential"
            # Every model in chain MUST be local
            for model in plan.chain:
                assert model.startswith("ollama/")
            assert_local_only(plan)


def test_cloud_model_injection_into_confidential_plan_fails() -> None:
    malicious_plan = RoutePlan(
        vk_name="confidential",
        vk_value="sk-bf-confidential",
        chain=["ollama/llama3.1:8b", "openai/gpt-4o"],  # Injected cloud model!
        tier="local_only",
    )
    with pytest.raises(PolicyViolation, match="Confidential safety policy violation"):
        assert_local_only(malicious_plan)


def test_normal_session_routing(config: ZeroBurnConfig) -> None:
    router = Router(config)
    session = SimpleNamespace(confidential=False, last_turn_tools=[], last_turn_had_error=False)

    # 1. OK budget, heavy tier
    plan_heavy = router.plan(session, tier="heavy", budget_decision=Decision.OK)
    assert plan_heavy.vk_name == "standard"
    assert plan_heavy.chain[0] == "openai/gpt-4o"
    assert plan_heavy.chain[-1] == "ollama/llama3.1:8b"

    # 2. OK budget, light tier
    plan_light = router.plan(session, tier="light", budget_decision=Decision.OK)
    assert plan_light.chain == ["openai/gpt-4o-mini", "ollama/llama3.1:8b"]

    # 3. DOWNSHIFT forces light chain
    plan_downshifted = router.plan(session, tier="heavy", budget_decision=Decision.DOWNSHIFT)
    assert plan_downshifted.tier == "light"
    assert plan_downshifted.chain == ["openai/gpt-4o-mini", "ollama/llama3.1:8b"]

    # 4. LIMIT forces local only
    plan_limit = router.plan(session, tier="heavy", budget_decision=Decision.LIMIT)
    assert plan_limit.tier == "local_only"
    assert plan_limit.chain == ["ollama/llama3.1:8b"]


def test_tier_selection(config: ZeroBurnConfig) -> None:
    router = Router(config)

    # Initial turn or write turn -> heavy
    session_initial = SimpleNamespace(last_turn_tools=[], last_turn_had_error=False)
    assert router.pick_tier(session_initial) == "heavy"

    # Turn after read tools only -> light (exploration)
    session_read = SimpleNamespace(
        last_turn_tools=["repo_map", "read_range"],
        last_turn_had_error=False,
    )
    assert router.pick_tier(session_read) == "light"

    # Turn after read tools but WITH error -> heavy
    session_error = SimpleNamespace(
        last_turn_tools=["read_range"],
        last_turn_had_error=True,
    )
    assert router.pick_tier(session_error) == "heavy"

    # Compaction / commit / final -> light
    assert router.pick_tier(session_initial, is_compaction=True) == "light"
    assert router.pick_tier(session_initial, is_commit=True) == "light"
    assert router.pick_tier(session_initial, is_final=True) == "light"
