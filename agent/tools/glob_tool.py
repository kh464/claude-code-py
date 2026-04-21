from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata


class GlobTool(ToolDef):
    metadata = ToolMetadata(name="GlobTool")
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "pattern": {"type": "string"},
        },
        "required": ["path", "pattern"],
    }
    output_schema = {"type": "object"}

    def is_read_only(self) -> bool:
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
        root = Path(str(args["path"])).expanduser().resolve()
        pattern = str(args["pattern"])
        paths = sorted(str(path.resolve()) for path in root.rglob(pattern) if path.is_file())
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "glob", "count": len(paths)})
        return {"paths": paths, "count": len(paths)}
