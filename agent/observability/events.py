from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


EVENT_TYPES = (
    "tool_use_started",
    "tool_progress",
    "tool_result",
    "tool_error",
    "permission_decision",
    "agent_spawned",
    "agent_completed",
    "agent_failed",
)


@dataclass(slots=True)
class AgentEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
