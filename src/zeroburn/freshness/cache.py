"""Disk cache for Tavily freshness lookups keyed by query sha256."""
from __future__ import annotations

import os
import json
import hashlib
from pathlib import Path
from typing import Any


def get_default_cache_path() -> Path:
    if custom := os.environ.get("ZEROBURN_HOME"):
        base = Path(custom)
    else:
        base = Path.home() / ".zeroburn"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        base = Path(".zeroburn")
        base.mkdir(parents=True, exist_ok=True)
    return base / "freshness_cache.json"


class FreshnessCache:
    def __init__(self, cache_path: Path | None = None) -> None:
        self.cache_path = cache_path or get_default_cache_path()

    def _hash(self, query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()

    def load(self) -> dict[str, Any]:
        if not self.cache_path.is_file():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def get(self, query: str) -> dict[str, Any] | None:
        key = self._hash(query)
        data = self.load()
        return data.get(key)

    def set(self, query: str, result: dict[str, Any]) -> None:
        key = self._hash(query)
        data = self.load()
        data[key] = result
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
