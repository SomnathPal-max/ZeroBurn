"""Unit tests for the complete agent execution loop."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from zeroburn.config import ZeroBurnConfig
from zeroburn.agent.loop import run_task
from zeroburn.gateway.client import LLMResult, ToolCall
from zeroburn.policy.approval import ActionRequest


class AutoAllowApprover:
    def __init__(self) -> None:
        self.approved_requests: list[ActionRequest] = []

    def approve(self, req: ActionRequest) -> bool:
        self.approved_requests.append(req)
        return True


@pytest.fixture
def paging_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "paging_repo"
    repo.mkdir()

    # Code with an off-by-one pagination bug
    src = repo / "paging.py"
    src.write_text(
        "def paginate(items, page, page_size):\n"
        "    start = page * page_size + 1  # BUG: off-by-one\n"
        "    end = start + page_size\n"
        "    return items[start:end]\n",
        encoding="utf-8",
    )

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_paging.py"
    test_file.write_text(
        "from paging import paginate\n\n"
        "def test_paging():\n"
        "    data = list(range(10))\n"
        "    assert paginate(data, 0, 5) == [0, 1, 2, 3, 4]\n",
        encoding="utf-8",
    )

    return repo


def test_agent_loop_end_to_end(paging_repo: Path, tmp_path: Path) -> None:
    approver = AutoAllowApprover()
    mock_client = MagicMock()

    # Turn 1: model calls apply_edit to fix the bug
    call_1 = LLMResult(
        content="I will fix the off-by-one pagination bug.",
        tool_calls=[
            ToolCall(
                id="call_edit",
                name="apply_edit",
                args={
                    "path": "paging.py",
                    "old": "    start = page * page_size + 1  # BUG: off-by-one",
                    "new": "    start = page * page_size",
                },
            )
        ],
        prompt_tokens=150,
        completion_tokens=40,
        served_model="openai/gpt-4o",
        latency_ms=250,
    )

    # Turn 2: model runs finish
    call_2 = LLMResult(
        content="Fixed pagination start index.",
        tool_calls=[
            ToolCall(
                id="call_finish",
                name="finish",
                args={"summary": "Fixed off-by-one bug in paginate function."},
            )
        ],
        prompt_tokens=220,
        completion_tokens=25,
        served_model="openai/gpt-4o",
        latency_ms=180,
    )

    mock_client.chat.side_effect = [call_1, call_2]

    usage_file = tmp_path / "usage.jsonl"
    ledger_file = tmp_path / "ledger.json"

    cfg = ZeroBurnConfig(
        prices_usd_per_million={
            "openai/gpt-4o": [2.50, 10.00],
            "openai/gpt-4o-mini": [0.15, 0.60],
            "ollama/llama3.1:8b": [0.0, 0.0],
        }
    )

    session = run_task(
        task="fix the failing test in tests/test_paging.py",
        repo=paging_repo,
        mode="zeroburn",
        config=cfg,
        approver=approver,
        client=mock_client,
        print_footer=False,
    )

    assert session.step == 2
    assert session.total_prompt_tokens == 370
    assert session.total_completion_tokens == 65
    assert len(approver.approved_requests) == 1
    assert approver.approved_requests[0].summary == "Edit file: paging.py"

    # Verify bug was fixed in paging.py
    updated_code = (paging_repo / "paging.py").read_text(encoding="utf-8")
    assert "start = page * page_size\n" in updated_code
    assert "off-by-one" not in updated_code
