from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.editing.engine import StructuredEditEngine
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"structured-edit-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


def test_structured_edit_rejects_drifted_range() -> None:
    temp_root = _create_temp_dir()
    try:
        file_path = temp_root / "sample.txt"
        file_path.write_text("hello world\n", encoding="utf-8")
        engine = StructuredEditEngine()

        with pytest.raises(ValueError, match="range drifted"):
            engine.apply(
                file_path=file_path,
                edit={
                    "old_string": "world",
                    "new_string": "python",
                    "start_offset": 0,
                },
            )
        assert file_path.read_text(encoding="utf-8") == "hello world\n"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_structured_edit_applies_with_matching_range() -> None:
    temp_root = _create_temp_dir()
    try:
        file_path = temp_root / "sample.txt"
        file_path.write_text("hello world\n", encoding="utf-8")
        engine = StructuredEditEngine()

        result = engine.apply(
            file_path=file_path,
            edit={
                "old_string": "world",
                "new_string": "python",
                "start_offset": 6,
            },
        )
        assert result["updated"] is True
        assert result["replacements"] == 1
        assert file_path.read_text(encoding="utf-8") == "hello python\n"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_file_edit_tool_supports_offset_targeting() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        file_path = temp_root / "repeat.txt"

        await runtime.execute_tool_use(
            "FileWriteTool",
            {"path": str(file_path), "content": "beta beta\n"},
        )
        await runtime.execute_tool_use("FileReadTool", {"path": str(file_path)})
        result = await runtime.execute_tool_use(
            "FileEditTool",
            {
                "path": str(file_path),
                "old_string": "beta",
                "new_string": "gamma",
                "start_offset": 5,
            },
        )

        payload = result["raw_result"]
        assert payload["updated"] is True
        assert payload["replacements"] == 1
        assert file_path.read_text(encoding="utf-8") == "beta gamma\n"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
