"""Central tool registry providing concise tool schemas and gated execution."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING
from pathlib import Path

from zeroburn.policy.sandbox import is_sensitive_read, resolve
from zeroburn.policy.approval import ActionKind, ActionRequest, ApprovalGate
from zeroburn.context.repo_map import generate_repo_map
from zeroburn.context import readers
from zeroburn.tools import read_tools, write_tools, shell_tool, git_tool

if TYPE_CHECKING:
    from zeroburn.agent.session import Session


# Concise JSON schemas (descriptions strictly under 15 words)
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "repo_map",
            "description": "Show repository file map and Python symbols.",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of priority file paths.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for regex pattern across files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to match."},
                    "path": {"type": "string", "description": "Subdirectory to restrict search."},
                    "max_results": {"type": "integer", "description": "Maximum match lines."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_range",
            "description": "Read line range from file with line numbers (max 200 lines).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read."},
                    "start": {"type": "integer", "description": "Starting line number (1-based)."},
                    "end": {"type": "integer", "description": "Ending line number (inclusive)."},
                },
                "required": ["path", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_symbol",
            "description": "Extract function or class definition body via tree-sitter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."},
                    "name": {"type": "string", "description": "Symbol or function name."},
                },
                "required": ["path", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read entire file if 150 lines or fewer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_edit",
            "description": "Replace exact unique old string with new string in file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path."},
                    "old": {"type": "string", "description": "Unique exact string to replace."},
                    "new": {"type": "string", "description": "Replacement string."},
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file with specified content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "New file path."},
                    "content": {"type": "string", "description": "Full file content."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run shell command in repository with human approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run."},
                    "timeout_s": {"type": "number", "description": "Command timeout in seconds."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git",
            "description": "Execute git subcommand with arguments and human approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Git subcommand and arguments.",
                    }
                },
                "required": ["args"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Conclude task when done with two-sentence summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Completion summary."},
                },
                "required": ["summary"],
            },
        },
    },
]


class ToolRegistry:
    def __init__(self, gate: ApprovalGate | None = None) -> None:
        self.gate: ApprovalGate = gate or ApprovalGate()

    def get_schemas(self) -> list[dict[str, Any]]:
        return TOOL_SCHEMAS

    def execute(self, name: str, args: dict[str, Any], session: Any) -> str:
        """Execute a tool request within session context and return XML-wrapped result."""
        repo_root = getattr(session, "repo_root", Path("."))
        cache = getattr(session, "read_cache", None)
        turn = getattr(session, "step", 0)
        max_chars = getattr(getattr(session, "config", None), "agent", None)
        tool_result_max_chars = max_chars.tool_result_max_chars if max_chars else 4000

        # In naive mode, disable read cache and size cap
        is_naive = getattr(session, "mode", "zeroburn") == "naive"
        if is_naive:
            cache = None
            read_capped = False
        else:
            read_capped = True

        output = ""
        try:
            if name == "repo_map":
                focus = args.get("focus")
                output = generate_repo_map(
                    repo_root=repo_root,
                    focus=focus,
                    task_text=getattr(session, "task_text", ""),
                    touched_files=touched,
                )

            elif name == "search_code":
                pattern = args["pattern"]
                path = args.get("path")
                max_results = args.get("max_results", 20)
                output = read_tools.search_code(
                    pattern=pattern,
                    path=path,
                    max_results=max_results,
                    repo_root=repo_root,
                )

            elif name == "read_range":
                path = args["path"]
                # Sensitive read check
                if is_sensitive_read(repo_root, path):
                    req = ActionRequest(
                        kind=ActionKind.SHELL,
                        summary=f"Read sensitive file {path}",
                        detail=f"Read sensitive credential/env file {path}",
                    )
                    self.gate.require(req)

                start = int(args["start"])
                end = int(args["end"])
                output = readers.read_range(
                    path=path,
                    start=start,
                    end=end,
                    repo_root=repo_root,
                    cache=cache,
                    turn=turn,
                )

            elif name == "get_symbol":
                path = args["path"]
                symbol_name = args["name"]
                output = readers.get_symbol(
                    path=path,
                    name=symbol_name,
                    repo_root=repo_root,
                )

            elif name == "read_file":
                path = args["path"]
                if is_sensitive_read(repo_root, path):
                    req = ActionRequest(
                        kind=ActionKind.SHELL,
                        summary=f"Read sensitive file {path}",
                        detail=f"Read sensitive credential/env file {path}",
                    )
                    self.gate.require(req)

                output = readers.read_file(
                    path=path,
                    repo_root=repo_root,
                    cache=cache,
                    turn=turn,
                    capped=read_capped,
                )

            elif name == "apply_edit":
                path = args["path"]
                old = args["old"]
                new = args["new"]
                output = write_tools.apply_edit(
                    path=path,
                    old=old,
                    new=new,
                    repo_root=repo_root,
                    gate=self.gate,
                    cache=cache,
                )

            elif name == "create_file":
                path = args["path"]
                content = args["content"]
                output = write_tools.create_file(
                    path=path,
                    content=content,
                    repo_root=repo_root,
                    gate=self.gate,
                    cache=cache,
                )

            elif name == "run_shell":
                cmd = args["command"]
                timeout_s = args.get("timeout_s", 60.0)
                output = shell_tool.run_shell(
                    command=cmd,
                    repo_root=repo_root,
                    gate=self.gate,
                    timeout_s=timeout_s,
                    max_chars=tool_result_max_chars,
                )

            elif name == "git":
                git_args = args.get("args", [])
                output = git_tool.run_git(
                    args=git_args,
                    repo_root=repo_root,
                    gate=self.gate,
                    max_chars=tool_result_max_chars,
                )

            elif name == "finish":
                output = f"Task completed: {args.get('summary', '')}"

            else:
                output = f"Unknown tool: '{name}'"

        except Exception as exc:
            output = f"Tool execution failed: {exc}"

        # Truncate output to tool_result_max_chars
        if len(output) > tool_result_max_chars:
            output = output[:tool_result_max_chars] + f"\n... [truncated to {tool_result_max_chars} chars]"

        return f"<tool_result name={name}>\n{output}\n</tool_result>"
