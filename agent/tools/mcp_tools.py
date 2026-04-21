from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.mcp_integration import MCPManager


class DynamicMcpTool(ToolDef):
    input_schema = {"type": "object", "properties": {}, "required": []}
    output_schema = {"type": "object"}

    def __init__(self, *, manager: MCPManager, server: str, tool_name: str) -> None:
        self.manager = manager
        self.server = server
        self.tool_name = tool_name
        self.metadata = ToolMetadata(name=f"mcp__{server}__{tool_name}")

    def is_read_only(self) -> bool:
        return True

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message
        on_progress(
            {
                "event": "tool_progress",
                "tool": self.metadata.name,
                "stage": "invoking",
                "server": self.server,
            }
        )
        return self.manager.invoke_tool(self.server, self.tool_name, args)


class ListMcpResourcesTool(ToolDef):
    metadata = ToolMetadata(name="ListMcpResourcesTool")
    input_schema = {
        "type": "object",
        "properties": {
            "server": {"type": "string"},
        },
        "required": ["server"],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, manager: MCPManager) -> None:
        self.manager = manager

    def is_read_only(self) -> bool:
        return True

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message, on_progress
        server = str(args["server"])
        return {"server": server, "resources": self.manager.list_resources(server)}


class ReadMcpResourceTool(ToolDef):
    metadata = ToolMetadata(name="ReadMcpResourceTool")
    input_schema = {
        "type": "object",
        "properties": {
            "server": {"type": "string"},
            "uri": {"type": "string"},
        },
        "required": ["server", "uri"],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, manager: MCPManager) -> None:
        self.manager = manager

    def is_read_only(self) -> bool:
        return True

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message, on_progress
        server = str(args["server"])
        uri = str(args["uri"])
        return self.manager.read_resource(server, uri)


class ToolSearchTool(ToolDef):
    metadata = ToolMetadata(name="ToolSearchTool")
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "server": {"type": "string"},
        },
        "required": ["query"],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, manager: MCPManager) -> None:
        self.manager = manager

    def is_read_only(self) -> bool:
        return True

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message, on_progress
        query = str(args.get("query", "")).strip().lower()
        server = str(args["server"]) if args.get("server") else None
        tools = self.manager.list_tools(server)
        filtered = [tool for tool in tools if query in tool["name"].lower() or query in tool["full_name"].lower()]
        return {"query": query, "results": filtered}
