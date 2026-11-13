"""Tavily web freshness client for resolving breaking changes and stale imports."""
from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
import httpx
from tavily import TavilyClient

from zeroburn.freshness.cache import FreshnessCache
from zeroburn.freshness.detector import detect_stale_error, extract_package_version


class TavilyFreshnessClient:
    def __init__(self, api_key: str, cache: FreshnessCache | None = None) -> None:
        self.api_key = api_key
        self.cache = cache or FreshnessCache()
        self.client = TavilyClient(api_key=api_key)

    def lookup(
        self,
        package: str,
        version: str,
        symbol: str,
        max_inject_tokens: int = 600,
        chars_per_token: int = 4,
    ) -> tuple[str, float]:
        """Perform targeted search and return untrusted web notes with freshness score."""
        parts = [p for p in (package, version, "breaking change migration", symbol) if p]
        query = " ".join(parts).strip()

        # 1. Check disk cache
        if cached := self.cache.get(query):
            return cached["content"], cached["freshness_score"]

        # 2. Query Tavily
        try:
            res = self.client.search(query=query, max_results=3, search_depth="basic")
            results = res.get("results", [])
        except Exception as exc:
            return f"<untrusted_web_notes>\nSearch error: {exc}\n</untrusted_web_notes>", 0.0

        mention_count = 0
        urls: list[str] = []
        snippets: list[str] = []

        for item in results:
            url = item.get("url", "")
            title = item.get("title", "")
            content = item.get("content", "")
            if url:
                urls.append(url)
            snippets.append(f"[{title}] {content}")
            if symbol and symbol.lower() in content.lower():
                mention_count += 1

        freshness_score = min(1.0, mention_count / 2.0)
        retrieval_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        max_chars = max_inject_tokens * chars_per_token
        combined_snippets = "\n".join(snippets)
        if len(combined_snippets) > max_chars:
            combined_snippets = combined_snippets[:max_chars] + "... [truncated]"

        message_content = (
            f"<untrusted_web_notes>\n"
            f"Query: {query}\n"
            f"Retrieval Date: {retrieval_date}\n"
            f"Source URLs:\n" + "\n".join(f"- {u}" for u in urls) + "\n\n"
            f"Notes:\n{combined_snippets}\n"
            f"</untrusted_web_notes>"
        )

        # 3. Store in cache
        self.cache.set(
            query,
            {
                "content": message_content,
                "freshness_score": freshness_score,
                "urls": urls,
            },
        )

        return message_content, freshness_score


def maybe_freshness_lookup(output: str, session: Any) -> bool:
    """Conditionally run a freshness check on shell output.
    
    Safety guardrails:
    - NEVER runs on confidential repos.
    - Skipped if TAVILY_API_KEY is missing or freshness is disabled.
    - Capped at max_lookups_per_task.
    """
    if getattr(session, "confidential", False):
        return False

    cfg = getattr(session, "config", None)
    if not cfg or not cfg.freshness.enabled:
        return False

    api_key = cfg.tavily_api_key
    if not api_key:
        return False

    current_count = getattr(session, "freshness_lookups_count", 0)
    if current_count >= cfg.freshness.max_lookups_per_task:
        return False

    is_stale, pkg, sym = detect_stale_error(output)
    if not is_stale:
        return False

    version = extract_package_version(session.repo_root, pkg)
    client = TavilyFreshnessClient(api_key=api_key)
    notes, score = client.lookup(
        package=pkg,
        version=version,
        symbol=sym,
        max_inject_tokens=cfg.freshness.max_inject_tokens,
        chars_per_token=cfg.budget.chars_per_token,
    )

    session.freshness_lookups_count = current_count + 1
    session.messages.append({"role": "user", "content": notes})
    return True
