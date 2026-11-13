"""Tests for configuration loading and validation."""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from zeroburn.config import load_config, ZeroBurnConfig, ModelsConfig


def test_default_config() -> None:
    cfg = load_config()
    assert cfg.models.local.startswith("ollama/")
    assert cfg.budget.user_limit_usd > 0
    assert cfg.agent.max_steps == 25


def test_missing_price_fails_fast() -> None:
    with pytest.raises(ValueError, match="missing from prices_usd_per_million"):
        ZeroBurnConfig(
            models=ModelsConfig(
                local="ollama/unknown-model:latest",
                light_chain=["ollama/unknown-model:latest"],
                heavy_chain=["ollama/unknown-model:latest"],
            ),
            prices_usd_per_million={},
        )


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIFROST_URL", "http://custom-host:9000/v1")
    monkeypatch.setenv("ZEROBURN_USER", "custom_tester")
    cfg = load_config()
    assert cfg.bifrost_url == "http://custom-host:9000/v1"
    assert cfg.zeroburn_user == "custom_tester"
