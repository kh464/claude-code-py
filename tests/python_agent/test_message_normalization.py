from __future__ import annotations

from agent.messages import normalize_tool_messages


def test_normalize_tool_messages_dedupes_tool_use_ids() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "run tools",
            "tool_uses": [
                {"id": "u1", "name": "FileReadTool", "arguments": {"path": "a.py"}},
                {"id": "u1", "name": "FileReadTool", "arguments": {"path": "a.py"}},
                {"id": "u2", "name": "GlobTool", "arguments": {"path": ".", "pattern": "*.py"}},
            ],
        }
    ]

    normalized = normalize_tool_messages(messages)
    tool_uses = normalized[0]["tool_uses"]
    assert [tool_use["id"] for tool_use in tool_uses] == ["u1", "u2"]


def test_normalize_tool_messages_removes_orphan_results_and_inserts_missing() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "need tools",
            "tool_uses": [
                {"id": "u1", "name": "FileReadTool", "arguments": {"path": "a.py"}},
                {"id": "u2", "name": "GrepTool", "arguments": {"path": ".", "pattern": "TODO"}},
            ],
        },
        {"role": "tool", "name": "FileReadTool", "tool_use_id": "u1", "content": {"status": "success"}},
        {"role": "tool", "name": "UnknownTool", "tool_use_id": "orphan", "content": {"status": "success"}},
    ]

    normalized = normalize_tool_messages(messages)
    tool_messages = [message for message in normalized if message.get("role") == "tool"]
    tool_use_ids = [message["tool_use_id"] for message in tool_messages]

    assert "orphan" not in tool_use_ids
    assert "u1" in tool_use_ids
    assert "u2" in tool_use_ids
    synthetic = next(message for message in tool_messages if message["tool_use_id"] == "u2")
    assert synthetic["is_error"] is True
    assert "Missing tool_result" in synthetic["content"]["content"]
