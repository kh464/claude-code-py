from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata


class GrepTool(ToolDef):
    metadata = ToolMetadata(name="GrepTool")
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "pattern": {"type": "string"},
            "file_pattern": {"type": "string"},
            "case_sensitive": {"type": "boolean"},
            "max_results": {"type": "integer"},
        },
        "required": ["path", "pattern"],
    }
    output_schema = {"type": "object"}

    def is_read_only(self) -> bool:
        return True

    def validate_input(self, args: Mapping[str, Any]) -> None:
        max_results = int(args.get("max_results", 200))
        if max_results <= 0:
            raise ValueError("max_results must be > 0")

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
        file_pattern = str(args.get("file_pattern", "*"))
        case_sensitive = bool(args.get("case_sensitive", True))
        max_results = int(args.get("max_results", 200))

        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
        matches: list[dict[str, Any]] = []
        truncated = False

        for path in root.rglob(file_pattern):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(
                        {
                            "path": str(path.resolve()),
                            "line_number": line_number,
                            "line": line,
                        }
                    )
                    if len(matches) >= max_results:
                        truncated = True
                        break
            if truncated:
                break

        on_progress(
            {
                "event": "tool_progress",
                "tool": self.metadata.name,
                "stage": "grep",
                "count": len(matches),
                "truncated": truncated,
            }
        )
        return {"matches": matches, "count": len(matches), "truncated": truncated}
