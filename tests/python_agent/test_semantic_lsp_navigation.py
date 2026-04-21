from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from agent.semantic.index import SemanticIndex
from agent.semantic.lsp_client import LSPClient
from agent.tools.lsp_tool import LSPTool
from agent.contracts import ToolContext
import pytest


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"semantic-lsp-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _create_sample_project(root: Path) -> None:
    (root / "service.py").write_text(
        "class UserService:\n"
        "    def run(self):\n"
        "        return 'ok'\n",
        encoding="utf-8",
    )
    (root / "handler.py").write_text(
        "from service import UserService\n"
        "\n"
        "def invoke():\n"
        "    return UserService().run()\n",
        encoding="utf-8",
    )


class FakeLSPClient(LSPClient):
    def __init__(self) -> None:
        self.definition_calls: list[str] = []
        self.reference_calls: list[str] = []

    def find_definitions(self, *, symbol: str, root: Path) -> list[dict]:
        _ = root
        self.definition_calls.append(symbol)
        return [
            {
                "symbol": symbol,
                "kind": "class",
                "path": str(root / "service.py"),
                "line_number": 1,
                "line": "class UserService:",
                "source": "lsp",
            }
        ]

    def find_references(self, *, symbol: str, root: Path) -> list[dict]:
        self.reference_calls.append(symbol)
        return [
            {
                "symbol": symbol,
                "path": str(root / "service.py"),
                "line_number": 1,
                "line": "class UserService:",
                "source": "lsp",
            },
            {
                "symbol": symbol,
                "path": str(root / "handler.py"),
                "line_number": 1,
                "line": "from service import UserService",
                "source": "lsp",
            },
        ]


class ErrorLSPClient(LSPClient):
    def find_definitions(self, *, symbol: str, root: Path) -> list[dict]:
        _ = symbol, root
        raise RuntimeError("lsp unavailable")

    def find_references(self, *, symbol: str, root: Path) -> list[dict]:
        _ = symbol, root
        raise RuntimeError("lsp unavailable")


class RefactorLSPClient(FakeLSPClient):
    def list_code_actions(
        self,
        *,
        root: Path,
        path: Path,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        only: list[str] | None = None,
    ) -> list[dict[str, object]]:
        _ = root, start_line, start_character, end_line, end_character, only
        uri = path.resolve().as_uri()
        return [
            {
                "title": "Extract helper",
                "kind": "refactor.extract",
                "edit": {
                    "changes": {
                        uri: [
                            {
                                "range": {
                                    "start": {"line": 2, "character": 8},
                                    "end": {"line": 2, "character": 19},
                                },
                                "newText": "return helper()",
                            },
                            {
                                "range": {
                                    "start": {"line": 3, "character": 0},
                                    "end": {"line": 3, "character": 0},
                                },
                                "newText": "\n\ndef helper():\n    return 'ok'\n",
                            },
                        ]
                    }
                },
            }
        ]


def test_semantic_index_uses_lsp_client_results() -> None:
    temp_root = _create_temp_dir()
    try:
        _create_sample_project(temp_root)
        client = FakeLSPClient()
        index = SemanticIndex(root=temp_root, lsp_client=client)

        definitions = index.find_symbol("UserService")
        references = index.find_references("UserService")

        assert client.definition_calls == ["UserService"]
        assert client.reference_calls == ["UserService"]
        assert definitions and definitions[0]["source"] == "lsp"
        assert len(references) >= 2
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_semantic_index_falls_back_when_lsp_errors() -> None:
    temp_root = _create_temp_dir()
    try:
        _create_sample_project(temp_root)
        index = SemanticIndex(root=temp_root, lsp_client=ErrorLSPClient())

        definitions = index.find_symbol("UserService")
        references = index.find_references("UserService")

        assert definitions
        assert any(item["path"].endswith("service.py") for item in definitions)
        assert any(item["path"].endswith("handler.py") for item in references)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_lsp_tool_strict_mode_raises_when_lsp_fails() -> None:
    temp_root = _create_temp_dir()
    try:
        _create_sample_project(temp_root)
        tool = LSPTool()
        with pytest.raises(RuntimeError):
            await tool.call(
                {"operation": "find_symbol", "symbol": "UserService"},
                ToolContext(
                    metadata={
                        "current_cwd": str(temp_root),
                        "lsp_client": ErrorLSPClient(),
                        "lsp_strict": True,
                    }
                ),
                None,
                None,
                lambda _event: None,
            )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_lsp_tool_can_rename_symbol_with_scan_fallback() -> None:
    temp_root = _create_temp_dir()
    try:
        _create_sample_project(temp_root)
        tool = LSPTool()
        result = await tool.call(
            {
                "operation": "rename_symbol",
                "symbol": "UserService",
                "new_name": "AccountService",
                "apply": True,
            },
            ToolContext(metadata={"current_cwd": str(temp_root)}),
            None,
            None,
            lambda _event: None,
        )
        assert result["operation"] == "rename_symbol"
        assert result["backend"] == "scan"
        assert result["applied"] is True
        assert result["files_changed"] >= 2
        service_text = (temp_root / "service.py").read_text(encoding="utf-8")
        handler_text = (temp_root / "handler.py").read_text(encoding="utf-8")
        assert "AccountService" in service_text
        assert "AccountService" in handler_text
        assert "UserService" not in service_text
        assert "UserService" not in handler_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_lsp_tool_lists_and_applies_refactor_actions() -> None:
    temp_root = _create_temp_dir()
    try:
        _create_sample_project(temp_root)
        tool = LSPTool()
        context = ToolContext(metadata={"current_cwd": str(temp_root), "lsp_client": RefactorLSPClient(), "lsp_strict": True})

        listed = await tool.call(
            {
                "operation": "list_refactors",
                "path": str(temp_root / "service.py"),
                "start_line": 2,
                "start_character": 4,
                "end_line": 2,
                "end_character": 19,
                "kinds": ["refactor.extract"],
            },
            context,
            None,
            None,
            lambda _event: None,
        )
        assert listed["count"] >= 1
        assert listed["actions"][0]["kind"] == "refactor.extract"

        applied = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(temp_root / "service.py"),
                "start_line": 2,
                "start_character": 4,
                "end_line": 2,
                "end_character": 19,
                "action_index": 0,
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )
        assert applied["backend"] == "lsp"
        assert applied["selected"]["title"] == "Extract helper"
        assert applied["files_changed"] >= 1

        service_text = (temp_root / "service.py").read_text(encoding="utf-8")
        assert "helper()" in service_text
        assert "def helper()" in service_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_lsp_tool_reports_capabilities_and_normalized_refactor_kinds() -> None:
    temp_root = _create_temp_dir()
    try:
        _create_sample_project(temp_root)
        tool = LSPTool()
        context = ToolContext(metadata={"current_cwd": str(temp_root), "lsp_client": RefactorLSPClient(), "lsp_strict": True})

        result = await tool.call(
            {
                "operation": "capabilities",
                "path": str(temp_root / "service.py"),
                "start_line": 2,
                "start_character": 4,
                "end_line": 2,
                "end_character": 19,
            },
            context,
            None,
            None,
            lambda _event: None,
        )
        assert result["operation"] == "capabilities"
        assert "rename_symbol" in result["supported_operations"]
        assert "list_refactors" in result["supported_operations"]
        assert "apply_refactor" in result["supported_operations"]
        assert "extract" in result["supported_refactor_kinds"]
        assert result["strict_lsp_effective"] is True
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
