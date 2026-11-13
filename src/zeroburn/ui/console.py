"""Console UI formatting with Rich banners, panels, and tables."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_model_switch_banner(old_model: str, new_model: str, reason: str) -> None:
    """Print visible console banner on model switch/failover."""
    text = f"[bold yellow]MODEL SWITCH:[/bold yellow] [bold red]{old_model}[/bold red] -> [bold green]{new_model}[/bold green] (reason: {reason})"
    console.print(
        Panel(
            text,
            title="[bold yellow]Gateway Failover Alert[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
    )


def print_task_footer(
    steps: int,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    models_used: list[str],
    failovers: int,
) -> None:
    """Print session completion footer with token and cost breakdown."""
    table = Table(title="ZeroBurn Run Summary", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("Steps Completed", str(steps))
    table.add_row("Prompt Tokens", f"{prompt_tokens:,}")
    table.add_row("Completion Tokens", f"{completion_tokens:,}")
    table.add_row("Total Tokens", f"{prompt_tokens + completion_tokens:,}")
    table.add_row("Total Cost (USD)", f"${cost_usd:.5f}")
    table.add_row("Models Used", ", ".join(models_used) if models_used else "None")
    table.add_row("Failovers Occurred", str(failovers))

    console.print(table)
