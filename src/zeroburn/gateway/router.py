"""Deterministic model router and confidential routing enforcement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zeroburn.config import ZeroBurnConfig
from zeroburn.errors import PolicyViolation
from zeroburn.gateway.budget import Decision


@dataclass
class RoutePlan:
    vk_name: str  # "standard" | "confidential"
    vk_value: str
    chain: list[str]
    tier: str     # "heavy" | "light" | "local_only"


def assert_local_only(plan: RoutePlan) -> None:
    """Hard assertion that every model in the chain starts with 'ollama/'.
    
    Raises PolicyViolation if any cloud model is present in a confidential plan.
    Must be executed on every call, not just once.
    """
    for model in plan.chain:
        if not model.startswith("ollama/"):
            raise PolicyViolation(
                f"Confidential safety policy violation: non-local model '{model}' "
                f"found in confidential route plan. Confidential repos must NEVER route to cloud."
            )


class Router:
    def __init__(self, config: ZeroBurnConfig) -> None:
        self.config = config

    def pick_tier(
        self,
        session: Any,
        is_compaction: bool = False,
        is_commit: bool = False,
        is_final: bool = False,
    ) -> str:
        """Select light or heavy tier deterministically without reading prompt text."""
        if is_compaction or is_commit or is_final:
            return "light"

        # Exploration turn optimization:
        # If previous turn used only read tools and produced no errors, use light tier
        if self.config.agent.explore_with_light:
            last_tools = getattr(session, "last_turn_tools", [])
            last_has_error = getattr(session, "last_turn_had_error", False)
            read_tool_names = {"repo_map", "search_code", "read_range", "get_symbol", "read_file"}
            if last_tools and not last_has_error and all(t in read_tool_names for t in last_tools):
                return "light"

        return "heavy"

    def plan(
        self,
        session: Any,
        tier: str = "heavy",
        budget_decision: Decision = Decision.OK,
    ) -> RoutePlan:
        """Construct the RoutePlan enforcing confidentiality and budget constraints."""
        is_confidential = getattr(session, "confidential", False)

        # 1. Confidential Session: strictly local only
        if is_confidential:
            chain = [self.config.models.local]
            plan = RoutePlan(
                vk_name="confidential",
                vk_value=self.config.bifrost_vk_confidential,
                chain=chain,
                tier="local_only",
            )
            assert_local_only(plan)
            return plan

        # 2. Normal Session: check budget constraints
        if budget_decision == Decision.LIMIT:
            # Over budget: fallback to local model only
            chain = [self.config.models.local]
            return RoutePlan(
                vk_name="standard",
                vk_value=self.config.bifrost_vk_standard,
                chain=chain,
                tier="local_only",
            )

        if budget_decision == Decision.DOWNSHIFT:
            # Force light tier when downshifted
            tier = "light"

        if tier == "light":
            base_chain = list(self.config.models.light_chain)
        else:
            base_chain = list(self.config.models.heavy_chain)

        # Always append local model as last-resort fallback
        if self.config.models.local not in base_chain:
            base_chain.append(self.config.models.local)

        return RoutePlan(
            vk_name="standard",
            vk_value=self.config.bifrost_vk_standard,
            chain=base_chain,
            tier=tier,
        )
