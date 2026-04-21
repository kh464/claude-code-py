from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.runtime import ToolRuntime
from agent.tools.registry import ToolRegistry
from agent.errors import ToolExecutionError


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"file-tools-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_file_write_and_read_roundtrip() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        file_path = temp_root / "sample.txt"

        await runtime.execute_tool_use(
            "FileWriteTool",
            {"path": str(file_path), "content": "line1\nline2\nline3\n"},
        )
        read_result = await runtime.execute_tool_use(
            "FileReadTool",
            {"path": str(file_path), "offset": 1, "limit": 2},
        )

        payload = read_result["raw_result"]
        assert payload["path"] == str(file_path.resolve())
        assert payload["content"] == "line2\nline3\n"
        assert payload["line_count"] == 2
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_file_edit_requires_prior_read() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        file_path = temp_root / "edit.txt"
        file_path.write_text("hello world\n", encoding="utf-8")

        with pytest.raises(ToolExecutionError, match="Must read file before editing"):
            await runtime.execute_tool_use(
                "FileEditTool",
                {"path": str(file_path), "old_string": "world", "new_string": "python"},
            )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_file_edit_after_read_updates_file() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        file_path = temp_root / "edit-pass.txt"

        await runtime.execute_tool_use(
            "FileWriteTool",
            {"path": str(file_path), "content": "alpha\nbeta\n"},
        )
        await runtime.execute_tool_use("FileReadTool", {"path": str(file_path)})
        edit_result = await runtime.execute_tool_use(
            "FileEditTool",
            {"path": str(file_path), "old_string": "beta", "new_string": "gamma"},
        )

        payload = edit_result["raw_result"]
        assert payload["updated"] is True
        assert payload["replacements"] == 1
        assert file_path.read_text(encoding="utf-8") == "alpha\ngamma\n"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_file_edit_rejects_stale_read() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        file_path = temp_root / "stale.txt"
        file_path.write_text("before\n", encoding="utf-8")

        await runtime.execute_tool_use("FileReadTool", {"path": str(file_path)})
        file_path.write_text("changed externally\n", encoding="utf-8")

        with pytest.raises(ToolExecutionError, match="File changed since last read"):
            await runtime.execute_tool_use(
                "FileEditTool",
                {"path": str(file_path), "old_string": "changed", "new_string": "updated"},
            )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_glob_and_grep_scan_files() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        (temp_root / "src").mkdir(parents=True, exist_ok=True)
        (temp_root / "src" / "main.py").write_text("print('hello')\n# TODO: fix\n", encoding="utf-8")
        (temp_root / "src" / "util.py").write_text("def util():\n    return 1\n", encoding="utf-8")
        (temp_root / "README.md").write_text("# notes\n", encoding="utf-8")

        glob_result = await runtime.execute_tool_use(
            "GlobTool",
            {"path": str(temp_root), "pattern": "*.py"},
        )
        grep_result = await runtime.execute_tool_use(
            "GrepTool",
            {"path": str(temp_root), "pattern": "TODO"},
        )

        glob_paths = glob_result["raw_result"]["paths"]
        matches = grep_result["raw_result"]["matches"]
        assert len(glob_paths) == 2
        assert any(path.endswith("main.py") for path in glob_paths)
        assert matches[0]["line_number"] == 2
        assert "TODO" in matches[0]["line"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
