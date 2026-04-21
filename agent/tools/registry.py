from __future__ import annotations

from typing import Iterable

from agent.contracts import ToolDef
from agent.mcp_integration import MCPManager

from .builtin import build_builtin_tools, build_dynamic_mcp_tools


class ToolRegistry:
    def __init__(self, *, include_conditionals: bool = True) -> None:
        self.mcp_manager = MCPManager()
        self._tools: dict[str, ToolDef] = {}
        for tool in build_builtin_tools(include_conditionals=include_conditionals, mcp_manager=self.mcp_manager):
            self.register(tool)

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.metadata.name] = tool

    def get(self, name: str) -> ToolDef:
        return self._tools[name]

    def get_all_base_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def register_mcp_server(
        self,
        server: str,
        *,
        tools: dict[str, dict] | None = None,
        resources: dict[str, str] | None = None,
        connected: bool = True,
    ) -> None:
        self.mcp_manager.register_server(
            server,
            tools=tools or {},
            resources=resources or {},
            connected=connected,
        )

    def inject_mcp_tools(self, server: str, tool_names: Iterable[str] | None = None) -> None:
        names = list(tool_names) if tool_names is not None else self.mcp_manager.list_server_tool_names(server)
        for tool in build_dynamic_mcp_tools(server, names, mcp_manager=self.mcp_manager):
            self.register(tool)

    def sync_mcp_tools(self, server: str) -> None:
        prefix = f"mcp__{server}__"
        stale = [name for name in self._tools.keys() if name.startswith(prefix)]
        for name in stale:
            del self._tools[name]
        self.inject_mcp_tools(server, None)
