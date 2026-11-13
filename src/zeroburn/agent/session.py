"""Agent session state management with immutable confidentiality flag."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from zeroburn.config import ZeroBurnConfig
from zeroburn.context.read_cache import ReadCache
from zeroburn.policy.repo_flag import is_confidential


class Session:
    def __init__(
        self,
        repo_root: Path | str,
        task_text: str = "",
        config: ZeroBurnConfig | None = None,
        confidential: bool | None = None,
        user: str | None = None,
        session_id: str | None = None,
        mode: str = "zeroburn",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        
        # Confidentiality is determined once at session start and is immutable
        if confidential is not None:
            self._confidential = bool(confidential)
        else:
            self._confidential = is_confidential(self.repo_root)

        self.config = config or ZeroBurnConfig()
        self.user = user or self.config.zeroburn_user
        self.session_id = session_id or f"s_{uuid.uuid4().hex[:8]}"
        self.task_text = task_text
        self.mode = mode

        self.messages: list[dict[str, Any]] = []
        self.read_cache = ReadCache()
        self.touched_files: set[str] = set()
        self.step: int = 0

        # Turn state tracking for router tier heuristics
        self.last_turn_tools: list[str] = []
        self.last_turn_had_error: bool = False
        self.cache_stub_hits: int = 0

        # Run aggregation metrics
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.models_used: list[str] = []
        self.failovers_count: int = 0

    @property
    def confidential(self) -> bool:
        """Immutable confidentiality flag."""
        return self._confidential

    @confidential.setter
    def confidential(self, value: bool) -> None:
        raise AttributeError("Session confidentiality flag is immutable and cannot be modified.")
