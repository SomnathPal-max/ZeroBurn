"""Unit tests for safety policy, sandbox boundaries, and approval gates."""
from __future__ import annotations

import os
import pytest
from pathlib import Path

from zeroburn.errors import PolicyViolation, ApprovalDenied
from zeroburn.policy import sandbox, repo_flag, risk
from zeroburn.policy.approval import (
    ActionKind,
    ActionRequest,
    ApprovalGate,
    Approver,
)


def test_path_traversal_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(PolicyViolation, match="Path traversal detected"):
        sandbox.resolve(repo, "../outside.txt")

    with pytest.raises(PolicyViolation, match="Path traversal detected"):
        sandbox.resolve(repo, "../../etc/passwd")


def test_symlink_escape_blocked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target_outside = tmp_path / "outside_target.txt"
    target_outside.write_text("escape", encoding="utf-8")

    link = repo / "symlink_escape"
    try:
        link.symlink_to(target_outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment")

    with pytest.raises(PolicyViolation, match="Path traversal detected"):
        sandbox.resolve(repo, "symlink_escape")


def test_sandbox_deny_list_writes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    # .git
    with pytest.raises(PolicyViolation, match="\\.git"):
        sandbox.check_write(repo, ".git/config")

    # .zeroburn
    with pytest.raises(PolicyViolation, match="\\.zeroburn"):
        sandbox.check_write(repo, ".zeroburn/confidential")

    # zeroburn.toml
    with pytest.raises(PolicyViolation, match="zeroburn\\.toml"):
        sandbox.check_write(repo, "zeroburn.toml")

    # .env files
    with pytest.raises(PolicyViolation, match="\\.env"):
        sandbox.check_write(repo, ".env")
    with pytest.raises(PolicyViolation, match="\\.env"):
        sandbox.check_write(repo, ".env.production")

    # Safe file should not raise
    sandbox.check_write(repo, "src/main.py")


def test_sensitive_reads(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert sandbox.is_sensitive_read(repo, ".env") is True
    assert sandbox.is_sensitive_read(repo, "server.pem") is True
    assert sandbox.is_sensitive_read(repo, "id_rsa") is True
    assert sandbox.is_sensitive_read(repo, "main.py") is False


class MockApprover:
    def __init__(self, decision: bool) -> None:
        self.decision = decision
        self.called = False

    def approve(self, req: ActionRequest) -> bool:
        self.called = True
        return self.decision


def test_approval_gate_read_free() -> None:
    approver = MockApprover(decision=False)
    gate = ApprovalGate(approver=approver)

    req = ActionRequest(kind=ActionKind.READ, summary="read file", detail="cat file.txt")
    gate.require(req)
    assert not approver.called


def test_approval_gate_write_requires_approval() -> None:
    approver_deny = MockApprover(decision=False)
    gate_deny = ApprovalGate(approver=approver_deny)
    req_write = ActionRequest(kind=ActionKind.WRITE, summary="edit file", detail="+ new line")

    with pytest.raises(ApprovalDenied, match="Action denied by user"):
        gate_deny.require(req_write)
    assert approver_deny.called

    approver_allow = MockApprover(decision=True)
    gate_allow = ApprovalGate(approver=approver_allow)
    gate_allow.require(req_write)
    assert approver_allow.called


def test_approval_gate_shell_and_git_require_approval() -> None:
    approver_deny = MockApprover(decision=False)
    gate = ApprovalGate(approver=approver_deny)

    with pytest.raises(ApprovalDenied):
        gate.require(ActionRequest(kind=ActionKind.SHELL, summary="run pytest", detail="pytest"))

    with pytest.raises(ApprovalDenied):
        gate.require(ActionRequest(kind=ActionKind.GIT, summary="git commit", detail="git commit -m msg"))


def test_no_auto_approve_bypass_in_policy() -> None:
    policy_dir = Path(__file__).resolve().parent.parent / "src" / "zeroburn" / "policy"
    for py_file in policy_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "--yes" not in content
        assert "auto_approve" not in content
        assert "bypass=True" not in content
        assert "force=True" not in content
        assert "skip_approval" not in content


def test_repo_flag_confidential(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert not repo_flag.is_confidential(repo)

    # Via mark_confidential
    repo_flag.mark_confidential(repo)
    assert repo_flag.is_confidential(repo)

    # Clean up marker and test zeroburn.toml
    (repo / ".zeroburn" / "confidential").unlink()
    assert not repo_flag.is_confidential(repo)

    (repo / "zeroburn.toml").write_text("confidential = true\n", encoding="utf-8")
    assert repo_flag.is_confidential(repo)


def test_risk_scoring() -> None:
    req_create = ActionRequest(kind=ActionKind.WRITE, summary="create_file", detail="content")
    assert risk.score(req_create) == 30

    req_edit = ActionRequest(kind=ActionKind.WRITE, summary="apply_edit", detail="diff")
    assert risk.score(req_edit) == 25

    req_edit_protected = ActionRequest(kind=ActionKind.WRITE, summary="apply_edit", detail="pyproject.toml diff")
    assert risk.score(req_edit_protected) == 60

    req_shell_safe = ActionRequest(kind=ActionKind.SHELL, summary="run_shell", detail="ls -la")
    assert risk.score(req_shell_safe) == 40

    req_shell_risky = ActionRequest(kind=ActionKind.SHELL, summary="run_shell", detail="rm -rf /data")
    assert risk.score(req_shell_risky) == 70

    req_git_commit = ActionRequest(kind=ActionKind.GIT, summary="git", detail="commit -m fix")
    assert risk.score(req_git_commit) == 35

    req_git_push = ActionRequest(kind=ActionKind.GIT, summary="git", detail="push origin main")
    assert risk.score(req_git_push) == 70

    req_git_reset = ActionRequest(kind=ActionKind.GIT, summary="git", detail="reset --hard HEAD~1")
    assert risk.score(req_git_reset) == 80
