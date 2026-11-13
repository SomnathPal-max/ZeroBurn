"""Git tool strictly requiring human approval for every subcommand."""
from __future__ import annotations

import subprocess
from pathlib import Path

from zeroburn.policy.approval import ActionKind, ActionRequest, ApprovalGate


def run_git(
    args: list[str],
    repo_root: Path | str,
    gate: ApprovalGate,
    max_chars: int = 4000,
) -> str:
    """Execute git with args in repo_root with approval gating and shell=False."""
    root = Path(repo_root).resolve()
    cmd_str = f"git {' '.join(args)}"

    req = ActionRequest(
        kind=ActionKind.GIT,
        summary=f"Git operation: {cmd_str}",
        detail=cmd_str,
    )
    # Require human approval for ALL git invocations
    gate.require(req)

    try:
        proc = subprocess.run(
            ["git", *args],
            shell=False,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            errors="replace",
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        output = combined if combined.strip() else f"(Git completed with exit code {proc.returncode})"
    except Exception as exc:
        output = f"Git execution error: {exc}"

    if len(output) > max_chars:
        output = output[:max_chars] + f"\n... [truncated to {max_chars} chars]"

    return output
