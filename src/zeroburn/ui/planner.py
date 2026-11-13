"""Rich UI reporting for zeroburn plan command."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from zeroburn.config import load_config
from zeroburn.policy import repo_flag
from zeroburn.context.repo_map import generate_repo_map


def render_plan(
    task: str,
    repo: str = ".",
    console: Optional[Console] = None,
) -> None:
    """Analyze repository and display candidate routes with token and cost projections."""
    c = console or Console()
    root = Path(repo).resolve()
    if not root.exists():
        c.print(f"[red]Error: repository directory '{root}' does not exist.[/red]")
        return

    cfg = load_config(root)
    is_conf = repo_flag.is_confidential(root)

    # Calculate repo map and token sizes
    try:
        repo_map_str = generate_repo_map(root, task_text=task, max_tokens=1500)
    except Exception:
        repo_map_str = ""

    repo_map_tokens = max(50, len(repo_map_str) // 4)
    task_tokens = max(10, len(task) // 4)
    sys_prompt_tokens = 400
    base_step_in = sys_prompt_tokens + repo_map_tokens + task_tokens
    step_out = 60

    c.print(Panel(
        f"[bold]Task:[/bold] {task}\n"
        f"[bold]Target Repository:[/bold] {root}\n"
        f"[bold]Confidential Status:[/bold] {'[bold red]CONFIDENTIAL (Local-Only)[/bold red]' if is_conf else '[bold green]STANDARD (Cloud Permitted)[/bold green]'}\n"
        f"[bold]Repo Map Size:[/bold] ~{repo_map_tokens:,} tokens",
        title="[bold cyan]ZeroBurn Route Planner[/bold cyan]",
        border_style="cyan",
        expand=False,
    ))

    table = Table(title="Candidate Route Options (3-step projection)", show_header=True, header_style="bold magenta")
    table.add_column("Route", style="bold")
    table.add_column("Tier", style="dim")
    table.add_column("Primary Model", style="cyan")
    table.add_column("Failover Chain")
    table.add_column("Est. Tokens (In / Out)", justify="right")
    table.add_column("Est. Cost (USD)", justify="right")
    table.add_column("Confidential?", justify="center")

    # 1. Local Vault
    local_m = cfg.models.local
    local_chain = [local_m]
    local_in = base_step_in * 3
    local_out = step_out * 3
    table.add_row(
        "Local Vault",
        "local_only",
        local_m,
        " -> ".join(local_chain),
        f"{local_in:,} / {local_out:,}",
        "$0.00000",
        "[bold green]YES[/bold green]",
    )

    # 2. Eco Route
    eco_primary = cfg.models.light_chain[0]
    eco_chain = list(cfg.models.light_chain)
    if local_m not in eco_chain:
        eco_chain.append(local_m)
    eco_in = base_step_in * 2
    eco_out = step_out * 2
    eco_rates = cfg.prices_usd_per_million.get(eco_primary, [0.0, 0.0])
    eco_cost = (eco_in * eco_rates[0] + eco_out * eco_rates[1]) / 1_000_000.0
    eco_cost_str = f"${eco_cost:.5f}"

    table.add_row(
        "Eco (Light)",
        "light",
        eco_primary,
        " -> ".join(eco_chain),
        f"{eco_in:,} / {eco_out:,}",
        eco_cost_str,
        "[bold red]BLOCKED[/bold red]" if is_conf else "[dim]Available[/dim]",
    )

    # 3. Deep Route
    deep_primary = cfg.models.heavy_chain[0]
    deep_chain = list(cfg.models.heavy_chain)
    if local_m not in deep_chain:
        deep_chain.append(local_m)
    deep_in = base_step_in * 3
    deep_out = step_out * 3
    deep_rates = cfg.prices_usd_per_million.get(deep_primary, [0.0, 0.0])
    deep_cost = (deep_in * deep_rates[0] + deep_out * deep_rates[1]) / 1_000_000.0
    deep_cost_str = f"${deep_cost:.5f}"

    table.add_row(
        "Deep (Heavy)",
        "heavy",
        deep_primary,
        " -> ".join(deep_chain),
        f"{deep_in:,} / {deep_out:,}",
        deep_cost_str,
        "[bold red]BLOCKED[/bold red]" if is_conf else "[dim]Available[/dim]",
    )

    c.print(table)

    if is_conf:
        c.print(Panel(
            "[bold yellow]CONFIDENTIALITY ENFORCEMENT ACTIVE[/bold yellow]\n"
            "This repository has a `.zeroburn/confidential` marker.\n"
            "By safety policy, the runtime will strictly select the [bold green]Local Vault[/bold green] route.\n"
            "Cloud routes (Eco, Deep) are denied to prevent any data exfiltration.",
            border_style="yellow",
            expand=False,
        ))
    else:
        c.print(f"[dim]To execute this task, run: zeroburn run \"{task}\" --repo \"{root}\"[/dim]")
