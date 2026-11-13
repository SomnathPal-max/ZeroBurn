"""Read cache tracking previously read file ranges to avoid redundant tokens."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ReadCache:
    """Cache of (path, start, end) -> (sha256, turn).
    
    If the exact content at (path, start, end) has been read before, returns
    a compact stub: {"status":"unchanged", "hash":"<8 chars>"}.
    Any write to path invalidates all cached ranges for that path.
    """
    def __init__(self) -> None:
        # (normalized_path, start, end) -> (sha256_hex, turn)
        self._entries: dict[tuple[str, int, int], tuple[str, int]] = {}

    def normalize_path(self, path: str | Path) -> str:
        return str(Path(path)).replace("\\", "/")

    def get_stub_or_record(
        self,
        path: str | Path,
        start: int,
        end: int,
        content: str,
        turn: int = 0,
    ) -> str | None:
        norm_path = self.normalize_path(path)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        key = (norm_path, start, end)

        if key in self._entries:
            prev_hash, _ = self._entries[key]
            if prev_hash == content_hash:
                short_hash = content_hash[:8]
                return json.dumps({"status": "unchanged", "hash": short_hash})

        self._entries[key] = (content_hash, turn)
        return None

    def invalidate(self, path: str | Path) -> int:
        norm_path = self.normalize_path(path)
        keys_to_remove = [k for k in self._entries if k[0] == norm_path]
        for k in keys_to_remove:
            del self._entries[k]
        return len(keys_to_remove)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
