from __future__ import annotations

import pytest

from agent.contracts import ToolDef, ToolMetadata
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.runtime import ToolRuntime


class RecordingTool(ToolDef):
    metadata = ToolMetadata(name="RecordingTool")
    input_schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    }
    output_schema = {"type": "object"}

    def __init__(self) -> None:
        self.order: list[str] = []

    def validate_input(self, args):
        self.order.append("validate")

    def call(self, args, context, can_use_tool, parent_message, on_progress):
        self.order.append("call")
        on_progress({"event": "tool_progress", "message": "running"})
        return {"value": args["value"]}


class ExplodingTool(ToolDef):
    metadata = ToolMetadata(name="ExplodingTool")
    input_schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    }
    output_schema = {"type": "object"}

    def call(self, args, context, can_use_tool, parent_message, on_progress):
        _ = args, context, can_use_tool, parent_message, on_progress
        raise ValueError("boom")


@pytest.mark.asyncio
async def test_runtime_pipeline_order() -> None:
    tool = RecordingTool()
    order: list[str] = []

    def pre_hook(*_):
        order.append("pre")

    def post_hook(*_):
        order.append("post")

    runtime = ToolRuntime(
        tools={"RecordingTool": tool},
        permission_engine=PermissionEngine([PermissionRule("RecordingTool", PermissionMode.ALLOW, "session")]),
        pre_tool_use_hooks=[pre_hook],
        post_tool_use_hooks=[post_hook],
    )

    result = await runtime.execute_tool_use("RecordingTool", {"value": "ok"})

    assert tool.order == ["validate", "call"]
    assert order == ["pre", "post"]
    assert result["tool_result"]["status"] == "success"
    assert result["progress_events"]


@pytest.mark.asyncio
async def test_runtime_respects_permission_denied() -> None:
    tool = RecordingTool()
    runtime = ToolRuntime(
        tools={"RecordingTool": tool},
        permission_engine=PermissionEngine([PermissionRule("RecordingTool", PermissionMode.DENY, "policy")]),
    )

    with pytest.raises(PermissionError):
        await runtime.execute_tool_use("RecordingTool", {"value": "ok"})

    assert tool.order == ["validate"]


@pytest.mark.asyncio
async def test_runtime_rejects_permission_ask_without_resolver() -> None:
    tool = RecordingTool()
    runtime = ToolRuntime(
        tools={"RecordingTool": tool},
        permission_engine=PermissionEngine([PermissionRule("RecordingTool", PermissionMode.ASK, "session")]),
    )

    with pytest.raises(PermissionError, match="requires approval"):
        await runtime.execute_tool_use("RecordingTool", {"value": "ok"})

    assert tool.order == ["validate"]


@pytest.mark.asyncio
async def test_runtime_allows_permission_ask_with_resolver() -> None:
    tool = RecordingTool()

    async def allow_resolver(*_):
        return True

    runtime = ToolRuntime(
        tools={"RecordingTool": tool},
        permission_engine=PermissionEngine([PermissionRule("RecordingTool", PermissionMode.ASK, "session")]),
        permission_ask_resolver=allow_resolver,
    )

    result = await runtime.execute_tool_use("RecordingTool", {"value": "ok"})
    assert result["raw_result"]["value"] == "ok"
    assert tool.order == ["validate", "call"]


@pytest.mark.asyncio
async def test_runtime_runs_failure_hooks_on_tool_error() -> None:
    failure_log: list[str] = []

    def failure_hook(tool, args, error, context):
        _ = args, context
        failure_log.append(f"{tool.metadata.name}:{type(error).__name__}")

    runtime = ToolRuntime(
        tools={"ExplodingTool": ExplodingTool()},
        permission_engine=PermissionEngine([PermissionRule("ExplodingTool", PermissionMode.ALLOW, "session")]),
        failure_tool_use_hooks=[failure_hook],
    )

    with pytest.raises(Exception):
        await runtime.execute_tool_use("ExplodingTool", {"value": "x"})

    assert failure_log == ["ExplodingTool:ValueError"]
