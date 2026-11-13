"""Write tools for editing and creating files with diff generation and approval."""
from __future__ import annotations

import difflib
from pathlib import Path

from zeroburn.policy import sandbox
from zeroburn.policy.approval import ActionKind, ActionRequest, ApprovalGate
from zeroburn.context.read_cache import ReadCache


def apply_edit(
    path: str,
    old: str,
    new: str,
    repo_root: Path | str,
    gate: ApprovalGate,
    cache: ReadCache | None = None,
) -> str:
    """Apply an exact string replacement in a file after building a diff and getting approval."""
    root = Path(repo_root).resolve()
    target = sandbox.resolve(root, path)
    sandbox.check_write(root, target)

    if not target.is_file():
        return f"Error: File '{path}' does not exist."

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Error reading '{path}': {exc}"

    matches = content.count(old)
    if matches == 0:
        return f"Error: The old string was not found in '{path}'."
    if matches > 1:
        return (
            f"Error: The old string occurs {matches} times in '{path}'. "
            f"Edits require an exact unique match. Provide more surrounding context lines."
        )

    # Perform substitution
    new_content = content.replace(old, new, 1)

    # Generate unified diff for user inspection
    old_lines = content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    if not diff:
        diff = f"No visible line changes in {path}."

    req = ActionRequest(
        kind=ActionKind.WRITE,
        summary=f"Edit file: {path}",
        detail=diff,
    )
    # Human approval gate
    gate.require(req)

    # Apply edit on approved
    target.write_text(new_content, encoding="utf-8")

    if cache is not None:
        cache.invalidate(path)

    return f"Successfully updated '{path}'."


def create_file(
    path: str,
    content: str,
    repo_root: Path | str,
    gate: ApprovalGate,
    cache: ReadCache | None = None,
) -> str:
    """Create a new file in the repository after getting approval."""
    root = Path(repo_root).resolve()
    target = sandbox.resolve(root, path)
    sandbox.check_write(root, target)

    if target.exists():
        return f"Error: File '{path}' already exists. Use apply_edit instead."

    preview_content = content if len(content) <= 3000 else content[:3000] + "\n... [truncated]"
    req = ActionRequest(
        kind=ActionKind.WRITE,
        summary=f"Create file: {path}",
        detail=f"+++ {path}\n{preview_content}",
    )
    gate.require(req)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    if cache is not None:
        cache.invalidate(path)

    return f"Successfully created '{path}'."
