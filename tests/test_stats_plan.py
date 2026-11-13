"""Tests for zeroburn stats and zeroburn plan commands."""
from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner
from rich.console import Console
import io

from zeroburn.cli import app
from zeroburn.ui.stats import render_stats
from zeroburn.ui.planner import render_plan
from zeroburn.policy.repo_flag import mark_confidential

runner = CliRunner()


def test_stats_with_sample_records(tmp_path: Path):
    usage_file = tmp_path / "usage.jsonl"
    records = [
        {
            "session_id": "sess_1",
            "served_model": "openai/gpt-4o",
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "est_cost_usd": 0.003,
            "latency_ms": 150,
            "failover": False,
            "cache_stub_hits": 2,
            "tool_calls": ["read_file", "apply_edit", "finish"],
        },
        {
            "session_id": "sess_2",
            "served_model": "ollama/llama3.1:8b",
            "prompt_tokens": 500,
            "completion_tokens": 20,
            "est_cost_usd": 0.0,
            "latency_ms": 80,
            "failover": True,
            "cache_stub_hits": 0,
            "tool_calls": ["search_code"],
        },
    ]
    with open(usage_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    buf = io.StringIO()
    con = Console(file=buf, width=160, no_color=True)
    render_stats(usage_path=usage_file, console=con)
    output = buf.getvalue()

    assert "ZeroBurn Usage Statistics" in output
    assert "Total Sessions" in output
    assert "openai/gpt-4o" in output
    assert "ollama/llama3.1:8b" in output
    assert "apply_edit" in output
    assert "search_code" in output


def test_stats_filter_session_and_last(tmp_path: Path):
    usage_file = tmp_path / "usage.jsonl"
    records = [
        {"session_id": "sess_A", "served_model": "openai/gpt-4o", "prompt_tokens": 100, "completion_tokens": 10, "est_cost_usd": 0.001, "latency_ms": 100, "tool_calls": ["finish"]},
        {"session_id": "sess_B", "served_model": "openai/gpt-4o-mini", "prompt_tokens": 200, "completion_tokens": 20, "est_cost_usd": 0.0001, "latency_ms": 50, "tool_calls": ["apply_edit"]},
    ]
    with open(usage_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    buf_last = io.StringIO()
    render_stats(last=True, usage_path=usage_file, console=Console(file=buf_last, width=160, no_color=True))
    out_last = buf_last.getvalue()
    assert "sess_B" in out_last
    assert "openai/gpt-4o-mini" in out_last

    buf_spec = io.StringIO()
    render_stats(session_id="sess_A", usage_path=usage_file, console=Console(file=buf_spec, width=160, no_color=True))
    out_spec = buf_spec.getvalue()
    assert "sess_A" in out_spec
    assert "openai/gpt-4o" in out_spec


def test_plan_standard_repo(tmp_path: Path):
    (tmp_path / "hello.py").write_text("def hello(): pass\n", encoding="utf-8")
    buf = io.StringIO()
    render_plan("fix bug in hello", repo=str(tmp_path), console=Console(file=buf, width=160, no_color=True))
    out = buf.getvalue()

    assert "ZeroBurn Route Planner" in out
    assert "STANDARD (Cloud Permitted)" in out
    assert "Local Vault" in out
    assert "Eco (Light)" in out
    assert "Deep (Heavy)" in out
    assert "$0.00000" in out


def test_plan_confidential_repo(tmp_path: Path):
    (tmp_path / "hello.py").write_text("def hello(): pass\n", encoding="utf-8")
    mark_confidential(tmp_path)

    buf = io.StringIO()
    render_plan("fix bug in hello", repo=str(tmp_path), console=Console(file=buf, width=160, no_color=True))
    out = buf.getvalue()

    assert "ZeroBurn Route Planner" in out
    assert "CONFIDENTIAL" in out
    assert "BLOCKED" in out
    assert "CONFIDENTIALITY ENFORCEMENT ACTIVE" in out


def test_cli_stats_and_plan():
    res_stats = runner.invoke(app, ["stats"])
    assert res_stats.exit_code == 0

    res_plan = runner.invoke(app, ["plan", "test task", "--repo", "."])
    assert res_plan.exit_code == 0
    assert "ZeroBurn Route Planner" in res_plan.stdout
