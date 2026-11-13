"""Shell execution tool gated by human approval."""
from __future__ import annotations

import subprocess
from pathlib import Path

from zeroburn.policy.approval import ActionKind, ActionRequest, ApprovalGate


def run_shell(
    command: str,
    repo_root: Path | str,
    gate: ApprovalGate,
    timeout_s: float = 60.0,
    max_chars: int = 4000,
) -> str:
    """Execute a shell command in repo_root with approval gating and timeout."""
    root = Path(repo_root).resolve()

    req = ActionRequest(
        kind=ActionKind.SHELL,
        summary=f"Shell command: {command}",
        detail=command,
    )
    # Require human approval
    gate.require(req)

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            errors="replace",
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        output = combined if combined.strip() else f"(Command completed with exit code {proc.returncode})"
    except subprocess.TimeoutExpired:
        output = f"Command timed out after {timeout_s} seconds."
    except Exception as exc:
        output = f"Command execution error: {exc}"

    if len(output) > max_chars:
        output = output[:max_chars] + f"\n... [truncated to {max_chars} chars]"

    return output
