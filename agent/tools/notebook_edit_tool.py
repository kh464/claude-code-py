from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata


class NotebookEditTool(ToolDef):
    metadata = ToolMetadata(name="NotebookEditTool")
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "cell_index": {"type": "integer"},
            "new_source": {"type": "string"},
            "mode": {"type": "string"},
        },
        "required": ["path", "cell_index", "new_source"],
    }
    output_schema = {"type": "object"}

    def is_concurrency_safe(self) -> bool:
        return False

    def is_destructive(self) -> bool:
        return True

    def validate_input(self, args: Mapping[str, Any]) -> None:
        mode = str(args.get("mode", "replace"))
        if mode not in {"replace", "append"}:
            raise ValueError("mode must be one of: replace, append")

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message
        path = Path(str(args["path"])).expanduser().resolve()
        cell_index = int(args["cell_index"])
        new_source = str(args["new_source"])
        mode = str(args.get("mode", "replace"))

        notebook = json.loads(path.read_text(encoding="utf-8"))
        cells = notebook.get("cells")
        if not isinstance(cells, list):
            raise ValueError("Notebook JSON missing cells list")
        if cell_index < 0 or cell_index >= len(cells):
            raise ValueError("cell_index out of range")

        source_lines = new_source.splitlines(keepends=True)
        cell = cells[cell_index]
        existing_source = cell.get("source", [])
        if isinstance(existing_source, str):
            existing_lines = existing_source.splitlines(keepends=True)
        else:
            existing_lines = [str(line) for line in existing_source]

        if mode == "append":
            cell["source"] = existing_lines + source_lines
        else:
            cell["source"] = source_lines

        path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "edited", "path": str(path)})
        return {
            "path": str(path),
            "cell_index": cell_index,
            "mode": mode,
            "updated": True,
        }
