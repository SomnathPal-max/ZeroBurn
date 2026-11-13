"""Filesystem sandbox enforcing repository boundaries and path restrictions."""
from __future__ import annotations

import os
from pathlib import Path
from zeroburn.errors import PolicyViolation


def resolve(repo_root: Path | str, path: str | Path) -> Path:
    """Resolve path to realpath and strictly ensure it is inside repo_root.
    
    Blocks parent traversal (..) and symlinks escaping repo_root.
    """
    root = Path(repo_root).resolve()
    target = (root / path).resolve()

    try:
        target.relative_to(root)
    except ValueError:
        raise PolicyViolation(
            f"Path traversal detected: '{path}' resolves to '{target}' which is outside repo root '{root}'."
        )

    return target


def check_write(repo_root: Path | str, target_path: Path | str) -> None:
    """Verify that writing to target_path is permitted by sandbox policy.
    
    Deny list: writes to .git/, .zeroburn/, zeroburn.toml, .env*
    """
    root = Path(repo_root).resolve()
    target = resolve(root, target_path)
    rel_path = target.relative_to(root)
    parts = rel_path.parts

    # Check root-level protected files
    if parts:
        first_part = parts[0]
        # .git/
        if first_part == ".git":
            raise PolicyViolation("Sandbox policy violation: writes to .git/ are strictly forbidden.")
        # .zeroburn/
        if first_part == ".zeroburn":
            raise PolicyViolation("Sandbox policy violation: writes to .zeroburn/ are strictly forbidden.")
        # zeroburn.toml
        if first_part == "zeroburn.toml":
            raise PolicyViolation("Sandbox policy violation: writes to zeroburn.toml are strictly forbidden.")
        # .env*
        if first_part.startswith(".env"):
            raise PolicyViolation(f"Sandbox policy violation: writes to '{first_part}' are strictly forbidden.")


def is_sensitive_read(repo_root: Path | str, target_path: Path | str) -> bool:
    """Check if reading target_path is sensitive (.env*, *.pem, id_rsa*).
    
    Reads of sensitive files require explicit user approval (treated as SHELL-level action).
    """
    root = Path(repo_root).resolve()
    target = resolve(root, target_path)
    name = target.name.lower()

    if name.startswith(".env"):
        return True
    if name.endswith(".pem"):
        return True
    if name.startswith("id_rsa"):
        return True

    return False
