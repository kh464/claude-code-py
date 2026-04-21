from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata


class EnterPlanModeTool(ToolDef):
    metadata = ToolMetadata(name="EnterPlanModeTool")
    input_schema = {
        "type": "object",
        "properties": {
            "reason": {"type": "string"},
        },
        "required": [],
    }
    output_schema = {"type": "object"}

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = can_use_tool, parent_message
        metadata = context.metadata if context is not None else {}
        metadata["plan_mode"] = True
        if args.get("reason"):
            metadata["plan_mode_reason"] = str(args.get("reason"))
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "enabled"})
        return {
            "plan_mode": True,
            "reason": str(metadata.get("plan_mode_reason", "")),
        }


class ExitPlanModeV2Tool(ToolDef):
    metadata = ToolMetadata(name="ExitPlanModeV2Tool")
    input_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
        },
        "required": [],
    }
    output_schema = {"type": "object"}

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = can_use_tool, parent_message
        metadata = context.metadata if context is not None else {}
        metadata["plan_mode"] = False
        summary = str(args.get("summary", "")).strip()
        if summary:
            metadata["plan_mode_summary"] = summary
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "disabled"})
        return {"plan_mode": False, "summary": summary}
