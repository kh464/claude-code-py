from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from agent.errors import MCPError
from agent.mcp_integration.stdio_transport import StdioMCPClient
from agent.mcp_integration.transport import MCPRequest, invoke_with_retry


@dataclass(slots=True)
class MCPServerState:
    name: str
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    resources: dict[str, str] = field(default_factory=dict)
    connected: bool = True
    transport: dict[str, Any] | None = None


class MCPManager:
    def __init__(self) -> None:
        self._servers: dict[str, MCPServerState] = {}
        self._stdio_clients: dict[str, StdioMCPClient] = {}

    def register_server(
        self,
        name: str,
        *,
        tools: Mapping[str, Mapping[str, Any] | None] | None = None,
        resources: Mapping[str, str] | None = None,
        connected: bool = True,
        transport: Mapping[str, Any] | None = None,
    ) -> None:
        normalized_tools: dict[str, dict[str, Any]] = {}
        for tool_name, config in (tools or {}).items():
            normalized_tools[str(tool_name)] = dict(config or {})

        normalized_resources = {str(uri): str(content) for uri, content in (resources or {}).items()}
        normalized_transport = dict(transport or {}) if transport is not None else None
        self._servers[str(name)] = MCPServerState(
            name=str(name),
            tools=normalized_tools,
            resources=normalized_resources,
            connected=bool(connected),
            transport=normalized_transport,
        )
        # Reset old client after server re-registration.
        existing = self._stdio_clients.pop(str(name), None)
        if existing is not None:
            existing.close()

    def _is_stdio_server(self, state: MCPServerState) -> bool:
        transport = state.transport or {}
        transport_type = str(transport.get("type", "")).strip().lower()
        return transport_type == "stdio"

    def _get_stdio_client(self, state: MCPServerState) -> StdioMCPClient:
        if not self._is_stdio_server(state):
            raise MCPError(f"MCP server {state.name} is not configured for stdio transport")
        cached = self._stdio_clients.get(state.name)
        if cached is not None:
            return cached
        transport = dict(state.transport or {})
        command_raw = transport.get("command", [])
        if isinstance(command_raw, str):
            command = [command_raw]
        elif isinstance(command_raw, list):
            command = [str(part).strip() for part in command_raw if str(part).strip()]
        else:
            command = []
        if not command:
            raise MCPError(f"stdio transport command missing for MCP server: {state.name}")
        env_raw = transport.get("env", {})
        env: dict[str, str] = {}
        if isinstance(env_raw, Mapping):
            for key, value in env_raw.items():
                env[str(key)] = str(value)
        timeout_s = float(transport.get("timeout_s", 8.0))
        client = StdioMCPClient(
            command=command,
            cwd=str(transport["cwd"]) if transport.get("cwd") else None,
            env=env,
            timeout_s=timeout_s,
        )
        self._stdio_clients[state.name] = client
        return client

    def ensure_server(self, name: str) -> MCPServerState:
        server = self._servers.get(name)
        if server is None:
            raise MCPError(f"MCP server not found: {name}")
        return server

    def list_server_names(self) -> list[str]:
        return sorted(self._servers.keys())

    def list_tools(self, server: str | None = None) -> list[dict[str, str]]:
        if server is not None:
            state = self.ensure_server(server)
            if self._is_stdio_server(state):
                client = self._get_stdio_client(state)
                listed = client.list_tools()
                names: list[str] = []
                for item in listed:
                    if not isinstance(item, Mapping):
                        continue
                    name = str(item.get("name", "")).strip()
                    if not name:
                        continue
                    names.append(name)
                if names:
                    state.tools = {name: dict(state.tools.get(name, {})) for name in names}
            return [
                {"server": state.name, "name": tool_name, "full_name": f"mcp__{state.name}__{tool_name}"}
                for tool_name in sorted(state.tools.keys())
            ]

        all_tools: list[dict[str, str]] = []
        for server_name in self.list_server_names():
            all_tools.extend(self.list_tools(server_name))
        return all_tools

    def list_server_tool_names(self, server: str) -> list[str]:
        state = self.ensure_server(server)
        if self._is_stdio_server(state):
            _ = self.list_tools(server)
        return sorted(state.tools.keys())

    def list_resources(self, server: str) -> list[dict[str, str]]:
        state = self.ensure_server(server)
        if self._is_stdio_server(state):
            client = self._get_stdio_client(state)
            listed = client.list_resources()
            return [
                {"uri": str(item.get("uri", "")), "server": state.name}
                for item in listed
                if isinstance(item, Mapping) and str(item.get("uri", "")).strip()
            ]
        return [{"uri": uri, "server": state.name} for uri in sorted(state.resources.keys())]

    def read_resource(self, server: str, uri: str) -> dict[str, str]:
        state = self.ensure_server(server)
        if self._is_stdio_server(state):
            client = self._get_stdio_client(state)
            payload = client.read_resource(uri)
            if "content" in payload:
                content = str(payload.get("content", ""))
            elif "contents" in payload and isinstance(payload["contents"], list) and payload["contents"]:
                first = payload["contents"][0]
                if isinstance(first, Mapping):
                    content = str(first.get("text", first.get("content", "")))
                else:
                    content = str(first)
            else:
                content = str(payload)
            return {"server": state.name, "uri": uri, "content": content}
        if uri not in state.resources:
            raise MCPError(f"MCP resource not found: {uri}")
        return {"server": state.name, "uri": uri, "content": state.resources[uri]}

    def set_connected(self, server: str, connected: bool) -> None:
        state = self.ensure_server(server)
        state.connected = bool(connected)
        if not state.connected:
            client = self._stdio_clients.pop(state.name, None)
            if client is not None:
                client.close()

    @staticmethod
    def _runtime_profile() -> str:
        profile = str(os.getenv("PY_AGENT_PROFILE", "")).strip().lower()
        if profile in {"prod", "production"}:
            return "prod"
        if profile in {"test", "testing"}:
            return "test"
        if os.getenv("PYTEST_CURRENT_TEST"):
            return "test"
        return "prod"

    def _allow_simulated_modes(self, config: Mapping[str, Any]) -> bool:
        explicit = config.get("allow_simulated")
        if explicit is None:
            return False
        return bool(explicit) and self._runtime_profile() == "test" and bool(os.getenv("PYTEST_CURRENT_TEST"))

    def _invoke_tool_once(self, server: str, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        state = self.ensure_server(server)
        if tool not in state.tools:
            raise MCPError(f"MCP tool not found: {server}/{tool}")
        config = state.tools[tool]
        transient_failures = int(config.get("transient_failures", 0))
        if transient_failures > 0:
            config["transient_failures"] = transient_failures - 1
            raise MCPError(f"transient: MCP transport failure for {server}/{tool}")

        recovered = False
        if not state.connected:
            if bool(config.get("auto_reconnect", False)):
                state.connected = True
                recovered = True
            else:
                raise MCPError(f"MCP server disconnected: {server}")

        mode = str(config.get("mode", "echo"))
        if mode in {"echo", "constant"} and not self._allow_simulated_modes(config):
            raise MCPError(f"simulated MCP tool mode '{mode}' is disabled in production profile")
        if mode == "echo":
            result = {
                "server": server,
                "tool": tool,
                "arguments": dict(arguments),
            }
            if recovered:
                result["recovered"] = True
            return result
        if mode == "constant":
            result = {"server": server, "tool": tool, "result": config.get("result")}
            if recovered:
                result["recovered"] = True
            return result
        raise MCPError(f"Unsupported MCP tool mode: {mode}")

    def _invoke_tool_stdio_once(self, server: str, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        state = self.ensure_server(server)
        if not state.connected:
            raise MCPError(f"MCP server disconnected: {server}")
        client = self._get_stdio_client(state)
        payload = client.call_tool(tool, arguments)
        result: dict[str, Any] = {
            "server": server,
            "tool": tool,
            "arguments": dict(arguments),
        }
        if isinstance(payload, Mapping):
            if "structuredContent" in payload:
                result["result"] = payload["structuredContent"]
            elif "result" in payload:
                result["result"] = payload["result"]
            else:
                result["result"] = dict(payload)
            if "content" in payload:
                result["content"] = payload["content"]
            if "isError" in payload:
                result["isError"] = bool(payload.get("isError"))
        else:
            result["result"] = payload
        return result

    def invoke_tool(self, server: str, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        state = self.ensure_server(server)
        is_stdio = self._is_stdio_server(state)
        if not is_stdio and tool not in state.tools:
            raise MCPError(f"MCP tool not found: {server}/{tool}")
        config = state.tools.get(tool, {})

        request = MCPRequest(server=server, tool=tool, arguments=dict(arguments))
        max_attempts = int(config.get("max_attempts", 3))
        base_delay_s = float(config.get("retry_base_delay_s", 0.05))
        return invoke_with_retry(
            request=request,
            invoker=(
                (lambda: self._invoke_tool_stdio_once(server, tool, arguments))
                if is_stdio
                else (lambda: self._invoke_tool_once(server, tool, arguments))
            ),
            max_attempts=max_attempts,
            base_delay_s=base_delay_s,
        )
