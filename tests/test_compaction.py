"""Unit tests for context compaction and naive baseline mode."""
from __future__ import annotations

import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from zeroburn.config import ZeroBurnConfig, AgentConfig
from zeroburn.context.compaction import compact_messages
from zeroburn.context.read_cache import ReadCache
from zeroburn.agent.loop import run_task
from zeroburn.agent.modes import get_mode_settings, NAIVE_MODE, ZEROBURN_MODE
from zeroburn.gateway.client import LLMResult, ToolCall
from zeroburn.policy.approval import ActionRequest


class DenyAllApprover:
    def approve(self, req: ActionRequest) -> bool:
        return False


def test_compaction_preserves_head_tail_and_invalidates_cache() -> None:
    cache = ReadCache()
    # Cache an entry for models.py
    cache.get_stub_or_record("app/models.py", 10, 40, "code lines", turn=1)
    assert len(cache) == 1

    # Construct message list with > 6 messages
    messages = [
        {"role": "system", "content": "You are ZeroBurn"},      # Index 0 (Head)
        {"role": "user", "content": "fix bug in models.py"},     # Index 1 (Head)
        {
            "role": "tool",                                       # Index 2 (Eligible for elision)
            "content": "<tool_result name=read_range>\napp/models.py:\n" + ("x" * 2000) + "\n</tool_result>",
        },
        {"role": "assistant", "content": "I see the bug."},      # Index 3
        {"role": "user", "content": "please apply fix"},         # Index 4 (Tail 4)
        {"role": "assistant", "content": "fixing now..."},       # Index 5 (Tail 3)
        {"role": "tool", "content": "<tool_result name=apply_edit>\nSuccess\n</tool_result>"}, # Index 6 (Tail 2)
        {"role": "assistant", "content": "done"},                # Index 7 (Tail 1)
    ]

    compacted, elisions = compact_messages(
        messages=messages,
        read_cache=cache,
        compact_at_tokens=200,  # Force compaction threshold
    )

    assert elisions == 1
    assert len(compacted) == len(messages)
    # Head preserved
    assert compacted[0]["role"] == "system"
    assert compacted[1]["content"] == "fix bug in models.py"
    # Index 2 elided with one-line stub
    assert "[elided: read_range app/models.py" in compacted[2]["content"]
    assert "re-read if needed" in compacted[2]["content"]
    # Tail 4 preserved
    assert compacted[4]["content"] == "please apply fix"
    assert compacted[7]["content"] == "done"

    # Verify cache for models.py was invalidated!
    assert len(cache) == 0


def test_naive_mode_settings() -> None:
    settings_z = get_mode_settings("zeroburn")
    settings_n = get_mode_settings("naive")

    assert settings_z.use_repo_map is True
    assert settings_z.use_light_tier is True
    assert settings_z.read_file_capped is True

    assert settings_n.use_repo_map is False
    assert settings_n.use_light_tier is False
    assert settings_n.read_file_capped is False


def test_both_modes_block_unapproved_write(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target_file = repo / "data.txt"
    target_file.write_text("original content", encoding="utf-8")

    approver = DenyAllApprover()
    mock_client = MagicMock()

    # Tool call requesting edit
    call_edit = LLMResult(
        content="Editing file",
        tool_calls=[
            ToolCall(
                id="call_edit",
                name="apply_edit",
                args={"path": "data.txt", "old": "original", "new": "hacked"},
            )
        ],
        prompt_tokens=100,
        completion_tokens=20,
        served_model="openai/gpt-4o",
        latency_ms=100,
    )
    call_finish = LLMResult(
        content="Finished",
        tool_calls=[ToolCall(id="call_fin", name="finish", args={"summary": "done"})],
        prompt_tokens=50,
        completion_tokens=10,
        served_model="openai/gpt-4o",
        latency_ms=50,
    )

    cfg = ZeroBurnConfig()

    for mode in ("zeroburn", "naive"):
        mock_client.chat.side_effect = [call_edit, call_finish]
        session = run_task(
            task="hack data",
            repo=repo,
            mode=mode,
            config=cfg,
            approver=approver,
            client=mock_client,
            print_footer=False,
        )

        # File content must remain original and untouched!
        assert target_file.read_text(encoding="utf-8") == "original content"
        # Tool result in session messages must show denied
        tool_msg = next(m for m in session.messages if m.get("role") == "tool")
        assert "Action denied by user" in tool_msg["content"]
