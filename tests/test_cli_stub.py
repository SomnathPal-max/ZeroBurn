from __future__ import annotations

from typer.testing import CliRunner
from zeroburn.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    help_text = result.stdout
    for cmd in ["run", "stats", "plan", "mark-confidential", "ping", "init"]:
        assert cmd in help_text
