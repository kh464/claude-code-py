from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata


class FileWriteTool(ToolDef):
    metadata = ToolMetadata(name="FileWriteTool")
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }
    output_schema = {"type": "object"}

    def is_concurrency_safe(self) -> bool:
        return False

    def is_destructive(self) -> bool:
        return True

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message
        path = Path(str(args["path"])).expanduser().resolve()
        content = str(args["content"])
        existed_before = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "write", "path": str(path)})
        return {
            "path": str(path),
            "updated": existed_before,
            "created": not existed_before,
            "bytes_written": len(content.encode("utf-8")),
        }
