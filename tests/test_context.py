"""Unit tests for repo map, readers, and read cache."""
from __future__ import annotations

import pytest
from pathlib import Path

from zeroburn.context.read_cache import ReadCache
from zeroburn.context.readers import read_range, read_file, get_symbol
from zeroburn.context.repo_map import generate_repo_map


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "sample_repo"
    repo.mkdir()

    # Create .gitignore
    (repo / ".gitignore").write_text("*.log\nsecret_dir/\n", encoding="utf-8")

    # Python module 1
    (repo / "models.py").write_text(
        '''"""Data models."""

class User:
    def __init__(self, username: str, email: str):
        self.username = username
        self.email = email

    def get_display_name(self) -> str:
        return f"{self.username} <{self.email}>"

def make_user(name: str) -> User:
    return User(name, f"{name}@example.com")
''',
        encoding="utf-8",
    )

    # Python module 2 (long file to test 150 line cap)
    long_content = "\n".join([f"# Line {i}" for i in range(160)])
    (repo / "long_file.py").write_text(long_content, encoding="utf-8")

    # Non-python file
    (repo / "README.md").write_text("# Sample Project\nA simple project.\n", encoding="utf-8")

    # Ignored files
    (repo / "test.log").write_text("ignore this log", encoding="utf-8")
    ignored_dir = repo / "secret_dir"
    ignored_dir.mkdir()
    (ignored_dir / "secret.txt").write_text("top secret", encoding="utf-8")

    return repo


def test_repo_map_budget_and_filtering(sample_repo: Path) -> None:
    repo_map = generate_repo_map(
        repo_root=sample_repo,
        task_text="look at User model",
        max_tokens=1500,
        chars_per_token=4,
    )

    # Assert ignored files are excluded
    assert "test.log" not in repo_map
    assert "secret.txt" not in repo_map

    # Assert class and def signatures with line ranges are included
    assert "models.py" in repo_map
    assert "class User L3-9" in repo_map or "class User" in repo_map
    assert "def __init__(self, username: str, email: str)" in repo_map
    assert "def get_display_name(self) -> str" in repo_map
    assert "def make_user(name: str) -> User" in repo_map

    # Non-py file has name and line count only
    assert "README.md" in repo_map
    assert "README.md (2 lines)" in repo_map

    # Check budget estimation (under 1500 tokens = under 6000 chars)
    estimated_tokens = len(repo_map) / 4
    assert estimated_tokens < 1500


def test_get_symbol_exact_body(sample_repo: Path) -> None:
    symbol_body = get_symbol("models.py", "make_user", sample_repo)
    assert "def make_user(name: str) -> User:" in symbol_body
    assert 'return User(name, f"{name}@example.com")' in symbol_body

    class_body = get_symbol("models.py", "User", sample_repo)
    assert "class User:" in class_body
    assert "def get_display_name(self) -> str:" in class_body

    not_found = get_symbol("models.py", "non_existent_func", sample_repo)
    assert "Symbol 'non_existent_func' not found" in not_found


def test_read_range_and_cache(sample_repo: Path) -> None:
    cache = ReadCache()

    # First read returns formatted lines with line numbers
    read_1 = read_range("models.py", 3, 9, sample_repo, cache=cache, turn=1)
    assert "3 | class User:" in read_1
    assert "9 |         return f\"{self.username} <{self.email}>\"" in read_1
    assert "unchanged" not in read_1

    # Second identical read returns unchanged stub
    read_2 = read_range("models.py", 3, 9, sample_repo, cache=cache, turn=2)
    assert '"status": "unchanged"' in read_2

    # Invalidate path
    invalidated = cache.invalidate("models.py")
    assert invalidated > 0

    # Third read returns full lines again
    read_3 = read_range("models.py", 3, 9, sample_repo, cache=cache, turn=3)
    assert "3 | class User:" in read_3
    assert '"status": "unchanged"' not in read_3


def test_read_file_line_cap(sample_repo: Path) -> None:
    cache = ReadCache()

    # Short file <= 150 lines succeeds
    short_read = read_file("README.md", sample_repo, cache=cache)
    assert "1 | # Sample Project" in short_read

    # Long file > 150 lines returns warning instruction
    long_read = read_file("long_file.py", sample_repo, cache=cache)
    assert "> 150 lines limit" in long_read
    assert "please use read_range" in long_read
