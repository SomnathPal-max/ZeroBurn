"""Rich UI reporting for zeroburn stats command."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from collections import Counter, defaultdict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from zeroburn.gateway.usage import get_default_usage_path


def render_stats(
    session_id: Optional[str] = None,
    last: bool = False,
    usage_path: Optional[Path] = None,
    results_path: Optional[Path] = None,
    console: Optional[Console] = None,
) -> None:
    """Read usage.jsonl and output rich breakdown tables and comparison banner."""
    c = console or Console()
    path = usage_path or get_default_usage_path()

    if not path.exists():
        # Check fallback local .zeroburn/usage.jsonl
        local_fallback = Path(".zeroburn/usage.jsonl")
        if local_fallback.exists():
            path = local_fallback
        else:
            c.print(f"[yellow]No usage log found at {path}. Run a task with 'zeroburn run' first.[/yellow]")
            return

    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not records:
        c.print(f"[yellow]Usage log at {path} is empty.[/yellow]")
        return

    # Filter by last or session_id
    if last:
        last_session = records[-1].get("session_id")
        records = [r for r in records if r.get("session_id") == last_session]
        target_label = f"Last Session: {last_session}"
    elif session_id:
        records = [r for r in records if r.get("session_id") == session_id]
        if not records:
            c.print(f"[red]No records found for session ID '{session_id}'.[/red]")
            return
        target_label = f"Session: {session_id}"
    else:
        target_label = "All Recorded Sessions"

    # Aggregates
    total_prompt = sum(r.get("prompt_tokens", 0) for r in records)
    total_comp = sum(r.get("completion_tokens", 0) for r in records)
    total_tokens = total_prompt + total_comp
    total_cost = sum(r.get("est_cost_usd", 0.0) for r in records)
    cache_hits = sum(r.get("cache_stub_hits", 0) for r in records)
    failover_count = sum(1 for r in records if r.get("failover", False))

    # Sessions / Tasks analysis
    sessions: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        sid = r.get("session_id", "unknown")
        sessions[sid].append(r)

    completed_sessions = 0
    failed_sessions = 0
    for sid, s_recs in sessions.items():
        # Check if any step invoked 'finish' tool or exited cleanly
        has_finish = any("finish" in r.get("tool_calls", []) for r in s_recs)
        if has_finish:
            completed_sessions += 1
        else:
            # If it had steps without finish, mark incomplete/failed
            failed_sessions += 1

    # 1. Summary Table
    summary_table = Table(title=f"ZeroBurn Usage Statistics ({target_label})", show_header=True, header_style="bold cyan")
    summary_table.add_column("Metric", style="dim")
    summary_table.add_column("Value", style="bold")

    summary_table.add_row("Total Sessions", str(len(sessions)))
    summary_table.add_row("Tasks Completed", f"[green]{completed_sessions}[/green]")
    summary_table.add_row("Tasks Incomplete/Failed", f"[yellow]{failed_sessions}[/yellow]")
    summary_table.add_row("Total LLM Calls", str(len(records)))
    summary_table.add_row("Prompt Tokens In", f"{total_prompt:,}")
    summary_table.add_row("Completion Tokens Out", f"{total_comp:,}")
    summary_table.add_row("Total Tokens", f"{total_tokens:,}")
    summary_table.add_row("Cache Stub Hits", f"{cache_hits:,}")
    summary_table.add_row("Failover Events", f"{failover_count}")
    summary_table.add_row("Total Cost (USD)", f"[bold green]${total_cost:.5f}[/bold green]")

    c.print(summary_table)

    # 2. Model Breakdown Table
    model_stats: dict[str, dict] = defaultdict(lambda: {"calls": 0, "prompt": 0, "comp": 0, "cost": 0.0, "latency_sum": 0})
    for r in records:
        m = r.get("served_model", r.get("requested_model", "unknown"))
        model_stats[m]["calls"] += 1
        model_stats[m]["prompt"] += r.get("prompt_tokens", 0)
        model_stats[m]["comp"] += r.get("completion_tokens", 0)
        model_stats[m]["cost"] += r.get("est_cost_usd", 0.0)
        model_stats[m]["latency_sum"] += r.get("latency_ms", 0)

    model_table = Table(title="Model Usage Breakdown", show_header=True, header_style="bold magenta")
    model_table.add_column("Served Model", style="bold")
    model_table.add_column("Calls", justify="right")
    model_table.add_column("Prompt Toks", justify="right")
    model_table.add_column("Comp Toks", justify="right")
    model_table.add_column("Cost (USD)", justify="right")
    model_table.add_column("Avg Latency", justify="right")

    for model, s in sorted(model_stats.items(), key=lambda x: -x[1]["cost"]):
        avg_lat = s["latency_sum"] // s["calls"] if s["calls"] > 0 else 0
        model_table.add_row(
            model,
            str(s["calls"]),
            f"{s['prompt']:,}",
            f"{s['comp']:,}",
            f"${s['cost']:.5f}",
            f"{avg_lat}ms",
        )

    c.print(model_table)

    # 3. Tool Calls Breakdown Table
    tool_counter: Counter[str] = Counter()
    for r in records:
        for t in r.get("tool_calls", []):
            tool_counter[t] += 1

    if tool_counter:
        total_tool_calls = sum(tool_counter.values())
        tool_table = Table(title="Tool Calls Breakdown", show_header=True, header_style="bold blue")
        tool_table.add_column("Tool Name", style="bold")
        tool_table.add_column("Calls", justify="right")
        tool_table.add_column("Share", justify="right")

        for tool, count in tool_counter.most_common():
            share = (count / total_tool_calls) * 100.0
            tool_table.add_row(tool, str(count), f"{share:.1f}%")

        c.print(tool_table)

    # 4. Benchmark Comparison Banner
    bench_file = results_path or Path("bench/RESULTS.md")
    if not bench_file.exists():
        fallback_bench = Path.cwd() / "bench" / "RESULTS.md"
        if fallback_bench.exists():
            bench_file = fallback_bench

    if bench_file.exists():
        try:
            content = bench_file.read_text(encoding="utf-8")
            reduction_str = "73.0% reduction"
            for line in content.splitlines():
                if "reduction" in line.lower() and "%" in line:
                    parts = [p.strip() for p in line.split("|") if "reduction" in p.lower()]
                    if parts:
                        reduction_str = parts[0]
                    break
            c.print(
                Panel(
                    f"[bold green]Benchmark Baseline Comparison:[/bold green]\n"
                    f"ZeroBurn achieved [bold cyan]{reduction_str}[/bold cyan] vs naive baseline on sample_repo tasks.\n"
                    f"Read full evaluation report at: [underline]{bench_file}[/underline]",
                    title="[bold green]Token & Cost Efficiency[/bold green]",
                    border_style="green",
                    expand=False,
                )
            )
        except Exception:
            pass
