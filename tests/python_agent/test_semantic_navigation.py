from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.semantic.index import SemanticIndex
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"semantic-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _create_sample_project(root: Path) -> None:
    (root / "service.py").write_text(
        "class UserService:\n"
        "    def run(self):\n"
        "        return 'ok'\n"
        "\n"
        "svc = UserService()\n",
        encoding="utf-8",
    )
    (root / "handler.py").write_text(
        "from service import UserService\n"
        "\n"
        "def use_service():\n"
        "    item = UserService()\n"
        "    return item.run()\n",
        encoding="utf-8",
    )


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


def test_semantic_index_finds_symbol_definitions() -> None:
    temp_root = _create_temp_dir()
    try:
        _create_sample_project(temp_root)
        index = SemanticIndex(root=temp_root)
        definitions = index.find_symbol("UserService")
        assert definitions
        assert definitions[0]["kind"] == "class"
        assert definitions[0]["symbol"] == "UserService"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_lsp_tool_resolves_definitions_and_references() -> None:
    temp_root = _create_temp_dir()
    try:
        _create_sample_project(temp_root)
        runtime = _build_runtime()
        context = ToolContext(metadata={"current_cwd": str(temp_root)})

        symbol_result = await runtime.execute_tool_use(
            "LSPTool",
            {"operation": "find_symbol", "symbol": "UserService"},
            context=context,
        )
        reference_result = await runtime.execute_tool_use(
            "LSPTool",
            {"operation": "find_references", "symbol": "UserService"},
            context=context,
        )

        definitions = symbol_result["raw_result"]["definitions"]
        references = reference_result["raw_result"]["references"]
        assert definitions
        assert any(item["path"].endswith("service.py") for item in definitions)
        assert len(references) >= 2
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
