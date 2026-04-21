from __future__ import annotations

import pytest

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
async def test_powershell_tool_executes_command_successfully() -> None:
    runtime = _build_runtime()
    result = await runtime.execute_tool_use(
        "PowerShellTool",
        {"command": "Write-Output 'hello-ps'"},
    )

    payload = result["raw_result"]
    assert payload["exit_code"] == 0
    assert "hello-ps" in payload["stdout"]
    assert payload["timed_out"] is False


@pytest.mark.asyncio
async def test_powershell_tool_timeout_marks_result() -> None:
    runtime = _build_runtime()
    result = await runtime.execute_tool_use(
        "PowerShellTool",
        {"command": "Start-Sleep -Seconds 2; Write-Output 'late'", "timeout_ms": 100},
    )

    payload = result["raw_result"]
    assert payload["timed_out"] is True
    assert payload["interrupted"] is True


@pytest.mark.asyncio
async def test_bash_tool_rejects_dangerous_command() -> None:
    runtime = _build_runtime()
    with pytest.raises(ValueError, match="dangerous command"):
        await runtime.execute_tool_use(
            "BashTool",
            {"command": "rm -rf /"},
        )


@pytest.mark.asyncio
async def test_powershell_tool_rejects_dangerous_command() -> None:
    runtime = _build_runtime()
    with pytest.raises(ValueError, match="dangerous command"):
        await runtime.execute_tool_use(
            "PowerShellTool",
            {"command": "Remove-Item -Recurse -Force C:\\"},
        )
