from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.query_loop import QueryLoop
from agent.session_store.store import SessionStore
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


class FakeModel:
    def __init__(self) -> None:
        self.turn = 0

    async def generate(self, messages, tools):
        _ = messages, tools
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "need tool",
                "tool_uses": [{"name": "BriefTool", "arguments": {"text": "hello"}}],
            }
        return {"content": "done", "tool_uses": []}


class FakeModelWithoutToolUseId:
    def __init__(self) -> None:
        self.turn = 0

    async def generate(self, messages, tools):
        _ = messages, tools
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "need id",
                "tool_uses": [{"name": "BriefTool", "arguments": {"text": "hello"}}],
            }
        return {"content": "done", "tool_uses": []}


class FakeModelWithUnknownTool:
    def __init__(self) -> None:
        self.turn = 0

    async def generate(self, messages, tools):
        _ = messages, tools
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "mixed tools",
                "tool_uses": [
                    {"id": "known-1", "name": "BriefTool", "arguments": {"text": "ok"}},
                    {"id": "bad-1", "name": "NoSuchTool", "arguments": {}},
                ],
            }
        return {"content": "done after error", "tool_uses": []}


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"query-loop-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_query_loop_executes_tool_then_stops() -> None:
    loop = QueryLoop(model_client=FakeModel(), runtime=_build_runtime())
    transcript = await loop.run([{"role": "user", "content": "hi"}])

    assert any(item.get("role") == "tool" for item in transcript)
    assert transcript[-1]["role"] == "assistant"
    assert transcript[-1]["content"] == "done"


@pytest.mark.asyncio
async def test_query_loop_assigns_tool_use_ids_and_pairs_results() -> None:
    loop = QueryLoop(model_client=FakeModelWithoutToolUseId(), runtime=_build_runtime())
    transcript = await loop.run([{"role": "user", "content": "hello"}])

    assistant_with_tool = next(
        message for message in transcript if message.get("role") == "assistant" and message.get("tool_uses")
    )
    tool_message = next(message for message in transcript if message.get("role") == "tool")

    tool_use_id = assistant_with_tool["tool_uses"][0]["id"]
    assert tool_use_id
    assert tool_message["tool_use_id"] == tool_use_id


@pytest.mark.asyncio
async def test_query_loop_normalizes_initial_orphan_tool_result() -> None:
    loop = QueryLoop(model_client=FakeModel(), runtime=_build_runtime())
    transcript = await loop.run(
        [
            {"role": "user", "content": "start"},
            {"role": "tool", "name": "FileReadTool", "tool_use_id": "orphan", "content": {"status": "success"}},
        ]
    )

    assert not any(message.get("tool_use_id") == "orphan" for message in transcript if message.get("role") == "tool")


@pytest.mark.asyncio
async def test_query_loop_keeps_running_when_some_tools_fail() -> None:
    loop = QueryLoop(model_client=FakeModelWithUnknownTool(), runtime=_build_runtime())
    transcript = await loop.run([{"role": "user", "content": "run"}])

    tool_messages = [message for message in transcript if message.get("role") == "tool"]
    assert len(tool_messages) >= 2
    assert any(message.get("tool_use_id") == "known-1" and not message.get("is_error") for message in tool_messages)
    assert any(
        message.get("tool_use_id") == "bad-1"
        and message.get("is_error") is True
        and message.get("content", {}).get("status") == "error"
        for message in tool_messages
    )
    assert transcript[-1]["role"] == "assistant"
    assert transcript[-1]["content"] == "done after error"


@pytest.mark.asyncio
async def test_query_loop_can_persist_new_messages_to_session_store() -> None:
    temp_root = _create_temp_dir()
    try:
        store = SessionStore(temp_root / "store")
        loop = QueryLoop(
            model_client=FakeModel(),
            runtime=_build_runtime(),
            session_store=store,
            session_id="session-q1",
        )
        await loop.run([{"role": "user", "content": "persist please"}])

        events = store.load_events("session-q1")
        message_events = [event for event in events if event.get("event") == "message"]
        assert message_events
        assert any(event["message"].get("role") == "assistant" for event in message_events)
        assert any(event["message"].get("role") == "tool" for event in message_events)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
