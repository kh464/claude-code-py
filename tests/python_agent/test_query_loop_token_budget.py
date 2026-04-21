from __future__ import annotations

import pytest

from agent.context.compaction import compact_messages
from agent.query_loop import QueryLoop
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


class RecordingModel:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def generate(self, messages, tools):
        _ = tools
        self.calls.append([dict(message) for message in messages])
        return {"content": "done", "tool_uses": []}


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_query_loop_uses_token_budget_not_char_budget() -> None:
    model = RecordingModel()
    loop = QueryLoop(
        model_client=model,
        runtime=_build_runtime(),
        max_context_tokens=40,
        compaction_keep_last=3,
    )
    messages = [
        {"role": "user", "content": f"message {i} " + ("token " * 25)}
        for i in range(8)
    ]
    transcript = await loop.run(messages)

    assert any(
        message.get("role") == "system" and "[compacted]" in str(message.get("content", ""))
        for message in transcript
    )


def test_compact_messages_preserves_memory_and_latest_tool_pair() -> None:
    messages = [
        {"role": "system", "content": "[memory]\n- remember coding style"},
        {"role": "user", "content": "old request " + ("x " * 20)},
        {
            "role": "assistant",
            "content": "run old tool",
            "tool_uses": [{"id": "tool-old", "name": "BriefTool", "arguments": {"text": "old"}}],
        },
        {"role": "tool", "name": "BriefTool", "tool_use_id": "tool-old", "content": {"status": "success"}},
        {"role": "user", "content": "new request " + ("y " * 20)},
        {
            "role": "assistant",
            "content": "run latest tool",
            "tool_uses": [{"id": "tool-new", "name": "BriefTool", "arguments": {"text": "new"}}],
        },
        {"role": "tool", "name": "BriefTool", "tool_use_id": "tool-new", "content": {"status": "success"}},
    ]

    compacted = compact_messages(messages, max_tokens=55, compaction_keep_last=2)

    assert any("[memory]" in str(message.get("content", "")) for message in compacted if message.get("role") == "system")
    assert any(
        message.get("role") == "assistant"
        and any(tool.get("id") == "tool-new" for tool in message.get("tool_uses", []))
        for message in compacted
    )
    assert any(message.get("role") == "tool" and message.get("tool_use_id") == "tool-new" for message in compacted)
