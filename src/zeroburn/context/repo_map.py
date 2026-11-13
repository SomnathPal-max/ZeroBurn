"""Tree-sitter powered repository map generator with token-budget truncation."""
from __future__ import annotations

import os
from pathlib import Path
import pathspec
import tree_sitter
import tree_sitter_python

_TS_LANG = tree_sitter.Language(tree_sitter_python.language())
_TS_PARSER = tree_sitter.Parser(_TS_LANG)

SKIP_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".zeroburn",
    "dist",
    "build",
    ".egg-info",
}


def is_binary_string(bytes_sample: bytes) -> bool:
    return b"\x00" in bytes_sample


def get_py_signatures(content_bytes: bytes) -> list[str]:
    """Parse python code and return formatted class, function, and method signatures."""
    tree = _TS_PARSER.parse(content_bytes)
    signatures: list[str] = []

    def walk(node: tree_sitter.Node, indent_level: int = 2) -> None:
        for child in node.children:
            if child.type == "class_definition":
                name_node = child.child_by_field_name("name")
                body_node = child.child_by_field_name("body")
                if name_node and body_node:
                    raw_sig = content_bytes[child.start_byte : body_node.start_byte].decode("utf-8", errors="replace").strip()
                    # clean up trailing colon and extra whitespace
                    sig = raw_sig.rstrip(":").strip()
                    start_line = child.start_point.row + 1
                    end_line = child.end_point.row + 1
                    indent = " " * indent_level
                    signatures.append(f"{indent}{sig} L{start_line}-{end_line}")
                    walk(body_node, indent_level + 2)

            elif child.type == "function_definition":
                name_node = child.child_by_field_name("name")
                body_node = child.child_by_field_name("body")
                if name_node and body_node:
                    raw_sig = content_bytes[child.start_byte : body_node.start_byte].decode("utf-8", errors="replace").strip()
                    sig = raw_sig.rstrip(":").strip()
                    start_line = child.start_point.row + 1
                    end_line = child.end_point.row + 1
                    indent = " " * indent_level
                    signatures.append(f"{indent}{sig} L{start_line}-{end_line}")

    walk(tree.root_node, indent_level=2)
    return signatures


def generate_repo_map(
    repo_root: Path | str,
    focus: list[str] | None = None,
    task_text: str = "",
    touched_files: set[str] | list[str] | None = None,
    max_tokens: int = 1500,
    chars_per_token: int = 4,
) -> str:
    root = Path(repo_root).resolve()
    focus = [f.replace("\\", "/").lstrip("./") for f in (focus or [])]
    touched = {t.replace("\\", "/").lstrip("./") for t in (touched_files or [])}
    task_words = set(task_text.lower().replace("_", " ").replace("/", " ").replace(".", " ").split())

    # Build pathspec matcher from .gitignore
    patterns: list[str] = list(SKIP_DIRS)
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        try:
            patterns.extend(gitignore.read_text(encoding="utf-8", errors="replace").splitlines())
        except Exception:
            pass
    spec = pathspec.PathSpec.from_lines("gitignore", patterns)

    # Collect candidate files
    candidates: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude skip directories in place
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not spec.match_file(str((Path(dirpath) / d).relative_to(root)))]
        
        for f in filenames:
            file_path = Path(dirpath) / f
            rel_path = str(file_path.relative_to(root)).replace("\\", "/")
            if spec.match_file(rel_path):
                continue

            try:
                stat = file_path.stat()
                if stat.st_size > 500 * 1024:  # Skip files > 500 KB
                    continue
                with open(file_path, "rb") as fp:
                    header = fp.read(1024)
                    if is_binary_string(header):
                        continue
            except Exception:
                continue

            # Read line count
            try:
                line_count = len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                continue

            # Compute rank score: (in_focus: 100, task_overlap: 50, touched: 25)
            score = 0
            if rel_path in focus or any(f_item in rel_path for f_item in focus):
                score += 100
            
            # Word overlap with task text
            rel_words = set(rel_path.lower().replace("_", " ").replace("/", " ").replace(".", " ").split())
            overlap = len(task_words & rel_words)
            score += overlap * 10

            if rel_path in touched:
                score += 25

            candidates.append({
                "rel_path": rel_path,
                "abs_path": file_path,
                "line_count": line_count,
                "score": score,
                "is_py": file_path.suffix == ".py",
            })

    # Sort candidates by score descending, then path ascending
    candidates.sort(key=lambda x: (-x["score"], x["rel_path"]))

    max_chars = max_tokens * chars_per_token
    lines: list[str] = []
    current_chars = 0
    included_count = 0

    for idx, c in enumerate(candidates):
        block: list[str] = [f"{c['rel_path']} ({c['line_count']} lines)"]
        if c["is_py"]:
            try:
                sigs = get_py_signatures(c["abs_path"].read_bytes())
                block.extend(sigs)
            except Exception:
                pass

        block_text = "\n".join(block) + "\n"
        if current_chars + len(block_text) > max_chars and included_count > 0:
            remaining = len(candidates) - included_count
            lines.append(f"... {remaining} more files")
            break

        lines.append("\n".join(block))
        current_chars += len(block_text)
        included_count += 1

    return "\n".join(lines)
