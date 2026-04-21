from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentDescriptor:
    name: str
    description: str | None = None
    conditional: bool = False
    sdk_entry: bool = True
    tools_allowlist: list[str] = field(default_factory=list)
    tools_disallowlist: list[str] = field(default_factory=list)
    permission_mode: str | None = None
    model: str | None = None
    mcp_servers: list[str] = field(default_factory=list)
    hooks: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    system_prompt: str | None = None
    background: bool = False
    isolation: str | None = None
    initial_prompt: str | None = None
