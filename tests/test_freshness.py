"""Unit tests for targeted web freshness lookups with Tavily."""
from __future__ import annotations

import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from zeroburn.config import ZeroBurnConfig, FreshnessConfig
from zeroburn.freshness.detector import detect_stale_error
from zeroburn.freshness.cache import FreshnessCache
from zeroburn.freshness.tavily_client import TavilyFreshnessClient, maybe_freshness_lookup


def test_detector_matches_only_listed_error_classes() -> None:
    # 1. ModuleNotFoundError
    stale, pkg, sym = detect_stale_error("ModuleNotFoundError: No module named 'pydantic_settings'")
    assert stale is True
    assert pkg == "pydantic_settings"

    # 2. ImportError
    stale, pkg, sym = detect_stale_error("ImportError: cannot import name 'BaseSettings' from 'pydantic'")
    assert stale is True
    assert pkg == "pydantic"
    assert sym == "BaseSettings"

    # 3. AttributeError
    stale, pkg, sym = detect_stale_error("AttributeError: module 'openai' has no attribute 'ChatCompletion'")
    assert stale is True
    assert pkg == "openai"
    assert sym == "ChatCompletion"

    # 4. TypeError
    stale, pkg, sym = detect_stale_error("TypeError: create() got an unexpected keyword argument 'headers'")
    assert stale is True
    assert sym == "headers"

    # 5. DeprecationWarning
    stale, pkg, sym = detect_stale_error("DeprecationWarning: Function 'old_fn' is deprecated and will be removed.")
    assert stale is True

    # 6. RemovedIn
    stale, pkg, sym = detect_stale_error("RemovedInDjango40Warning: 'request_headers' has been removed.")
    assert stale is True

    # Non-stale errors should NOT trigger
    assert detect_stale_error("AssertionError: 1 != 2")[0] is False
    assert detect_stale_error("ZeroDivisionError: division by zero")[0] is False
    assert detect_stale_error("FileNotFoundError: No such file or directory")[0] is False


def test_confidential_session_never_calls_tavily(tmp_path: Path) -> None:
    session = SimpleNamespace(
        confidential=True,  # Confidential repo!
        repo_root=tmp_path,
        config=ZeroBurnConfig(
            freshness=FreshnessConfig(enabled=True),
            tavily_api_key="tvly-mock-key",
        ),
        freshness_lookups_count=0,
        messages=[],
    )

    with patch("zeroburn.freshness.tavily_client.TavilyFreshnessClient") as mock_client_cls:
        triggered = maybe_freshness_lookup(
            "ModuleNotFoundError: No module named 'foo'",
            session,
        )
        assert triggered is False
        assert session.freshness_lookups_count == 0
        assert not mock_client_cls.called


def test_tavily_token_capping_and_cache_hit(tmp_path: Path) -> None:
    cache = FreshnessCache(cache_path=tmp_path / "freshness_cache.json")
    client = TavilyFreshnessClient(api_key="tvly-mock-key", cache=cache)

    mock_search_results = {
        "results": [
            {
                "url": "https://example.com/migration",
                "title": "Migration Guide",
                "content": "In version 2.0 BaseSettings was moved. " * 200,  # Long content
            }
        ]
    }

    client.client.search = MagicMock(return_value=mock_search_results)

    # First lookup: network call made and cached
    msg, score = client.lookup(
        package="pydantic",
        version="2.0",
        symbol="BaseSettings",
        max_inject_tokens=100,  # Limit to 100 tokens = 400 chars
        chars_per_token=4,
    )

    assert "<untrusted_web_notes>" in msg
    assert "https://example.com/migration" in msg
    assert client.client.search.call_count == 1
    # Check max inject tokens ceiling
    assert len(msg) <= 100 * 4 + 200  # bounded by max_inject_tokens chars

    # Second lookup: EXACT SAME QUERY -> CACHE HIT! (No network call)
    client.client.search.reset_mock()
    cached_msg, cached_score = client.lookup(
        package="pydantic",
        version="2.0",
        symbol="BaseSettings",
        max_inject_tokens=100,
        chars_per_token=4,
    )

    assert cached_msg == msg
    assert cached_score == score
    assert not client.client.search.called
