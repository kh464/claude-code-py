from __future__ import annotations

import ast
from typing import Any


class ASTEditEngine:
    def _apply_single(self, *, content: str, edit: dict[str, Any]) -> tuple[str, int]:
        old_string = str(edit["old_string"])
        new_string = str(edit["new_string"])
        replace_all = bool(edit.get("replace_all", False))
        start_offset = edit.get("start_offset")

        if start_offset is not None:
            offset = int(start_offset)
            end = offset + len(old_string)
            if offset < 0 or end > len(content) or content[offset:end] != old_string:
                raise ValueError("Edit range drifted from expected content")
            return content[:offset] + new_string + content[end:], 1

        occurrences = content.count(old_string)
        if occurrences == 0:
            raise ValueError("old_string not found in current content")
        if occurrences > 1 and not replace_all:
            raise ValueError("old_string is not unique; use replace_all or start_offset")
        if replace_all:
            return content.replace(old_string, new_string), occurrences
        return content.replace(old_string, new_string, 1), 1

    def apply_edits(self, *, content: str, edits: list[dict[str, Any]], file_path: str | None = None) -> dict[str, Any]:
        updated = content
        replacements = 0
        for edit in edits:
            updated, count = self._apply_single(content=updated, edit=edit)
            replacements += count

        if file_path and str(file_path).endswith(".py"):
            try:
                ast.parse(updated)
            except SyntaxError as exc:
                raise ValueError(f"AST validation failed: {exc.msg}") from exc

        return {
            "content": updated,
            "replacements": replacements,
            "updated": updated != content,
        }
