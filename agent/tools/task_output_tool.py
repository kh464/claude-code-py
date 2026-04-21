from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.subagents.task_manager import TaskManager


class TaskOutputTool(ToolDef):
    metadata = ToolMetadata(name="TaskOutputTool")
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "tail_lines": {"type": "integer"},
        },
        "required": [],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, task_manager: TaskManager) -> None:
        self.task_manager = task_manager

    def is_read_only(self) -> bool:
        return True

    def validate_input(self, args: Mapping[str, Any]) -> None:
        if not args.get("task_id") and not args.get("agent_id"):
            raise ValueError("Either task_id or agent_id is required")
        if "tail_lines" in args and int(args["tail_lines"]) < 0:
            raise ValueError("tail_lines must be >= 0")

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message, on_progress
        return await self.task_manager.output(
            task_id=str(args["task_id"]) if args.get("task_id") else None,
            agent_id=str(args["agent_id"]) if args.get("agent_id") else None,
            tail_lines=int(args["tail_lines"]) if args.get("tail_lines") is not None else None,
            context=context,
        )
