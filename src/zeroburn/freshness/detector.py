"""Stale SDK and breaking change error detector."""
from __future__ import annotations

import re
from pathlib import Path


ERROR_PATTERNS = [
    # ModuleNotFoundError: No module named 'xyz'
    (r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", "module"),
    # ImportError: cannot import name 'abc' from 'xyz'
    (r"ImportError:\s+cannot import name ['\"]([^'\"]+)['\"](?:\s+from\s+['\"]([^'\"]+)['\"])?", "import"),
    # AttributeError: ... has no attribute 'abc'
    (r"AttributeError:\s+(?:module\s+['\"]?([a-zA-Z0-9_.]+)['\"]?\s+)?has no attribute ['\"]([^'\"]+)['\"]", "attribute"),
    # TypeError: ... unexpected keyword argument 'abc'
    (r"TypeError:\s+(?:[a-zA-Z0-9_.]+\(\)\s+)?got an unexpected keyword argument ['\"]([^'\"]+)['\"]", "keyword"),
    # DeprecationWarning
    (r"DeprecationWarning:\s*(.*)", "deprecation"),
    # RemovedIn...
    (r"RemovedIn[a-zA-Z0-9_.]*:\s*(.*)", "removed"),
]


def detect_stale_error(output: str) -> tuple[bool, str, str]:
    """Detect if build/test output contains stale SDK error classes.
    
    Returns: (is_stale, package_name, symbol_name)
    """
    for pattern, kind in ERROR_PATTERNS:
        match = re.search(pattern, output)
        if match:
            groups = match.groups()
            if kind == "module":
                pkg = groups[0].split(".")[0]
                return True, pkg, ""
            elif kind == "import":
                symbol = groups[0]
                pkg = groups[1].split(".")[0] if len(groups) > 1 and groups[1] else symbol
                return True, pkg, symbol
            elif kind == "attribute":
                pkg = groups[0].split(".")[0] if groups[0] else ""
                symbol = groups[1] if len(groups) > 1 else ""
                return True, pkg, symbol
            elif kind == "keyword":
                symbol = groups[0]
                return True, "", symbol
            else:
                raw_text = groups[0] if groups else ""
                words = re.findall(r"[a-zA-Z0-9_]+", raw_text)
                pkg = words[0] if words else ""
                symbol = words[1] if len(words) > 1 else ""
                return True, pkg, symbol

    return False, "", ""


def extract_package_version(repo_root: Path | str, package: str) -> str:
    """Attempt to extract package version from requirements.txt or pyproject.toml."""
    if not package:
        return ""
    root = Path(repo_root).resolve()

    # 1. requirements.txt
    req_file = root / "requirements.txt"
    if req_file.is_file():
        try:
            for line in req_file.read_text(encoding="utf-8").splitlines():
                if line.strip().lower().startswith(package.lower()):
                    match = re.search(r"==\s*([0-9a-zA-Z_.-]+)", line)
                    if match:
                        return match.group(1)
        except Exception:
            pass

    # 2. pyproject.toml
    toml_file = root / "pyproject.toml"
    if toml_file.is_file():
        try:
            content = toml_file.read_text(encoding="utf-8")
            match = re.search(rf'"{re.escape(package)}[><=~^]*([0-9.]+)"', content, re.IGNORECASE)
            if match:
                return match.group(1)
        except Exception:
            pass

    return ""
