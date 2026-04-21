from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata

from .file_safety import FileReadStateCache


class FileReadTool(ToolDef):
    metadata = ToolMetadata(name="FileReadTool")
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer"},
            "limit": {"type": "integer"},
        },
        "required": ["path"],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, read_cache: FileReadStateCache) -> None:
        self._read_cache = read_cache

    def is_read_only(self) -> bool:
        return True

    def validate_input(self, args: Mapping[str, Any]) -> None:
        if int(args.get("offset", 0)) < 0:
            raise ValueError("offset must be >= 0")
        limit = args.get("limit")
        if limit is not None and int(limit) <= 0:
            raise ValueError("limit must be > 0")

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
        content = path.read_text(encoding="utf-8")
        self._read_cache.record_read(str(path), content)

        lines = content.splitlines(keepends=True)
        offset = int(args.get("offset", 0))
        limit_value = args.get("limit")
        limit = int(limit_value) if limit_value is not None else None
        selected_lines = lines[offset : offset + limit] if limit is not None else lines[offset:]
        selected_content = "".join(selected_lines)

        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "read", "path": str(path)})
        return {
            "path": str(path),
            "content": selected_content,
            "line_offset": offset,
            "line_count": len(selected_lines),
            "total_lines": len(lines),
        }
