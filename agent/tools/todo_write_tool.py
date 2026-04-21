from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata


_ALLOWED_STATUS = {"pending", "in_progress", "completed"}


class TodoWriteTool(ToolDef):
    metadata = ToolMetadata(name="TodoWriteTool")
    input_schema = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
            }
        },
        "required": ["todos"],
    }
    output_schema = {"type": "object"}

    def is_concurrency_safe(self) -> bool:
        return False

    def is_destructive(self) -> bool:
        return True

    def validate_input(self, args: Mapping[str, Any]) -> None:
        todos = args.get("todos")
        if not isinstance(todos, list) or not todos:
            raise ValueError("todos must be a non-empty array")
        for index, item in enumerate(todos, start=1):
            if not isinstance(item, Mapping):
                raise ValueError(f"todo at index {index} must be an object")
            content = str(item.get("content", "")).strip()
            if not content:
                raise ValueError(f"todo at index {index} must include non-empty content")
            status = str(item.get("status", "pending")).strip().lower()
            if status not in _ALLOWED_STATUS:
                raise ValueError(f"todo at index {index} has unsupported status: {status}")

    @staticmethod
    def _resolve_store_path(context: ToolContext | None) -> Path:
        metadata = context.metadata if context is not None else {}
        if metadata.get("todo_file"):
            return Path(str(metadata["todo_file"])).expanduser().resolve()
        session = (context.session_id if context is not None else None) or "default"
        return (Path.cwd() / ".claude" / "todos" / f"{session}.json").resolve()

    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = can_use_tool, parent_message
        todos_raw = args.get("todos", [])
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(todos_raw, start=1):
            todo = dict(item) if isinstance(item, Mapping) else {}
            normalized.append(
                {
                    "id": str(todo.get("id") or f"todo-{index}"),
                    "content": str(todo.get("content", "")).strip(),
                    "status": str(todo.get("status", "pending")).strip().lower(),
                }
            )

        store_path = self._resolve_store_path(context)
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text(json.dumps({"todos": normalized}, ensure_ascii=False, indent=2), encoding="utf-8")
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "written", "count": len(normalized)})
        return {
            "path": str(store_path),
            "total": len(normalized),
            "pending": sum(1 for item in normalized if item["status"] == "pending"),
            "in_progress": sum(1 for item in normalized if item["status"] == "in_progress"),
            "completed": sum(1 for item in normalized if item["status"] == "completed"),
        }
