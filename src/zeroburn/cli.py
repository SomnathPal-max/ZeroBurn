"""Command-line interface for ZeroBurn."""
from __future__ import annotations

import typer
from typing import Optional

app = typer.Typer(
    name="zeroburn",
    help="ZeroBurn - Token-efficient coding agent with local failover and approval gates.",
    no_args_is_help=True,
)


@app.command()
def init() -> None:
    """Create zeroburn.toml and .zeroburn/ in the current repo."""
    typer.echo("Initialized ZeroBurn configuration.")


@app.command()
def run(
    task: str = typer.Argument(..., help="The task for ZeroBurn to execute."),
    repo: str = typer.Option(".", "--repo", "-r", help="Path to target repository."),
    mode: str = typer.Option("zeroburn", "--mode", "-m", help="Execution mode: zeroburn or naive."),
) -> None:
    """Run the agent with interactive approvals."""
    typer.echo(f"Running task '{task}' in {repo} (mode: {mode})")


@app.command()
def stats(
    session: Optional[str] = typer.Option(None, "--session", help="Session ID to inspect."),
    last: bool = typer.Option(False, "--last", help="Show stats for the last session."),
) -> None:
    """Display token and cost usage table from usage.jsonl."""
    typer.echo("Stats stub")


@app.command()
def plan(
    task: str = typer.Argument(..., help="The task to estimate."),
    repo: str = typer.Option(".", "--repo", "-r", help="Path to target repository."),
) -> None:
    """Print route options with token and cost estimates."""
    typer.echo(f"Planning task '{task}' in {repo}")


@app.command("mark-confidential")
def mark_confidential(
    path: str = typer.Argument(..., help="Path to repository to mark confidential."),
) -> None:
    """Create .zeroburn/confidential in the given repository."""
    typer.echo(f"Marked {path} as confidential.")


@app.command()
def ping() -> None:
    """Test both virtual keys through Bifrost gateway."""
    typer.echo("Pinging gateway...")


if __name__ == "__main__":
    app()
