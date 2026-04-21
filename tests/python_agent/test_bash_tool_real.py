from __future__ import annotations

import asyncio

import pytest

from agent.errors import ToolInterruptedError
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_bash_tool_executes_command_successfully() -> None:
    runtime = _build_runtime()
    result = await runtime.execute_tool_use(
        "BashTool",
        {"command": 'python -c "print(\'hello-bash\')"'},
    )

    payload = result["raw_result"]
    assert payload["exit_code"] == 0
    assert "hello-bash" in payload["stdout"]
    assert payload["timed_out"] is False


@pytest.mark.asyncio
async def test_bash_tool_timeout_marks_result() -> None:
    runtime = _build_runtime()
    result = await runtime.execute_tool_use(
        "BashTool",
        {"command": 'python -c "import time; time.sleep(2); print(\'late\')"', "timeout_ms": 100},
    )

    payload = result["raw_result"]
    assert payload["timed_out"] is True
    assert payload["interrupted"] is True


@pytest.mark.asyncio
async def test_bash_tool_emits_progress_events() -> None:
    runtime = _build_runtime()
    result = await runtime.execute_tool_use(
        "BashTool",
        {
            "command": 'python -c "import sys,time; print(\'line-a\'); sys.stdout.flush(); time.sleep(0.2); print(\'line-b\')"',
            "timeout_ms": 5000,
        },
    )

    events = result["progress_events"]
    assert any(event.get("stage") == "spawned" for event in events)
    assert any(event.get("stream") == "stdout" for event in events)


@pytest.mark.asyncio
async def test_bash_tool_interruption_raises_interrupted_error() -> None:
    runtime = _build_runtime()
    task = asyncio.create_task(
        runtime.execute_tool_use(
            "BashTool",
            {"command": 'python -c "import time; time.sleep(5)"', "timeout_ms": 10000},
        )
    )
    await asyncio.sleep(0.2)
    task.cancel()

    with pytest.raises(ToolInterruptedError):
        await task
