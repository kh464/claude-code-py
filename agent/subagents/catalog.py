from __future__ import annotations

from .models import AgentDescriptor


_BUILTIN_AGENTS: tuple[AgentDescriptor, ...] = (
    AgentDescriptor("general-purpose"),
    AgentDescriptor("statusline-setup"),
    AgentDescriptor("Explore", conditional=True),
    AgentDescriptor("Plan", conditional=True),
    AgentDescriptor("claude-code-guide", sdk_entry=False),
    AgentDescriptor("verification", conditional=True),
)


def get_built_in_agents(*, include_conditionals: bool = True) -> list[AgentDescriptor]:
    if include_conditionals:
        return list(_BUILTIN_AGENTS)
    return [agent for agent in _BUILTIN_AGENTS if not agent.conditional]
