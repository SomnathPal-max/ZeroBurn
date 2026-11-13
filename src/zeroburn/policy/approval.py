"""Deterministic approval gate and action requests."""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Protocol
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from zeroburn.errors import ApprovalDenied
from zeroburn.policy import risk


class ActionKind(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    SHELL = "SHELL"
    GIT = "GIT"


@dataclass
class ActionRequest:
    kind: ActionKind
    summary: str
    detail: str
    risk: int = 0

    def __post_init__(self) -> None:
        if not self.risk:
            self.risk = risk.score(self)


class Approver(Protocol):
    """Protocol for approving action requests."""
    def approve(self, req: ActionRequest) -> bool:
        ...


class ConsoleApprover:
    """Human-in-the-loop console approver using Rich panels.
    
    Default is No. There is no auto-approve, no timeout bypass, and no CLI bypass flag.
    """
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def approve(self, req: ActionRequest) -> bool:
        title = f"[bold red]Approval Required: {req.kind.value}[/bold red] (Risk: {req.risk}/100)"
        
        detail_renderable: Any = req.detail
        if req.kind == ActionKind.WRITE:
            detail_renderable = Syntax(req.detail, "diff", theme="monokai", line_numbers=True)
        elif req.kind in (ActionKind.SHELL, ActionKind.GIT):
            detail_renderable = Syntax(req.detail, "bash", theme="monokai")

        self.console.print(
            Panel(
                detail_renderable,
                title=title,
                subtitle=req.summary,
                expand=False,
            )
        )

        try:
            choice = input("Approve? [y/N]: ").strip().lower()
            return choice in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False


class ApprovalGate:
    """Deterministic default-deny gateway for all side-effecting actions.
    
    Reads are free; writes, shell, and git always require approval.
    """
    def __init__(self, approver: Approver | None = None) -> None:
        self.approver: Approver = approver or ConsoleApprover()

    def require(self, req: ActionRequest) -> None:
        if req.kind == ActionKind.READ:
            return

        approved = self.approver.approve(req)
        if not approved:
            raise ApprovalDenied(
                f"Action denied by user: [{req.kind.value}] {req.summary}"
            )
