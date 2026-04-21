from __future__ import annotations

from pathlib import Path
from typing import Any

from .ast_engine import ASTEditEngine


class StructuredEditEngine:
    def __init__(self, *, ast_engine: ASTEditEngine | None = None) -> None:
        self.ast_engine = ast_engine or ASTEditEngine()

    def apply(self, *, file_path: Path, edit: dict[str, Any]) -> dict[str, Any]:
        path = file_path.expanduser().resolve()
        content = path.read_text(encoding="utf-8")
        result = self.ast_engine.apply_edits(content=content, edits=[dict(edit)], file_path=str(path))
        updated_content = str(result["content"])
        replacements = int(result["replacements"])

        if updated_content == content:
            return {
                "path": str(path),
                "updated": False,
                "replacements": 0,
                "content": content,
            }

        try:
            path.write_text(updated_content, encoding="utf-8")
        except Exception:
            path.write_text(content, encoding="utf-8")
            raise

        return {
            "path": str(path),
            "updated": True,
            "replacements": replacements,
            "content": updated_content,
        }
