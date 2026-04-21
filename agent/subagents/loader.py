from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from .catalog import get_built_in_agents
from .models import AgentDescriptor


_SHORT_TOOL_ALIASES: dict[str, str] = {
    "agent": "AgentTool",
    "askuserquestion": "AskUserQuestionTool",
    "bash": "BashTool",
    "brief": "BriefTool",
    "croncreate": "CronCreateTool",
    "crondelete": "CronDeleteTool",
    "cronlist": "CronListTool",
    "edit": "FileEditTool",
    "enterworktree": "EnterWorktreeTool",
    "exitworktree": "ExitWorktreeTool",
    "glob": "GlobTool",
    "grep": "GrepTool",
    "read": "FileReadTool",
    "sendmessage": "SendMessageTool",
    "taskoutput": "TaskOutputTool",
    "taskstop": "TaskStopTool",
    "webfetch": "WebFetchTool",
    "websearch": "WebSearchTool",
    "write": "FileWriteTool",
}


def _normalize_token(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end_index = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index == -1:
        return None
    frontmatter = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).strip()
    return frontmatter, body


def _parse_tool_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("tools/disallowedTools must be a string or list")


def _parse_mcp_servers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        servers: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                servers.append(item.strip())
            elif isinstance(item, Mapping) and item:
                servers.extend(str(key).strip() for key in item.keys() if str(key).strip())
        return servers
    return []


def load_agent_markdown_file(path: str | Path, *, source: str) -> AgentDescriptor | None:
    file_path = Path(path)
    parsed = _split_frontmatter(file_path.read_text(encoding="utf-8"))
    if parsed is None:
        return None

    frontmatter_text, body = parsed
    loaded = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(loaded, Mapping):
        raise ValueError(f"Invalid frontmatter in {file_path}")

    name = str(loaded.get("name", "")).strip()
    description = str(loaded.get("description", "")).strip()
    if not name or not description:
        raise ValueError(f"Agent file requires name/description: {file_path}")

    hooks = loaded.get("hooks", {})
    if hooks is None:
        hooks = {}
    if not isinstance(hooks, Mapping):
        raise ValueError("hooks must be an object")

    return AgentDescriptor(
        name=name,
        description=description,
        conditional=bool(loaded.get("conditional", False)),
        sdk_entry=bool(loaded.get("sdkEntry", True)),
        tools_allowlist=_parse_tool_list(loaded.get("tools")),
        tools_disallowlist=_parse_tool_list(loaded.get("disallowedTools")),
        permission_mode=str(loaded["permissionMode"]).strip() if loaded.get("permissionMode") else None,
        model=str(loaded["model"]).strip() if loaded.get("model") else None,
        mcp_servers=_parse_mcp_servers(loaded.get("mcpServers")),
        hooks=dict(hooks),
        source=source,
        system_prompt=body or None,
        background=bool(loaded.get("background", False)),
        isolation=str(loaded["isolation"]).strip() if loaded.get("isolation") else None,
        initial_prompt=str(loaded["initialPrompt"]).strip() if loaded.get("initialPrompt") else None,
    )


def load_agents_from_directory(path: str | Path | None, *, source: str) -> list[AgentDescriptor]:
    if path is None:
        return []
    root = Path(path)
    if not root.exists() or not root.is_dir():
        return []

    loaded: list[AgentDescriptor] = []
    for file_path in sorted(root.glob("*.md")):
        try:
            descriptor = load_agent_markdown_file(file_path, source=source)
        except Exception:
            continue
        if descriptor is not None:
            loaded.append(descriptor)
    return loaded


def get_active_agents(
    *,
    include_conditionals: bool = True,
    user_agents_dir: str | Path | None = None,
    project_agents_dir: str | Path | None = None,
) -> list[AgentDescriptor]:
    merged: dict[str, AgentDescriptor] = {}
    for descriptor in get_built_in_agents(include_conditionals=include_conditionals):
        merged[descriptor.name] = descriptor
    for descriptor in load_agents_from_directory(user_agents_dir, source="user"):
        merged[descriptor.name] = descriptor
    for descriptor in load_agents_from_directory(project_agents_dir, source="project"):
        merged[descriptor.name] = descriptor
    return list(merged.values())


def _canonical_tool_name(requested: str, available_tools: Iterable[str]) -> str | None:
    requested_name = requested.strip()
    if not requested_name:
        return None
    available = list(available_tools)
    if requested_name in available:
        return requested_name

    requested_norm = _normalize_token(requested_name)
    normalized_to_tool = {_normalize_token(tool): tool for tool in available}
    if requested_norm in normalized_to_tool:
        return normalized_to_tool[requested_norm]

    if requested_norm in _SHORT_TOOL_ALIASES:
        alias_target = _SHORT_TOOL_ALIASES[requested_norm]
        if alias_target in available:
            return alias_target

    if not requested_norm.endswith("tool"):
        candidate = f"{requested_norm}tool"
        if candidate in normalized_to_tool:
            return normalized_to_tool[candidate]

    return None


def resolve_agent_tools(agent: AgentDescriptor, available_tools: Iterable[str]) -> list[str]:
    available = list(available_tools)

    denied: set[str] = set()
    for requested in agent.tools_disallowlist:
        resolved = _canonical_tool_name(requested, available)
        if resolved is not None:
            denied.add(resolved)

    has_explicit_allow = bool(agent.tools_allowlist) and "*" not in agent.tools_allowlist
    if has_explicit_allow:
        allowed: set[str] = set()
        for requested in agent.tools_allowlist:
            resolved = _canonical_tool_name(requested, available)
            if resolved is not None:
                allowed.add(resolved)
    else:
        allowed = set(available)

    return [tool for tool in available if tool in allowed and tool not in denied]
