"""Test for zeroburn ping CLI command."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from zeroburn.cli import app
from zeroburn.gateway.client import LLMResult

runner = CliRunner()


def test_ping_command_mocked() -> None:
    fake_res_std = LLMResult(
        content="ok",
        tool_calls=[],
        prompt_tokens=2,
        completion_tokens=1,
        served_model="openai/gpt-4o-mini",
        latency_ms=120,
    )
    fake_res_conf = LLMResult(
        content="ok",
        tool_calls=[],
        prompt_tokens=2,
        completion_tokens=1,
        served_model="ollama/llama3.1:8b",
        latency_ms=80,
    )

    with patch("zeroburn.gateway.client.GatewayClient.chat", side_effect=[fake_res_std, fake_res_conf]):
        result = runner.invoke(app, ["ping"])
        assert result.exit_code == 0
        assert "Standard key OK! Served by: openai/gpt-4o-mini" in result.stdout
        assert "Confidential key OK! Served by: ollama/llama3.1:8b" in result.stdout
