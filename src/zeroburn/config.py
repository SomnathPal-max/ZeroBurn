"""Configuration models and loading logic for ZeroBurn."""
from __future__ import annotations

import os
import sys
import getpass
from pathlib import Path
from typing import Literal
import tomllib
from pydantic import BaseModel, Field, model_validator


class ModelsConfig(BaseModel):
    local: str = "ollama/llama3.1:8b"
    light_chain: list[str] = Field(
        default_factory=lambda: ["openai/gpt-4o-mini", "ollama/llama3.1:8b"]
    )
    heavy_chain: list[str] = Field(
        default_factory=lambda: ["openai/gpt-4o", "openai/gpt-4o-mini", "ollama/llama3.1:8b"]
    )


class BudgetConfig(BaseModel):
    user_limit_usd: float = 2.00
    warn_at: float = 0.75
    downshift_at: float = 0.75
    on_limit: Literal["local_only", "stop"] = "local_only"
    chars_per_token: int = 4


class FailoverConfig(BaseModel):
    retries_per_model: int = 1
    backoff_seconds: float = 1.0
    request_timeout_s: float = 60.0


class AgentConfig(BaseModel):
    max_steps: int = 25
    max_tokens_per_call: int = 1500
    tool_result_max_chars: int = 4000
    compact_at_tokens: int = 6000
    explore_with_light: bool = True


class FreshnessConfig(BaseModel):
    enabled: bool = True
    max_lookups_per_task: int = 2
    max_inject_tokens: int = 600


class ZeroBurnConfig(BaseModel):
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    prices_usd_per_million: dict[str, list[float]] = Field(
        default_factory=lambda: {
            "openai/gpt-4o": [2.50, 10.00],
            "openai/gpt-4o-mini": [0.15, 0.60],
            "ollama/llama3.1:8b": [0.0, 0.0],
            "ollama/llama3.2:latest": [0.0, 0.0],
            "ollama/qwen2.5:3b-instruct": [0.0, 0.0],
        }
    )
    context_limits: dict[str, int] = Field(
        default_factory=lambda: {
            "openai/gpt-4o": 128000,
            "openai/gpt-4o-mini": 128000,
            "ollama/llama3.1:8b": 8000,
            "ollama/llama3.2:latest": 131072,
            "ollama/qwen2.5:3b-instruct": 32768,
        }
    )
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    failover: FailoverConfig = Field(default_factory=FailoverConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    freshness: FreshnessConfig = Field(default_factory=FreshnessConfig)

    # Environment variables
    bifrost_url: str = "http://localhost:8080/v1"
    bifrost_vk_standard: str = "sk-bf-standard"
    bifrost_vk_confidential: str = "sk-bf-confidential"
    tavily_api_key: str | None = None
    zeroburn_user: str = Field(default_factory=lambda: getpass.getuser())

    @model_validator(mode="after")
    def validate_model_prices(self) -> ZeroBurnConfig:
        required_models = set(self.models.light_chain) | set(self.models.heavy_chain) | {self.models.local}
        for m in required_models:
            if m not in self.prices_usd_per_million:
                raise ValueError(
                    f"Configuration error: Model '{m}' is configured in models chain/local, "
                    f"but missing from prices_usd_per_million."
                )
        return self


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("\"'")
        if k not in os.environ:
            os.environ[k] = v


def load_config(repo_root: Path | str | None = None) -> ZeroBurnConfig:
    # 1. Load .env if present (first check repo_root, then current dir)
    if repo_root:
        load_env_file(Path(repo_root) / ".env")
    load_env_file(Path(".env"))

    # 2. Config file discovery: repo zeroburn.toml > ~/.zeroburn/zeroburn.toml
    config_dict: dict = {}
    repo_toml = Path(repo_root) / "zeroburn.toml" if repo_root else Path("zeroburn.toml")
    user_toml = Path.home() / ".zeroburn" / "zeroburn.toml"

    toml_path: Path | None = None
    if repo_toml.is_file():
        toml_path = repo_toml
    elif user_toml.is_file():
        toml_path = user_toml

    if toml_path:
        with open(toml_path, "rb") as f:
            config_dict = tomllib.load(f)

    # 3. Environment variables overrides
    env_overrides: dict = {}
    if url := os.environ.get("BIFROST_URL"):
        env_overrides["bifrost_url"] = url
    if vk_std := os.environ.get("BIFROST_VK_STANDARD"):
        env_overrides["bifrost_vk_standard"] = vk_std
    if vk_conf := os.environ.get("BIFROST_VK_CONFIDENTIAL"):
        env_overrides["bifrost_vk_confidential"] = vk_conf
    if tavily := os.environ.get("TAVILY_API_KEY"):
        env_overrides["tavily_api_key"] = tavily
    if user := os.environ.get("ZEROBURN_USER"):
        env_overrides["zeroburn_user"] = user

    config_dict.update(env_overrides)

    return ZeroBurnConfig(**config_dict)
