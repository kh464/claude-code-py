from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.editing.transactions import EditTransaction


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"ast-edit-tx-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_ast_edit_transaction_rolls_back_on_conflict() -> None:
    temp_root = _create_temp_dir()
    try:
        file_path = temp_root / "sample.py"
        original = "def a():\n    return 1\n"
        file_path.write_text(original, encoding="utf-8")

        tx = EditTransaction(file_path)
        with pytest.raises(ValueError):
            tx.apply(
                edits=[
                    {"old_string": "return 1", "new_string": "return 2", "start_offset": 13},
                    {"old_string": "return 9", "new_string": "return 3", "start_offset": 13},
                ]
            )

        assert file_path.read_text(encoding="utf-8") == original
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_ast_edit_transaction_applies_multiple_edits_atomically() -> None:
    temp_root = _create_temp_dir()
    try:
        file_path = temp_root / "sample.py"
        file_path.write_text("def a():\n    return 1\n", encoding="utf-8")

        tx = EditTransaction(file_path)
        result = tx.apply(
            edits=[
                {"old_string": "a", "new_string": "renamed", "start_offset": 4},
                {"old_string": "return 1", "new_string": "return 2"},
            ]
        )

        assert result["updated"] is True
        assert result["replacements"] == 2
        content = file_path.read_text(encoding="utf-8")
        assert "def renamed()" in content
        assert "return 2" in content
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
