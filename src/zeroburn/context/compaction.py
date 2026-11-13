"""Context compaction eliding old tool outputs and invalidating read cache."""
from __future__ import annotations

import re
from typing import Any

from zeroburn.context.read_cache import ReadCache


def estimate_message_tokens(messages: list[dict[str, Any]], chars_per_token: int = 4) -> int:
    total_chars = 0
    for m in messages:
        if content := m.get("content"):
            total_chars += len(content)
        if tool_calls := m.get("tool_calls"):
            total_chars += len(str(tool_calls))
    return max(1, total_chars // chars_per_token)


def compact_messages(
    messages: list[dict[str, Any]],
    read_cache: ReadCache | None = None,
    compact_at_tokens: int = 6000,
    target_token_limit: int | None = None,
    chars_per_token: int = 4,
) -> tuple[list[dict[str, Any]], int]:
    """Elide older tool results when context exceeds limit.
    
    Rules:
    - Keep system prompt (index 0).
    - Keep user task (index 1).
    - Keep last 4 messages.
    - Replace older tool outputs with one-line stubs.
    - Call read_cache.invalidate(path) for every elided read so it can be re-read.
    Returns (compacted_messages, number_of_elisions).
    """
    threshold = target_token_limit or compact_at_tokens
    current_tokens = estimate_message_tokens(messages, chars_per_token=chars_per_token)

    if current_tokens <= threshold:
        return messages, 0

    if len(messages) <= 6:
        # Not enough messages to safely elide
        return messages, 0

    # Indices to protect: 0 (system), 1 (task), and the last 4 messages
    protect_head = 2
    protect_tail_start = len(messages) - 4

    elisions = 0
    new_messages: list[dict[str, Any]] = []

    for idx, msg in enumerate(messages):
        if idx < protect_head or idx >= protect_tail_start:
            new_messages.append(msg)
            continue

        role = msg.get("role")
        content = msg.get("content", "")

        if role == "tool" and isinstance(content, str):
            # Extract tool name from XML tag <tool_result name=...>
            tool_match = re.search(r'<tool_result name=([^>\s]+)>', content)
            tool_name = tool_match.group(1) if tool_match else "tool"
            
            # Approximate path from content
            path_match = re.search(r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)', content)
            path_str = path_match.group(1) if path_match else ""

            # Invalidate read cache for elided read
            if read_cache and path_str:
                read_cache.invalidate(path_str)

            tokens_saved = max(1, len(content) // chars_per_token)
            stub_text = f"[elided: {tool_name} {path_str}, ~{tokens_saved} tokens; re-read if needed]"
            new_msg = dict(msg)
            new_msg["content"] = f"<tool_result name={tool_name}>\n{stub_text}\n</tool_result>"
            new_messages.append(new_msg)
            elisions += 1
        else:
            new_messages.append(msg)

    # Secondary compaction: if still over threshold, summarize older assistant messages
    post_tokens = estimate_message_tokens(new_messages, chars_per_token=chars_per_token)
    if post_tokens > threshold:
        # Combine older middle assistant messages into a single summary stub
        compressed: list[dict[str, Any]] = []
        for idx, msg in enumerate(new_messages):
            if idx < protect_head or idx >= len(new_messages) - 4:
                compressed.append(msg)
            else:
                if msg.get("role") == "assistant" and msg.get("content"):
                    short_content = msg["content"][:80].replace("\n", " ")
                    compressed.append({
                        "role": "assistant",
                        "content": f"[summary: {short_content}...]",
                    })
                else:
                    compressed.append(msg)
        return compressed, elisions

    return new_messages, elisions
