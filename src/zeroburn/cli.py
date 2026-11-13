"""Command-line interface for ZeroBurn."""
from __future__ import annotations

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console

from zeroburn.config import load_config
from zeroburn.policy import repo_flag
from zeroburn.gateway.client import GatewayClient
from zeroburn.agent.loop import run_task
from zeroburn.ui.stats import render_stats
from zeroburn.ui.planner import render_plan

app = typer.Typer(
    name="zeroburn",
    help="ZeroBurn - Token-efficient coding agent with local failover and approval gates.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init(
    path: str = typer.Option(".", "--path", "-p", help="Directory to initialize."),
) -> None:
    """Create zeroburn.toml and .zeroburn/ in the current repo."""
    root = Path(path).resolve()
    target_dir = root / ".zeroburn"
    target_dir.mkdir(parents=True, exist_ok=True)

    toml_path = root / "zeroburn.toml"
    example_path = Path("zeroburn.toml.example")
    if not toml_path.exists():
        if example_path.exists():
            toml_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            toml_path.write_text(
                '[models]\nlocal = "ollama/llama3.1:8b"\n'
                'light_chain = ["openai/gpt-4o-mini", "ollama/llama3.1:8b"]\n'
                'heavy_chain = ["openai/gpt-4o", "openai/gpt-4o-mini", "ollama/llama3.1:8b"]\n',
                encoding="utf-8",
            )
    console.print(f"[green]Initialized ZeroBurn configuration at {root}[/green]")


@app.command()
def run(
    task: str = typer.Argument(..., help="The task for ZeroBurn to execute."),
    repo: str = typer.Option(".", "--repo", "-r", help="Path to target repository."),
    mode: str = typer.Option("zeroburn", "--mode", "-m", help="Execution mode: zeroburn or naive."),
) -> None:
    """Run the agent with interactive approvals."""
    console.print(f"[bold blue]Starting ZeroBurn task:[/bold blue] '{task}' in {repo} (mode: {mode})")
    run_task(task=task, repo=repo, mode=mode)


@app.command()
def stats(
    session: Optional[str] = typer.Option(None, "--session", help="Session ID to inspect."),
    last: bool = typer.Option(False, "--last", help="Show stats for the last session."),
) -> None:
    """Display token and cost usage table from usage.jsonl."""
    render_stats(session_id=session, last=last, console=console)


@app.command()
def plan(
    task: str = typer.Argument(..., help="The task to estimate."),
    repo: str = typer.Option(".", "--repo", "-r", help="Path to target repository."),
) -> None:
    """Print route options with token and cost estimates."""
    render_plan(task=task, repo=repo, console=console)


@app.command("mark-confidential")
def mark_confidential(
    path: str = typer.Argument(..., help="Path to repository to mark confidential."),
) -> None:
    """Create .zeroburn/confidential in the given repository."""
    marker = repo_flag.mark_confidential(path)
    console.print(f"[bold green]Successfully marked repository as confidential:[/bold green] {marker}")


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
