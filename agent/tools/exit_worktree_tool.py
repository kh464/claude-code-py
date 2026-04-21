from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.workspace_isolation.worktree import WorktreeManager


class ExitWorktreeTool(ToolDef):
    metadata = ToolMetadata(name="ExitWorktreeTool")
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "auto_cleanup_when_clean": {"type": "boolean"},
        },
        "required": [],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, manager: WorktreeManager) -> None:
        self.manager = manager

    def validate_input(self, args: Mapping[str, Any]) -> None:
        action = str(args.get("action", "auto"))
        if action not in {"auto", "keep", "remove"}:
            raise ValueError("action must be one of: auto, keep, remove")

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = can_use_tool, parent_message
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "exiting"})
        return self.manager.exit(
            action=str(args.get("action", "auto")),
            context=context,
            auto_cleanup_when_clean=bool(args.get("auto_cleanup_when_clean", True)),
        )
