from __future__ import annotations

import pytest

from agent.contracts import ToolContext
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.query_loop import QueryLoop
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


class RecordingModel:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def generate(self, messages, tools):
        _ = tools
        copied = [dict(message) for message in messages]
        self.calls.append(copied)
        return {"content": "done", "tool_uses": []}


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_query_loop_injects_memory_blocks_into_prompt_messages() -> None:
    model = RecordingModel()
    loop = QueryLoop(model_client=model, runtime=_build_runtime())
    context = ToolContext(
        session_id="session-memory",
        metadata={"memory_injections": ["Project memory: use pytest", "User memory: prefer concise output"]},
    )

    await loop.run([{"role": "user", "content": "start"}], context=context)

    assert model.calls
    first_call_messages = model.calls[0]
    assert first_call_messages[0]["role"] == "system"
    assert "Project memory: use pytest" in first_call_messages[0]["content"]
    assert "User memory: prefer concise output" in first_call_messages[0]["content"]


@pytest.mark.asyncio
async def test_query_loop_compacts_when_over_token_budget() -> None:
    model = RecordingModel()
    loop = QueryLoop(
        model_client=model,
        runtime=_build_runtime(),
        max_context_chars=260,
        compaction_keep_last=3,
    )
    long_messages = [{"role": "user", "content": f"message-{i}-" + ("x" * 120)} for i in range(8)]

    transcript = await loop.run(long_messages)

    compacted_markers = [
        message
        for message in transcript
        if message.get("role") == "system" and "[compacted]" in str(message.get("content", ""))
    ]
    assert compacted_markers


@pytest.mark.asyncio
async def test_query_loop_compaction_preserves_memory_message() -> None:
    model = RecordingModel()
    loop = QueryLoop(
        model_client=model,
        runtime=_build_runtime(),
        max_context_chars=220,
        compaction_keep_last=2,
    )
    context = ToolContext(
        session_id="session-memory-compact",
        metadata={"memory_injections": ["Memory A", "Memory B"]},
    )
    long_messages = [{"role": "user", "content": f"chunk-{i}-" + ("z" * 100)} for i in range(6)]

    transcript = await loop.run(long_messages, context=context)

    memory_messages = [
        message
        for message in transcript
        if message.get("role") == "system" and "[memory]" in str(message.get("content", ""))
    ]
    assert memory_messages
