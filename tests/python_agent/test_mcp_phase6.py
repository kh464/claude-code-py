from __future__ import annotations

import pytest

from agent.errors import ToolExecutionError
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


def _build_runtime_and_registry() -> tuple[ToolRuntime, ToolRegistry]:
    registry = ToolRegistry(include_conditionals=True)
    runtime = ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )
    return runtime, registry


@pytest.mark.asyncio
async def test_dynamic_mcp_tool_invokes_registered_server() -> None:
    runtime, registry = _build_runtime_and_registry()
    registry.register_mcp_server(
        "github",
        tools={"search_issues": {"mode": "echo", "allow_simulated": True}},
        resources={"repo://README": "# hello\n"},
    )
    registry.inject_mcp_tools("github", ["search_issues"])
    runtime.tools = {tool.metadata.name: tool for tool in registry.get_all_base_tools()}

    result = await runtime.execute_tool_use(
        "mcp__github__search_issues",
        {"query": "bug"},
    )
    payload = result["raw_result"]
    assert payload["server"] == "github"
    assert payload["tool"] == "search_issues"
    assert payload["arguments"]["query"] == "bug"


@pytest.mark.asyncio
async def test_mcp_resource_tools_list_and_read() -> None:
    runtime, registry = _build_runtime_and_registry()
    registry.register_mcp_server(
        "docs",
        tools={},
        resources={
            "doc://overview": "overview content",
            "doc://api": "api content",
        },
    )
    runtime.tools = {tool.metadata.name: tool for tool in registry.get_all_base_tools()}

    listed = await runtime.execute_tool_use("ListMcpResourcesTool", {"server": "docs"})
    resources = listed["raw_result"]["resources"]
    assert len(resources) == 2
    assert any(item["uri"] == "doc://overview" for item in resources)

    read = await runtime.execute_tool_use("ReadMcpResourceTool", {"server": "docs", "uri": "doc://api"})
    payload = read["raw_result"]
    assert payload["server"] == "docs"
    assert payload["uri"] == "doc://api"
    assert payload["content"] == "api content"


@pytest.mark.asyncio
async def test_mcp_tool_recovers_from_disconnect_when_auto_reconnect_enabled() -> None:
    runtime, registry = _build_runtime_and_registry()
    registry.register_mcp_server(
        "ops",
        connected=False,
        tools={"ping": {"mode": "echo", "auto_reconnect": True, "allow_simulated": True}},
        resources={},
    )
    registry.inject_mcp_tools("ops", ["ping"])
    runtime.tools = {tool.metadata.name: tool for tool in registry.get_all_base_tools()}

    result = await runtime.execute_tool_use("mcp__ops__ping", {"value": "x"})
    payload = result["raw_result"]
    assert payload["server"] == "ops"
    assert payload["tool"] == "ping"
    assert payload["arguments"]["value"] == "x"
    assert payload["recovered"] is True


@pytest.mark.asyncio
async def test_mcp_tool_errors_when_disconnected_without_auto_reconnect() -> None:
    runtime, registry = _build_runtime_and_registry()
    registry.register_mcp_server(
        "ops",
        connected=False,
        tools={"ping": {"mode": "echo", "auto_reconnect": False, "allow_simulated": True}},
        resources={},
    )
    registry.inject_mcp_tools("ops", ["ping"])
    runtime.tools = {tool.metadata.name: tool for tool in registry.get_all_base_tools()}

    with pytest.raises(ToolExecutionError, match="disconnected"):
        await runtime.execute_tool_use("mcp__ops__ping", {"value": "x"})


def test_registry_can_sync_mcp_tools_when_server_capabilities_change() -> None:
    _, registry = _build_runtime_and_registry()
    registry.register_mcp_server(
        "dyn",
        tools={"search": {"mode": "echo", "allow_simulated": True}},
        resources={},
    )
    registry.sync_mcp_tools("dyn")
    assert "mcp__dyn__search" in registry.list_names()

    registry.register_mcp_server(
        "dyn",
        tools={"summarize": {"mode": "echo", "allow_simulated": True}},
        resources={},
    )
    registry.sync_mcp_tools("dyn")
    names = set(registry.list_names())
    assert "mcp__dyn__summarize" in names
    assert "mcp__dyn__search" not in names


def test_mcp_prod_profile_rejects_simulated_modes(monkeypatch) -> None:
    monkeypatch.setenv("PY_AGENT_PROFILE", "prod")
    runtime, registry = _build_runtime_and_registry()
    registry.register_mcp_server(
        "github",
        tools={"search_issues": {"mode": "echo"}},
        resources={},
    )
    registry.inject_mcp_tools("github", ["search_issues"])
    runtime.tools = {tool.metadata.name: tool for tool in registry.get_all_base_tools()}

    with pytest.raises(ToolExecutionError, match="simulated"):
        import asyncio
        asyncio.run(runtime.execute_tool_use("mcp__github__search_issues", {"query": "bug"}))


def test_mcp_simulated_mode_requires_explicit_allow_even_in_test_profile(monkeypatch) -> None:
    monkeypatch.setenv("PY_AGENT_PROFILE", "test")
    runtime, registry = _build_runtime_and_registry()
    registry.register_mcp_server(
        "github",
        tools={"search_issues": {"mode": "echo"}},
        resources={},
    )
    registry.inject_mcp_tools("github", ["search_issues"])
    runtime.tools = {tool.metadata.name: tool for tool in registry.get_all_base_tools()}

    with pytest.raises(ToolExecutionError, match="simulated"):
        import asyncio
        asyncio.run(runtime.execute_tool_use("mcp__github__search_issues", {"query": "bug"}))
