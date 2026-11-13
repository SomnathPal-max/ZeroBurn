"""Risk scoring for proposed agent actions (display-only, never skips approval)."""
from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from zeroburn.policy.approval import ActionRequest, ActionKind


def score(req: ActionRequest) -> int:
    """Calculate a display risk score between 0 and 100 for an ActionRequest.
    
    Rules:
    - create_file: 30
    - apply_edit: 25 (60 on protected/critical paths)
    - shell: 40 (+30 for rm, sudo, chmod, curl, wget, pip/npm install)
    - git commit: 35
    - git push: 70
    - git reset --hard or git clean: 80
    """
    from zeroburn.policy.approval import ActionKind

    kind = req.kind
    summary = req.summary.lower()
    detail = req.detail.lower()

    if kind == ActionKind.READ:
        return 10

    if kind == ActionKind.WRITE:
        if "create" in summary or "create_file" in summary:
            return 30
        
        # apply_edit
        protected_targets = ["pyproject.toml", "setup.py", "requirements.txt", ".github", "dockerfile"]
        is_protected = any(p in detail or p in summary for p in protected_targets)
        return 60 if is_protected else 25

    if kind == ActionKind.SHELL:
        base_score = 40
        risky_keywords = [
            "rm ", "rmdir", "sudo", "chmod", "chown",
            "curl", "wget", "pip install", "pip3 install", "npm install", "npx",
            "format", "mkfs"
        ]
        if any(kw in detail for kw in risky_keywords):
            base_score += 30
        return min(base_score, 100)

    if kind == ActionKind.GIT:
        if "reset --hard" in detail or "clean" in detail:
            return 80
        if "push" in detail:
            return 70
        if "commit" in detail:
            return 35
        if "checkout" in detail:
            return 40
        return 30

    return 20
