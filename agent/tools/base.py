from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from agent.contracts import ToolContext, ToolDef, ToolMetadata


@dataclass(slots=True)
class ToolFlags:
    concurrency_safe: bool = True
    read_only: bool = False
    destructive: bool = False


class StaticTool(ToolDef):
    input_schema = {"type": "object", "properties": {}, "required": []}
    output_schema = {"type": "object"}

    def __init__(
        self,
        metadata: ToolMetadata,
        *,
        flags: ToolFlags | None = None,
        handler: Callable[[Mapping[str, Any]], Any] | None = None,
    ) -> None:
        self.metadata = metadata
        self.flags = flags or ToolFlags()
        self._handler = handler or (lambda args: {"tool": metadata.name, "arguments": dict(args)})

    def is_concurrency_safe(self) -> bool:
        return self.flags.concurrency_safe

    def is_read_only(self) -> bool:
        return self.flags.read_only

    def is_destructive(self) -> bool:
        return self.flags.destructive

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "started"})
        _ = context, can_use_tool, parent_message
        return self._handler(args)
