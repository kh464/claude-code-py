from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.semantic.lsp_client import LSPClient
from agent.tools.lsp_tool import LSPTool


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"semantic-hybrid-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class NoActionLSPClient(LSPClient):
    def find_definitions(self, *, symbol: str, root: Path) -> list[dict]:
        _ = symbol, root
        return []

    def find_references(self, *, symbol: str, root: Path) -> list[dict]:
        _ = symbol, root
        return []

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
        _ = root, path, start_line, start_character, end_line, end_character, only
        return []


@pytest.mark.asyncio
async def test_extract_refactor_falls_back_when_lsp_action_missing() -> None:
    temp_root = _create_temp_dir()
    try:
        target = temp_root / "service.py"
        target.write_text(
            "def run():\n"
            "    name = ' Ada '\n"
            "    return name.strip().lower()\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 2,
                "end_character": 29,
                "kinds": ["refactor.extract"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "extract"
        assert result["files_changed"] == 1

        updated = target.read_text(encoding="utf-8")
        assert "def _extracted_run_" in updated
        assert "return _extracted_run_" in updated
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_returns_structured_failure_when_no_lsp_action() -> None:
    temp_root = _create_temp_dir()
    try:
        target = temp_root / "service.py"
        target.write_text(
            "def run():\n"
            "    value = 1\n"
            "    return value\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(target),
                "start_line": 1,
                "start_character": 4,
                "end_line": 1,
                "end_character": 13,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["applied"] is False
        assert result["selected"] is None
        assert result["files_changed"] == 0
        assert result.get("fallback_error") == "move_target_path_required"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_falls_back_when_lsp_action_missing_and_moves_function_cross_file() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "def helper(value):\n"
            "    return value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return helper(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 1,
                "start_character": 0,
                "end_line": 2,
                "end_character": 33,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "def helper(value):" not in source_text
        assert "from utils import helper" in source_text
        assert "return helper(value)" in source_text
        assert "def helper(value):" in target_text
        assert "value.strip().lower()" in target_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_falls_back_when_lsp_action_missing_and_moves_class_cross_file() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "models.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return UserService().normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "class Existing:\n"
            "    pass\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 1,
                "start_character": 0,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "class UserService:" not in source_text
        assert "from models import UserService" in source_text
        assert "return UserService().normalize(value)" in source_text
        assert "class UserService:" in target_text
        assert "def normalize(self, value):" in target_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_preserves_decorators_when_moving_function() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "def traced(fn):\n"
            "    return fn\n"
            "\n"
            "@traced\n"
            "def helper(value):\n"
            "    return value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return helper(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 4,
                "start_character": 0,
                "end_line": 6,
                "end_character": 33,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "@traced" not in source_text
        assert "def helper(value):" not in source_text
        assert "from utils import helper" in source_text
        assert "@traced" in target_text
        assert "def helper(value):" in target_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_staticmethod_to_top_level_and_rewrites_class_qualified_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    @staticmethod\n"
            "    def normalize(value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return UserService.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 4,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "@staticmethod" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "return normalize(value)" in source_text
        assert "UserService.normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_classmethod_to_top_level_and_rewrites_class_qualified_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    @classmethod\n"
            "    def normalize(cls, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return UserService.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 4,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "@classmethod" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "return normalize(value)" in source_text
        assert "UserService.normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_returns_structured_failure_for_classmethod_using_cls_state() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    prefix = 'svc-'\n"
            "\n"
            "    @classmethod\n"
            "    def normalize(cls, value):\n"
            "        return cls.prefix + value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return UserService.normalize(value)\n",
            encoding="utf-8",
        )
        original_source = source.read_text(encoding="utf-8")
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        original_target = target.read_text(encoding="utf-8")
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 4,
                "start_character": 4,
                "end_line": 6,
                "end_character": 50,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["applied"] is False
        assert result["selected"] is None
        assert result["files_changed"] == 0
        assert result.get("fallback_error") == "move_classmethod_uses_cls_state"
        assert source.read_text(encoding="utf-8") == original_source
        assert target.read_text(encoding="utf-8") == original_target
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_instance_method_to_top_level_and_rewrites_ctor_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return UserService().normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "def normalize(self, value):" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "return normalize(value)" in source_text
        assert "UserService().normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_returns_structured_failure_for_instance_method_using_self_state() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return self.prefix + value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return UserService().normalize(value)\n",
            encoding="utf-8",
        )
        original_source = source.read_text(encoding="utf-8")
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        original_target = target.read_text(encoding="utf-8")
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 50,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["applied"] is False
        assert result["selected"] is None
        assert result["files_changed"] == 0
        assert result.get("fallback_error") == "move_instance_method_uses_instance_state"
        assert source.read_text(encoding="utf-8") == original_source
        assert target.read_text(encoding="utf-8") == original_target
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_instance_method_and_rewrites_known_instance_variable_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    service = UserService()\n"
            "    return service.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "def normalize(self, value):" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "service = UserService()" in source_text
        assert "return normalize(value)" in source_text
        assert "service.normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_returns_structured_failure_for_instance_method_with_unresolved_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def run(value, service):\n"
            "    return service.normalize(value)\n",
            encoding="utf-8",
        )
        original_source = source.read_text(encoding="utf-8")
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        original_target = target.read_text(encoding="utf-8")
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["applied"] is False
        assert result["selected"] is None
        assert result["files_changed"] == 0
        assert result.get("fallback_error") == "move_instance_method_unresolved_callsites"
        assert source.read_text(encoding="utf-8") == original_source
        assert target.read_text(encoding="utf-8") == original_target
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_instance_method_and_rewrites_constructor_args_alias_chain_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def run(value, config):\n"
            "    svc = UserService(config)\n"
            "    alias = svc\n"
            "    return alias.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "def normalize(self, value):" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "svc = UserService(config)" in source_text
        assert "alias = svc" in source_text
        assert "return normalize(value)" in source_text
        assert "alias.normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_instance_method_and_rewrites_local_factory_alias_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def build_service(config):\n"
            "    return UserService(config)\n"
            "\n"
            "def run(value, config):\n"
            "    svc = build_service(config)\n"
            "    return svc.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "def normalize(self, value):" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "svc = build_service(config)" in source_text
        assert "return normalize(value)" in source_text
        assert "svc.normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_returns_structured_failure_for_instance_method_with_external_factory_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "from helpers import build_service\n"
            "\n"
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def run(value, config):\n"
            "    svc = build_service(config)\n"
            "    return svc.normalize(value)\n",
            encoding="utf-8",
        )
        original_source = source.read_text(encoding="utf-8")
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        original_target = target.read_text(encoding="utf-8")
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 4,
                "start_character": 4,
                "end_line": 5,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["applied"] is False
        assert result["selected"] is None
        assert result["files_changed"] == 0
        assert result.get("fallback_error") == "move_instance_method_unresolved_callsites"
        assert source.read_text(encoding="utf-8") == original_source
        assert target.read_text(encoding="utf-8") == original_target
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_instance_method_and_rewrites_conditional_local_factory_alias_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def __init__(self, config):\n"
            "        self.config = config\n"
            "\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def build_service(config):\n"
            "    if config:\n"
            "        return UserService(config)\n"
            "    else:\n"
            "        return UserService({'mode': 'default'})\n"
            "\n"
            "def run(value, config):\n"
            "    svc = build_service(config)\n"
            "    return svc.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 5,
                "start_character": 4,
                "end_line": 6,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "def normalize(self, value):" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "svc = build_service(config)" in source_text
        assert "return normalize(value)" in source_text
        assert "svc.normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_instance_method_and_rewrites_local_factory_assignment_return_alias_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def build_service(config):\n"
            "    svc = UserService(config)\n"
            "    return svc\n"
            "\n"
            "def run(value, config):\n"
            "    service = build_service(config)\n"
            "    return service.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "def normalize(self, value):" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "service = build_service(config)" in source_text
        assert "return normalize(value)" in source_text
        assert "service.normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_moves_instance_method_and_rewrites_transitive_local_factory_wrapper_alias_calls() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def build_service(config):\n"
            "    return UserService(config)\n"
            "\n"
            "def make_service(config):\n"
            "    return build_service(config)\n"
            "\n"
            "def run(value, config):\n"
            "    service = make_service(config)\n"
            "    return service.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 2

        source_text = source.read_text(encoding="utf-8")
        target_text = target.read_text(encoding="utf-8")
        assert "def normalize(self, value):" not in target_text
        assert "def normalize(value):" in target_text
        assert "from utils import normalize" in source_text
        assert "service = make_service(config)" in source_text
        assert "return normalize(value)" in source_text
        assert "service.normalize(value)" not in source_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_constructor_callsites_for_instance_method() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def passthrough(value):\n"
            "    return value\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import UserService\n"
            "\n"
            "def use(value):\n"
            "    return UserService().normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "UserService().normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_imported_factory_alias_callsites_for_instance_method() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "\n"
            "def use(value, config):\n"
            "    svc = make_service(config)\n"
            "    return svc.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "svc.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_module_imported_factory_alias_callsites_for_instance_method() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "\n"
            "def use(value, config):\n"
            "    svc = service_mod.make_service(config)\n"
            "    return svc.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "svc.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_transitive_wrapper_over_imported_factory_alias_callsites_for_instance_method() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "\n"
            "def provide_service(config):\n"
            "    return make_service(config)\n"
            "\n"
            "def use(value, config):\n"
            "    svc = provide_service(config)\n"
            "    return svc.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "svc.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_multistep_wrapper_with_branch_over_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "\n"
            "def provide_service(config):\n"
            "    base = make_service(config)\n"
            "    if config:\n"
            "        chosen = base\n"
            "    else:\n"
            "        chosen = make_service({'mode': 'default'})\n"
            "    result = chosen\n"
            "    return result\n"
            "\n"
            "def use(value, config):\n"
            "    current = provide_service(config)\n"
            "    final = current\n"
            "    return final.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "final.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_multistep_wrapper_over_module_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "\n"
            "def provide_service(config):\n"
            "    base = service_mod.make_service(config)\n"
            "    result = base\n"
            "    return result\n"
            "\n"
            "def use(value, config):\n"
            "    current = provide_service(config)\n"
            "    return current.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "current.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_parameter_passthrough_wrapper_over_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "\n"
            "def relay(service):\n"
            "    return service\n"
            "\n"
            "def use(value, config):\n"
            "    created = make_service(config)\n"
            "    forwarded = relay(created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_parameter_passthrough_wrapper_over_module_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "\n"
            "def relay(service):\n"
            "    return service\n"
            "\n"
            "def use(value, config):\n"
            "    created = service_mod.make_service(config)\n"
            "    forwarded = relay(created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_chained_parameter_passthrough_wrappers_over_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "\n"
            "def relay_b(service):\n"
            "    return service\n"
            "\n"
            "def relay_a(current):\n"
            "    return relay_b(current)\n"
            "\n"
            "def use(value, config):\n"
            "    created = make_service(config)\n"
            "    forwarded = relay_a(created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_chained_parameter_passthrough_wrappers_over_module_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "\n"
            "def relay_b(service):\n"
            "    return service\n"
            "\n"
            "def relay_a(current):\n"
            "    return relay_b(current)\n"
            "\n"
            "def use(value, config):\n"
            "    created = service_mod.make_service(config)\n"
            "    forwarded = relay_a(created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_assignment_return_chained_passthrough_with_arg_reorder_over_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "\n"
            "def relay_b(primary, secondary):\n"
            "    return primary\n"
            "\n"
            "def relay_a(x, y):\n"
            "    wrapped = relay_b(y, x)\n"
            "    return wrapped\n"
            "\n"
            "def use(value, config):\n"
            "    created = make_service(config)\n"
            "    forwarded = relay_a('noop', created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_assignment_return_chained_passthrough_with_arg_reorder_over_module_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "\n"
            "def relay_b(primary, secondary):\n"
            "    return primary\n"
            "\n"
            "def relay_a(x, y):\n"
            "    wrapped = relay_b(y, x)\n"
            "    return wrapped\n"
            "\n"
            "def use(value, config):\n"
            "    created = service_mod.make_service(config)\n"
            "    forwarded = relay_a('noop', created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_branch_return_passthrough_wrapper_over_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "\n"
            "def relay(service):\n"
            "    return service\n"
            "\n"
            "def choose(primary, fallback, use_primary):\n"
            "    if use_primary:\n"
            "        return relay(primary)\n"
            "    return relay(fallback)\n"
            "\n"
            "def use(value, config):\n"
            "    created = make_service(config)\n"
            "    forwarded = choose(created, created, config is not None)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_branch_return_passthrough_wrapper_over_module_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "\n"
            "def relay(service):\n"
            "    return service\n"
            "\n"
            "def choose(primary, fallback, use_primary):\n"
            "    if use_primary:\n"
            "        return relay(primary)\n"
            "    return relay(fallback)\n"
            "\n"
            "def use(value, config):\n"
            "    created = service_mod.make_service(config)\n"
            "    forwarded = choose(created, created, config is not None)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_kwonly_passthrough_wrapper_over_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "\n"
            "def relay(*, service):\n"
            "    return service\n"
            "\n"
            "def use(value, config):\n"
            "    created = make_service(config)\n"
            "    forwarded = relay(service=created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_kwonly_passthrough_wrapper_over_module_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "\n"
            "def relay(*, service):\n"
            "    return service\n"
            "\n"
            "def use(value, config):\n"
            "    created = service_mod.make_service(config)\n"
            "    forwarded = relay(service=created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_imported_external_wrapper_over_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        wrappers = temp_root / "helpers.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        wrappers.write_text(
            "def relay(service):\n"
            "    return service\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "from helpers import relay\n"
            "\n"
            "def use(value, config):\n"
            "    created = make_service(config)\n"
            "    forwarded = relay(created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_module_imported_external_wrapper_over_module_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        wrappers = temp_root / "helpers.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        wrappers.write_text(
            "def relay(service):\n"
            "    return service\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "import helpers as helper_mod\n"
            "\n"
            "def use(value, config):\n"
            "    created = service_mod.make_service(config)\n"
            "    forwarded = helper_mod.relay(created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_external_transitive_imported_wrapper_over_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        bridge = temp_root / "bridge.py"
        helpers = temp_root / "helpers.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        bridge.write_text(
            "def relay(service):\n"
            "    return service\n",
            encoding="utf-8",
        )
        helpers.write_text(
            "from bridge import relay\n"
            "\n"
            "def relay_twice(service):\n"
            "    return relay(service)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "from service import make_service\n"
            "from helpers import relay_twice\n"
            "\n"
            "def use(value, config):\n"
            "    created = make_service(config)\n"
            "    forwarded = relay_twice(created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_rewrites_cross_file_external_transitive_module_wrapper_over_module_imported_factory_alias_callsites() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        bridge = temp_root / "bridge.py"
        helpers = temp_root / "helpers.py"
        consumer = temp_root / "consumer.py"
        target = temp_root / "utils.py"
        source.write_text(
            "class UserService:\n"
            "    def normalize(self, value):\n"
            "        return value.strip().lower()\n"
            "\n"
            "def make_service(config):\n"
            "    return UserService(config)\n",
            encoding="utf-8",
        )
        bridge.write_text(
            "def relay(service):\n"
            "    return service\n",
            encoding="utf-8",
        )
        helpers.write_text(
            "import bridge as bridge_mod\n"
            "\n"
            "def relay_twice(service):\n"
            "    return bridge_mod.relay(service)\n",
            encoding="utf-8",
        )
        consumer.write_text(
            "import service as service_mod\n"
            "import helpers as helper_mod\n"
            "\n"
            "def use(value, config):\n"
            "    created = service_mod.make_service(config)\n"
            "    forwarded = helper_mod.relay_twice(created)\n"
            "    return forwarded.normalize(value)\n",
            encoding="utf-8",
        )
        target.write_text(
            "def untouched():\n"
            "    return 'ok'\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 2,
                "start_character": 4,
                "end_line": 3,
                "end_character": 35,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "move"
        assert result["files_changed"] == 3

        consumer_text = consumer.read_text(encoding="utf-8")
        assert "from utils import normalize" in consumer_text
        assert "return normalize(value)" in consumer_text
        assert "forwarded.normalize(value)" not in consumer_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_move_refactor_does_not_mutate_source_when_target_is_invalid_python() -> None:
    temp_root = _create_temp_dir()
    try:
        source = temp_root / "service.py"
        target = temp_root / "utils.py"
        source.write_text(
            "def helper(value):\n"
            "    return value.strip().lower()\n"
            "\n"
            "def run(value):\n"
            "    return helper(value)\n",
            encoding="utf-8",
        )
        # Intentionally invalid python in target to force fallback parse failure.
        target.write_text(
            "def broken(:\n"
            "    pass\n",
            encoding="utf-8",
        )
        original_source = source.read_text(encoding="utf-8")
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(source),
                "target_path": str(target),
                "start_line": 1,
                "start_character": 0,
                "end_line": 2,
                "end_character": 33,
                "kinds": ["refactor.move"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["applied"] is False
        assert result["selected"] is None
        assert result["files_changed"] == 0
        assert result.get("fallback_error") == "move_target_invalid_python"
        assert source.read_text(encoding="utf-8") == original_source
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_inline_refactor_falls_back_when_lsp_action_missing() -> None:
    temp_root = _create_temp_dir()
    try:
        target = temp_root / "formatting.py"
        target.write_text(
            "def normalize_name(name):\n"
            "    return name.strip().lower()\n"
            "\n"
            "def greet(name):\n"
            "    return 'hello ' + normalize_name(name)\n",
            encoding="utf-8",
        )
        tool = LSPTool()
        context = ToolContext(
            metadata={
                "current_cwd": str(temp_root),
                "lsp_client": NoActionLSPClient(),
                "lsp_strict": True,
            }
        )

        result = await tool.call(
            {
                "operation": "apply_refactor",
                "path": str(target),
                "start_line": 4,
                "start_character": 11,
                "end_line": 4,
                "end_character": 43,
                "kinds": ["refactor.inline"],
                "apply": True,
            },
            context,
            None,
            None,
            lambda _event: None,
        )

        assert result["backend"] == "semantic_fallback"
        assert result["fallback_attempted"] is True
        assert result["selected"]["normalized_kind"] == "inline"
        assert result["files_changed"] == 1
        updated = target.read_text(encoding="utf-8")
        assert "return 'hello ' + name.strip().lower()" in updated
        assert "return 'hello ' + normalize_name(name)" not in updated
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
