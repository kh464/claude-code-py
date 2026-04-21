from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.base import StaticTool
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"high-frequency-tools-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root.resolve()


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


def test_high_frequency_tools_are_not_static_stubs() -> None:
    registry = ToolRegistry(include_conditionals=True)
    for name in ("TodoWriteTool", "EnterPlanModeTool", "ExitPlanModeV2Tool", "AskUserQuestionTool"):
        tool = registry.get(name)
        assert not isinstance(tool, StaticTool), f"{name} should be concrete tool, not StaticTool"


def test_all_registered_tools_are_concrete_after_de_stubbing() -> None:
    registry = ToolRegistry(include_conditionals=True)
    static_tools = [tool.metadata.name for tool in registry.get_all_base_tools() if isinstance(tool, StaticTool)]
    assert static_tools == []


@pytest.mark.asyncio
async def test_todo_write_tool_persists_structured_todos() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        todo_path = temp_root / "todo-store.json"
        context = ToolContext(session_id="todo-test", metadata={"todo_file": str(todo_path)})
        result = await runtime.execute_tool_use(
            "TodoWriteTool",
            {
                "todos": [
                    {"content": "design parity closure", "status": "in_progress"},
                    {"content": "add tests", "status": "pending"},
                ]
            },
            context=context,
        )
        payload = result["raw_result"]
        assert payload["total"] == 2
        assert payload["in_progress"] == 1
        assert payload["pending"] == 1
        saved = json.loads(todo_path.read_text(encoding="utf-8"))
        assert len(saved["todos"]) == 2
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_plan_mode_tools_toggle_context_state() -> None:
    runtime = _build_runtime()
    context = ToolContext(session_id="plan-test", metadata={})
    entered = await runtime.execute_tool_use(
        "EnterPlanModeTool",
        {"reason": "complex change"},
        context=context,
    )
    assert entered["raw_result"]["plan_mode"] is True
    assert context.metadata["plan_mode"] is True

    exited = await runtime.execute_tool_use(
        "ExitPlanModeV2Tool",
        {"summary": "plan completed"},
        context=context,
    )
    assert exited["raw_result"]["plan_mode"] is False
    assert context.metadata["plan_mode"] is False
    assert context.metadata["plan_mode_summary"] == "plan completed"


@pytest.mark.asyncio
async def test_ask_user_question_tool_returns_structured_prompt() -> None:
    runtime = _build_runtime()
    result = await runtime.execute_tool_use(
        "AskUserQuestionTool",
        {"question": "choose strategy", "header": "Decision", "options": ["A", "B"]},
    )
    payload = result["raw_result"]
    assert payload["status"] == "needs_user_input"
    assert payload["question"] == "choose strategy"
    assert payload["options"] == ["A", "B"]
