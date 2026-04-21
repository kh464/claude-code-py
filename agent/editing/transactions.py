from __future__ import annotations

from pathlib import Path
from typing import Any

from .ast_engine import ASTEditEngine


class EditTransaction:
    def __init__(self, file_path: str | Path, *, ast_engine: ASTEditEngine | None = None) -> None:
        self.file_path = Path(file_path).expanduser().resolve()
        self.ast_engine = ast_engine or ASTEditEngine()
        self._original_content: str | None = None

    def apply(self, *, edits: list[dict[str, Any]]) -> dict[str, Any]:
        self._original_content = self.file_path.read_text(encoding="utf-8")
        try:
            result = self.ast_engine.apply_edits(
                content=self._original_content,
                edits=edits,
                file_path=str(self.file_path),
            )
            if result["updated"]:
                self.file_path.write_text(str(result["content"]), encoding="utf-8")
            return {
                "path": str(self.file_path),
                "updated": bool(result["updated"]),
                "replacements": int(result["replacements"]),
                "content": str(result["content"]),
            }
        except Exception:
            self.rollback()
            raise

    def rollback(self) -> None:
        if self._original_content is None:
            return
        self.file_path.write_text(self._original_content, encoding="utf-8")
