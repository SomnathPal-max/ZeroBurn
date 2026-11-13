"""Read tools for repository exploration."""
from __future__ import annotations

import re
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from zeroburn.policy import sandbox
from zeroburn.context.repo_map import generate_repo_map, is_binary_string, SKIP_DIRS
from zeroburn.context import readers
from zeroburn.context.read_cache import ReadCache


def search_code(
    pattern: str,
    path: str | None,
    max_results: int = 20,
    repo_root: Path | str = ".",
) -> str:
    """Search for regex pattern across files, returning up to max_results matches."""
    root = Path(repo_root).resolve()
    target_dir = sandbox.resolve(root, path) if path else root

    # 1. Use ripgrep if installed
    rg_bin = shutil.which("rg")
    if rg_bin:
        cmd = [rg_bin, "-n", "-e", pattern, "--max-count", str(max_results)]
        try:
            res = subprocess.run(
                cmd,
                cwd=target_dir,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=10,
            )
            if res.returncode in (0, 1):
                lines = res.stdout.splitlines()[:max_results]
                results = []
                for line in lines:
                    results.append(line[:160])
                return "\n".join(results) if results else "No matches found."
        except Exception:
            pass

    # 2. Fallback to Python re
    matches: list[str] = []
    try:
        regex = re.compile(pattern)
    except Exception as exc:
        return f"Invalid regex pattern: {exc}"

    for dirpath, dirnames, filenames in os.walk(target_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            file_path = Path(dirpath) / f
            try:
                rel_path = str(file_path.relative_to(root)).replace("\\", "/")
                with open(file_path, "rb") as fp:
                    if is_binary_string(fp.read(1024)):
                        continue
                with open(file_path, "r", encoding="utf-8", errors="replace") as fp:
                    for line_no, line in enumerate(fp, start=1):
                        line_clean = line.rstrip("\r\n")
                        if regex.search(line_clean):
                            snippet = line_clean[:160]
                            matches.append(f"{rel_path}:{line_no}: {snippet}")
                            if len(matches) >= max_results:
                                return "\n".join(matches)
            except Exception:
                continue

    return "\n".join(matches) if matches else "No matches found."
