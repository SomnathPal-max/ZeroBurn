"""Confidential repo detection and marker management."""
from __future__ import annotations

from pathlib import Path
import tomllib


def is_confidential(repo_root: Path | str) -> bool:
    """Check if repository is marked confidential.
    
    A repo is confidential if:
    1. The marker file .zeroburn/confidential exists at the repo root.
    2. zeroburn.toml in the repo contains `confidential = true`.
    """
    root = Path(repo_root).resolve()
    marker = root / ".zeroburn" / "confidential"
    if marker.is_file():
        return True

    repo_toml = root / "zeroburn.toml"
    if repo_toml.is_file():
        try:
            with open(repo_toml, "rb") as f:
                data = tomllib.load(f)
                if data.get("confidential") is True:
                    return True
        except Exception:
            pass

    return False


def mark_confidential(repo_root: Path | str) -> Path:
    """Create .zeroburn/confidential at repo root."""
    root = Path(repo_root).resolve()
    target_dir = root / ".zeroburn"
    target_dir.mkdir(parents=True, exist_ok=True)
    marker = target_dir / "confidential"
    marker.write_text("confidential=true\n", encoding="utf-8")
    return marker
