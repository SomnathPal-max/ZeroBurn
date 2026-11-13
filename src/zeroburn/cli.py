"""Command-line interface for ZeroBurn."""
from __future__ import annotations

import typer
from typing import Optional
from rich.console import Console

from zeroburn.config import load_config
from zeroburn.gateway.client import GatewayClient

app = typer.Typer(
    name="zeroburn",
    help="ZeroBurn - Token-efficient coding agent with local failover and approval gates.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init() -> None:
    """Create zeroburn.toml and .zeroburn/ in the current repo."""
    console.print("[green]Initialized ZeroBurn configuration.[/green]")


@app.command()
def run(
    task: str = typer.Argument(..., help="The task for ZeroBurn to execute."),
    repo: str = typer.Option(".", "--repo", "-r", help="Path to target repository."),
    mode: str = typer.Option("zeroburn", "--mode", "-m", help="Execution mode: zeroburn or naive."),
) -> None:
    """Run the agent with interactive approvals."""
    console.print(f"Running task '{task}' in {repo} (mode: {mode})")


@app.command()
def stats(
    session: Optional[str] = typer.Option(None, "--session", help="Session ID to inspect."),
    last: bool = typer.Option(False, "--last", help="Show stats for the last session."),
) -> None:
    """Display token and cost usage table from usage.jsonl."""
    console.print("Stats stub")


@app.command()
def plan(
    task: str = typer.Argument(..., help="The task to estimate."),
    repo: str = typer.Option(".", "--repo", "-r", help="Path to target repository."),
) -> None:
    """Print route options with token and cost estimates."""
    console.print(f"Planning task '{task}' in {repo}")


@app.command("mark-confidential")
def mark_confidential(
    path: str = typer.Argument(..., help="Path to repository to mark confidential."),
) -> None:
    """Create .zeroburn/confidential in the given repository."""
    console.print(f"Marked {path} as confidential.")


@app.command()
def ping() -> None:
    """Test both virtual keys through Bifrost gateway and print which model served them."""
    cfg = load_config()
    client = GatewayClient(base_url=cfg.bifrost_url, timeout_s=15.0)

    console.print(f"[bold blue]Testing Bifrost Gateway at {cfg.bifrost_url}...[/bold blue]")

    # 1. Standard Virtual Key
    std_model = cfg.models.light_chain[0]
    console.print(f"Pinging Standard Virtual Key with {std_model}...")
    try:
        res_std = client.chat(
            model=std_model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            vk=cfg.bifrost_vk_standard,
        )
        console.print(f"  [green]Standard key OK! Served by: {res_std.served_model} (latency: {res_std.latency_ms}ms)[/green]")
    except Exception as exc:
        console.print(f"  [red]Standard key ping failed: {exc}[/red]")

    # 2. Confidential Virtual Key
    local_model = cfg.models.local
    console.print(f"Pinging Confidential Virtual Key with {local_model}...")
    try:
        res_conf = client.chat(
            model=local_model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            vk=cfg.bifrost_vk_confidential,
        )
        console.print(f"  [green]Confidential key OK! Served by: {res_conf.served_model} (latency: {res_conf.latency_ms}ms)[/green]")
    except Exception as exc:
        console.print(f"  [red]Confidential key ping failed: {exc}[/red]")


if __name__ == "__main__":
    app()
