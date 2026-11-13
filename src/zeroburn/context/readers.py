"""Targeted code readers: read_range, get_symbol, and size-capped read_file."""
from __future__ import annotations

from pathlib import Path
import tree_sitter
import tree_sitter_python

from zeroburn.policy.sandbox import resolve
from zeroburn.context.read_cache import ReadCache

_TS_LANG = tree_sitter.Language(tree_sitter_python.language())
_TS_PARSER = tree_sitter.Parser(_TS_LANG)


def read_range(
    path: str | Path,
    start: int,
    end: int,
    repo_root: str | Path,
    cache: ReadCache | None = None,
    turn: int = 0,
) -> str:
    """Read a specific line range from a file (max 200 lines).
    
    Returns line-numbered output. If unchanged from a previous read,
    returns a compact cache stub {"status":"unchanged", "hash":"<8 chars>"}.
    """
    target = resolve(repo_root, path)
    if not target.is_file():
        return f"Error: File '{path}' does not exist."

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading file '{path}': {exc}"

    all_lines = content.splitlines()
    total_lines = len(all_lines)

    start = max(1, start)
    if end < start:
        end = start

    # Enforce 200 line maximum per read_range call
    if end - start + 1 > 200:
        end = start + 199

    selected_lines = all_lines[start - 1 : min(end, total_lines)]
    raw_snippet = "\n".join(selected_lines)

    if cache is not None:
        stub = cache.get_stub_or_record(path, start, end, raw_snippet, turn=turn)
        if stub:
            return stub

    # Format with 1-based line numbers
    formatted: list[str] = []
    for idx, line in enumerate(selected_lines, start=start):
        formatted.append(f"{idx:4d} | {line}")

    return "\n".join(formatted)


def read_file(
    path: str | Path,
    repo_root: str | Path,
    cache: ReadCache | None = None,
    turn: int = 0,
    capped: bool = True,
) -> str:
    """Read full file only if 150 lines or fewer (unless capped=False in naive mode).
    
    If > 150 lines and capped=True, instructs the model to use read_range or get_symbol.
    """
    target = resolve(repo_root, path)
    if not target.is_file():
        return f"Error: File '{path}' does not exist."

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading file '{path}': {exc}"

    all_lines = content.splitlines()
    total_lines = len(all_lines)

    if capped and total_lines > 150:
        return (
            f"File '{path}' has {total_lines} lines (> 150 lines limit). "
            f"To save tokens, please use read_range('{path}', start, end) "
            f"or get_symbol('{path}', '<name>')."
        )

    if cache is not None:
        stub = cache.get_stub_or_record(path, 1, max(1, total_lines), content, turn=turn)
        if stub:
            return stub

    formatted = [f"{idx:4d} | {line}" for idx, line in enumerate(all_lines, start=1)]
    return "\n".join(formatted)


def get_symbol(path: str | Path, name: str, repo_root: str | Path) -> str:
    """Extract a function or class definition body via tree-sitter AST."""
    target = resolve(repo_root, path)
    if not target.is_file():
        return f"Error: File '{path}' does not exist."

    try:
        content_bytes = target.read_bytes()
    except Exception as exc:
        return f"Error reading file '{path}': {exc}"

    tree = _TS_PARSER.parse(content_bytes)

    def _find_symbol(node: tree_sitter.Node) -> tree_sitter.Node | None:
        if node.type in ("function_definition", "class_definition"):
            name_node = node.child_by_field_name("name")
            if name_node and content_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8") == name:
                return node
        for child in node.children:
            found = _find_symbol(child)
            if found:
                return found
        return None

    node = _find_symbol(tree.root_node)
    if not node:
        return f"Symbol '{name}' not found in '{path}'."

    symbol_bytes = content_bytes[node.start_byte : node.end_byte]
    return symbol_bytes.decode("utf-8", errors="replace")
