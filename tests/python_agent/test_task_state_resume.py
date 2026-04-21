from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"task-resume-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_task_state_can_be_restored_by_task_id_and_agent_id() -> None:
    temp_root = _create_temp_dir()
    try:
        context = ToolContext(
            session_id="session-resume",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "session_store_root": str(temp_root / "store"),
            },
        )
        runtime_a = _build_runtime()
        launched = await runtime_a.execute_tool_use(
            "AgentTool",
            {"prompt": "one-shot summary task"},
            context=context,
        )
        payload = launched["raw_result"]
        assert payload["status"] == "completed"

        runtime_b = _build_runtime()
        by_task_id = await runtime_b.execute_tool_use(
            "TaskOutputTool",
            {"task_id": payload["task_id"]},
            context=context,
        )
        by_agent_id = await runtime_b.execute_tool_use(
            "TaskOutputTool",
            {"agent_id": payload["agent_id"]},
            context=context,
        )

        task_payload = by_task_id["raw_result"]
        agent_payload = by_agent_id["raw_result"]
        assert task_payload["status"] == "completed"
        assert task_payload["task_id"] == payload["task_id"]
        assert task_payload["agent_id"] == payload["agent_id"]
        assert "Completed task:" in task_payload["output"]
        assert agent_payload["task_id"] == payload["task_id"]
        assert agent_payload["agent_id"] == payload["agent_id"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_task_stop_can_restore_existing_completed_task() -> None:
    temp_root = _create_temp_dir()
    try:
        context = ToolContext(
            session_id="session-resume-stop",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "session_store_root": str(temp_root / "store"),
            },
        )
        runtime_a = _build_runtime()
        launched = await runtime_a.execute_tool_use(
            "AgentTool",
            {"prompt": "already finished"},
            context=context,
        )
        payload = launched["raw_result"]

        runtime_b = _build_runtime()
        stop_result = await runtime_b.execute_tool_use(
            "TaskStopTool",
            {"task_id": payload["task_id"]},
            context=context,
        )
        stop_payload = stop_result["raw_result"]
        assert stop_payload["stopped"] is False
        assert stop_payload["status"] == "completed"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
