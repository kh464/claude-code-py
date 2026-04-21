from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .budget import estimate_messages_tokens


def _is_memory_message(message: Mapping[str, Any]) -> bool:
    return message.get("role") == "system" and "[memory]" in str(message.get("content", ""))


def _is_compaction_message(message: Mapping[str, Any]) -> bool:
    return message.get("role") == "system" and "[compacted]" in str(message.get("content", ""))


def _find_latest_tool_pair_indices(messages: list[dict[str, Any]]) -> set[int]:
    for tool_index in range(len(messages) - 1, -1, -1):
        message = messages[tool_index]
        if message.get("role") != "tool":
            continue
        tool_use_id = str(message.get("tool_use_id", "")).strip()
        if not tool_use_id:
            continue
        for assistant_index in range(tool_index - 1, -1, -1):
            candidate = messages[assistant_index]
            if candidate.get("role") != "assistant":
                continue
            tool_uses = candidate.get("tool_uses", [])
            if not isinstance(tool_uses, list):
                continue
            for tool_use in tool_uses:
                if str(tool_use.get("id", "")).strip() == tool_use_id:
                    return {assistant_index, tool_index}
            # assistant message reached without matching tool id: continue searching older assistant
        return {tool_index}
    return set()


def compact_messages(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int,
    compaction_keep_last: int = 8,
) -> list[dict[str, Any]]:
    if max_tokens <= 0:
        return messages
    if estimate_messages_tokens(messages) <= max_tokens:
        return messages

    keep_last = max(1, int(compaction_keep_last))
    memory_indices = {
        index
        for index, message in enumerate(messages)
        if isinstance(message, Mapping) and _is_memory_message(message)
    }
    tail_indices = set(range(max(0, len(messages) - keep_last), len(messages)))
    tool_pair_indices = _find_latest_tool_pair_indices(messages)
    kept_indices = memory_indices | tail_indices | tool_pair_indices
    kept = [messages[index] for index in sorted(kept_indices)]

    removed_count = max(0, len(messages) - len(kept))
    compacted_marker = {
        "role": "system",
        "content": f"[compacted] removed {removed_count} messages to fit token budget",
    }
    if removed_count > 0 and not any(
        isinstance(message, Mapping) and _is_compaction_message(message) for message in kept
    ):
        first_non_memory = 0
        for idx, message in enumerate(kept):
            if not (isinstance(message, Mapping) and _is_memory_message(message)):
                first_non_memory = idx
                break
        kept.insert(first_non_memory, compacted_marker)

    removable_positions = [
        index
        for index, message in enumerate(kept)
        if not (
            isinstance(message, Mapping)
            and (_is_memory_message(message) or _is_compaction_message(message))
        )
    ]
    while estimate_messages_tokens(kept) > max_tokens and removable_positions:
        remove_pos = removable_positions.pop(0)
        kept.pop(remove_pos)
        removable_positions = [
            pos - 1 if pos > remove_pos else pos for pos in removable_positions if pos != remove_pos
        ]

    if estimate_messages_tokens(kept) > max_tokens:
        for message in kept:
            if isinstance(message, Mapping) and _is_memory_message(message):
                message["content"] = "[memory]\n- compacted memory summary"
                break

    return kept
