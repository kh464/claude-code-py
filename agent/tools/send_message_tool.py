from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.subagents.task_manager import TaskManager


class SendMessageTool(ToolDef):
    metadata = ToolMetadata(name="SendMessageTool")
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "agent_id": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["message"],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, task_manager: TaskManager) -> None:
        self.task_manager = task_manager

    def validate_input(self, args: Mapping[str, Any]) -> None:
        if not args.get("task_id") and not args.get("agent_id"):
            raise ValueError("Either task_id or agent_id is required")
        message = str(args.get("message", "")).strip()
        if not message:
            raise ValueError("message must not be empty")

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "sending"})
        return await self.task_manager.send_message(
            task_id=str(args["task_id"]) if args.get("task_id") else None,
            agent_id=str(args["agent_id"]) if args.get("agent_id") else None,
            message=str(args["message"]),
            context=context,
        )
