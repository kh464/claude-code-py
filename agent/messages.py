from __future__ import annotations

from typing import Any


def _build_synthetic_tool_result(tool_use_id: str, tool_name: str | None) -> dict[str, Any]:
    return {
        "role": "tool",
        "name": tool_name or "unknown",
        "tool_use_id": tool_use_id,
        "is_error": True,
        "content": {
            "status": "error",
            "content": f"Missing tool_result for tool_use_id {tool_use_id}",
        },
    }


def normalize_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_tool_use_ids: set[str] = set()
    seen_tool_result_ids: set[str] = set()
    ordered_tool_use_ids: list[str] = []
    tool_use_name_by_id: dict[str, str] = {}
    generated_counter = 0

    for message in messages:
        message_copy = dict(message)
        if message_copy.get("role") == "assistant" and isinstance(message_copy.get("tool_uses"), list):
            deduped_tool_uses: list[dict[str, Any]] = []
            for tool_use in message_copy["tool_uses"]:
                if not isinstance(tool_use, dict):
                    continue
                tool_use_copy = dict(tool_use)
                tool_use_id = str(tool_use_copy.get("id", "")).strip()
                if not tool_use_id:
                    generated_counter += 1
                    tool_use_id = f"generated-tool-use-{generated_counter}"
                    tool_use_copy["id"] = tool_use_id
                if tool_use_id in seen_tool_use_ids:
                    continue
                seen_tool_use_ids.add(tool_use_id)
                ordered_tool_use_ids.append(tool_use_id)
                if "name" in tool_use_copy:
                    tool_use_name_by_id[tool_use_id] = str(tool_use_copy["name"])
                deduped_tool_uses.append(tool_use_copy)

            if deduped_tool_uses:
                message_copy["tool_uses"] = deduped_tool_uses
            else:
                message_copy.pop("tool_uses", None)
        normalized.append(message_copy)

    filtered: list[dict[str, Any]] = []
    for message in normalized:
        if message.get("role") != "tool":
            filtered.append(message)
            continue
        tool_use_id = message.get("tool_use_id")
        if not isinstance(tool_use_id, str):
            continue
        if tool_use_id not in seen_tool_use_ids:
            continue
        if tool_use_id in seen_tool_result_ids:
            continue
        seen_tool_result_ids.add(tool_use_id)
        filtered.append(dict(message))

    missing_ids = [tool_use_id for tool_use_id in ordered_tool_use_ids if tool_use_id not in seen_tool_result_ids]
    for tool_use_id in missing_ids:
        filtered.append(
            _build_synthetic_tool_result(
                tool_use_id=tool_use_id,
                tool_name=tool_use_name_by_id.get(tool_use_id),
            )
        )
    return filtered
