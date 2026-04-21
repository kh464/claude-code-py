from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.editing.transactions import EditTransaction

from .file_safety import FileReadStateCache


class FileEditTool(ToolDef):
    metadata = ToolMetadata(name="FileEditTool")
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"},
            "start_offset": {"type": "integer"},
        },
        "required": ["path", "old_string", "new_string"],
    }
    output_schema = {"type": "object"}

    def __init__(self, *, read_cache: FileReadStateCache) -> None:
        self._read_cache = read_cache

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
        old_string = str(args["old_string"])
        new_string = str(args["new_string"])
        replace_all = bool(args.get("replace_all", False))
        start_offset = args.get("start_offset")

        content = path.read_text(encoding="utf-8")
        self._read_cache.ensure_can_edit(
            str(path),
            content,
            old_string,
            replace_all=replace_all or start_offset is not None,
        )

        edit = {
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": replace_all,
        }
        if start_offset is not None:
            edit["start_offset"] = int(start_offset)
        transaction = EditTransaction(path)
        result = transaction.apply(edits=[edit])
        self._read_cache.record_read(str(path), result["content"])
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "edit", "path": str(path)})
        return {
            "path": str(path),
            "updated": bool(result["updated"]),
            "replacements": int(result["replacements"]),
        }
