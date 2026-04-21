from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.workspace_isolation.worktree import WorktreeManager


class EnterWorktreeTool(ToolDef):
    metadata = ToolMetadata(name="EnterWorktreeTool")
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": [],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, manager: WorktreeManager) -> None:
        self.manager = manager

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = can_use_tool, parent_message
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "entering"})
        return self.manager.enter(
            name=str(args["name"]) if args.get("name") else None,
            context=context,
        )
