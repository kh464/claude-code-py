from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata


class AskUserQuestionTool(ToolDef):
    metadata = ToolMetadata(name="AskUserQuestionTool")
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "header": {"type": "string"},
            "options": {"type": "array"},
        },
        "required": ["question"],
    }
    output_schema = {"type": "object"}

    def is_read_only(self) -> bool:
        return True

    def validate_input(self, args: Mapping[str, Any]) -> None:
        question = str(args.get("question", "")).strip()
        if not question:
            raise ValueError("question must not be empty")
        options = args.get("options")
        if options is not None and not isinstance(options, list):
            raise ValueError("options must be an array when provided")

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message
        question = str(args.get("question", "")).strip()
        header = str(args.get("header", "")).strip()
        raw_options = args.get("options", [])
        options = [str(item).strip() for item in raw_options if str(item).strip()] if isinstance(raw_options, list) else []
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "awaiting_user_input"})
        return {
            "status": "needs_user_input",
            "question": question,
            "header": header,
            "options": options,
        }
