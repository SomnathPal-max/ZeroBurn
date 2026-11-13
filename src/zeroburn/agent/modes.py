"""Execution modes: ZeroBurn vs Naive Baseline."""
from __future__ import annotations

from dataclasses import dataclass
from zeroburn.agent.prompts import SYSTEM_PROMPT
from zeroburn.policy.approval import ApprovalGate


@dataclass(frozen=True)
class ModeSettings:
    name: str
    use_repo_map: bool
    read_file_capped: bool
    use_read_cache: bool
    use_compaction: bool
    use_light_tier: bool


ZEROBURN_MODE = ModeSettings(
    name="zeroburn",
    use_repo_map=True,
    read_file_capped=True,
    use_read_cache=True,
    use_compaction=True,
    use_light_tier=True,
)

NAIVE_MODE = ModeSettings(
    name="naive",
    use_repo_map=False,
    read_file_capped=False,
    use_read_cache=False,
    use_compaction=False,
    use_light_tier=False,
)


def get_mode_settings(mode: str) -> ModeSettings:
    if mode.lower() == "naive":
        return NAIVE_MODE
    return ZEROBURN_MODE
