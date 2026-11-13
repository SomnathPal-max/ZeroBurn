"""Unit tests for tool registry, approval enforcement, and file modifications."""
from __future__ import annotations

import pytest
from pathlib import Path
from types import SimpleNamespace

from zeroburn.tools.registry import ToolRegistry, TOOL_SCHEMAS
from zeroburn.policy.approval import ApprovalGate, Approver, ActionRequest
from zeroburn.context.read_cache import ReadCache


class MockApprover:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.call_count = 0
        self.last_req: ActionRequest | None = None

    def approve(self, req: ActionRequest) -> bool:
        self.call_count += 1
        self.last_req = req
        return self.allow


@pytest.fixture
def mock_session(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "hello.py").write_text('def hello():\n    return "world"\n', encoding="utf-8")
    (repo / "duplicate.txt").write_text("apple\napple\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=123\n", encoding="utf-8")

    session = SimpleNamespace(
        repo_root=repo,
        read_cache=ReadCache(),
        step=1,
        task_text="test task",
        touched_files=set(),
        config=SimpleNamespace(agent=SimpleNamespace(tool_result_max_chars=4000)),
    )
    return session


def test_tool_schemas_under_15_words() -> None:
    for tool in TOOL_SCHEMAS:
        desc = tool["function"]["description"]
        word_count = len(desc.split())
        assert word_count < 15, f"Tool {tool['function']['name']} description has {word_count} words (> 15)"


def test_denied_approval_leaves_files_unchanged_apply_edit(mock_session) -> None:
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    res = registry.execute(
        "apply_edit",
        {"path": "hello.py", "old": '"world"', "new": '"universe"'},
        mock_session,
    )

    assert "Action denied by user" in res
    assert approver.call_count == 1
    # Check file was NOT modified
    content = (mock_session.repo_root / "hello.py").read_text(encoding="utf-8")
    assert '"world"' in content
    assert '"universe"' not in content


def test_ambiguous_old_string_rejected(mock_session) -> None:
    approver = MockApprover(allow=True)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    res = registry.execute(
        "apply_edit",
        {"path": "duplicate.txt", "old": "apple", "new": "orange"},
        mock_session,
    )

    assert "occurs 2 times" in res
    # Ensure gate was not called for invalid edit
    assert approver.call_count == 0


def test_denied_create_file(mock_session) -> None:
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    res = registry.execute(
        "create_file",
        {"path": "new_file.py", "content": "print('hello')"},
        mock_session,
    )

    assert "Action denied by user" in res
    assert not (mock_session.repo_root / "new_file.py").exists()


def test_approved_create_file(mock_session) -> None:
    approver = MockApprover(allow=True)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    res = registry.execute(
        "create_file",
        {"path": "new_file.py", "content": "print('hello')"},
        mock_session,
    )

    assert "Successfully created" in res
    assert (mock_session.repo_root / "new_file.py").read_text() == "print('hello')"


def test_denied_shell_runs_nothing(mock_session) -> None:
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    res = registry.execute(
        "run_shell",
        {"command": "echo hacked > hacked.txt"},
        mock_session,
    )

    assert "Action denied by user" in res
    assert not (mock_session.repo_root / "hacked.txt").exists()


def test_every_git_subcommand_triggers_approver(mock_session) -> None:
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    # status
    registry.execute("git", {"args": ["status"]}, mock_session)
    assert approver.call_count == 1

    # diff
    registry.execute("git", {"args": ["diff"]}, mock_session)
    assert approver.call_count == 2

    # commit
    registry.execute("git", {"args": ["commit", "-m", "fix"]}, mock_session)
    assert approver.call_count == 3


def test_reads_never_trigger_approver(mock_session) -> None:
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    # read_range
    res_range = registry.execute("read_range", {"path": "hello.py", "start": 1, "end": 2}, mock_session)
    assert "<tool_result name=read_range>" in res_range
    assert approver.call_count == 0

    # read_file
    res_file = registry.execute("read_file", {"path": "hello.py"}, mock_session)
    assert "<tool_result name=read_file>" in res_file
    assert approver.call_count == 0

    # get_symbol
    res_sym = registry.execute("get_symbol", {"path": "hello.py", "name": "hello"}, mock_session)
    assert "<tool_result name=get_symbol>" in res_sym
    assert approver.call_count == 0

    # search_code
    res_search = registry.execute("search_code", {"pattern": "def hello"}, mock_session)
    assert "<tool_result name=search_code>" in res_search
    assert approver.call_count == 0


def test_sensitive_read_triggers_approver(mock_session) -> None:
    approver = MockApprover(allow=False)
    registry = ToolRegistry(gate=ApprovalGate(approver=approver))

    res = registry.execute("read_file", {"path": ".env"}, mock_session)
    assert approver.call_count == 1
    assert "Action denied by user" in res
