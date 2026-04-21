from __future__ import annotations

import asyncio
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
    root = Path("tests/.tmp-python-agent") / f"agent-flow-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


async def _wait_for_status(
    runtime: ToolRuntime,
    *,
    task_id: str,
    context: ToolContext,
    expected: set[str],
    timeout_s: float = 3.0,
) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while True:
        result = await runtime.execute_tool_use("TaskOutputTool", {"task_id": task_id}, context=context)
        payload = result["raw_result"]
        if payload.get("status") in expected:
            return payload
        if asyncio.get_running_loop().time() >= deadline:
            return payload
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_agent_tool_background_launch_returns_task_metadata() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-agent-bg",
            metadata={"task_root": str(temp_root / "tasks")},
        )
        launched = await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "run a longer investigation task",
                "run_in_background": True,
                "name": "worker-a",
            },
            context=context,
        )
        payload = launched["raw_result"]

        assert payload["status"] == "async_launched"
        assert payload["task_id"].startswith("task-")
        assert payload["agent_id"].startswith("agent-")
        assert Path(payload["output_file"]).exists()

        await runtime.execute_tool_use(
            "TaskStopTool",
            {"task_id": payload["task_id"]},
            context=context,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_send_message_and_task_output_route_to_running_agent() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-send-message",
            metadata={"task_root": str(temp_root / "tasks")},
        )
        launched = await runtime.execute_tool_use(
            "AgentTool",
            {"prompt": "watch for inbox messages", "run_in_background": True},
            context=context,
        )
        launch_payload = launched["raw_result"]

        send_result = await runtime.execute_tool_use(
            "SendMessageTool",
            {"agent_id": launch_payload["agent_id"], "message": "ping from parent"},
            context=context,
        )
        assert send_result["raw_result"]["delivered"] is True

        output_payload = await _wait_for_status(
            runtime,
            task_id=launch_payload["task_id"],
            context=context,
            expected={"running", "completed"},
        )
        assert "ping from parent" in output_payload["output"]

        await runtime.execute_tool_use(
            "TaskStopTool",
            {"task_id": launch_payload["task_id"]},
            context=context,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_task_stop_transitions_background_agent_to_stopped() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-stop-task",
            metadata={"task_root": str(temp_root / "tasks")},
        )
        launched = await runtime.execute_tool_use(
            "AgentTool",
            {"prompt": "long task for stop testing", "run_in_background": True},
            context=context,
        )
        launch_payload = launched["raw_result"]

        stop_result = await runtime.execute_tool_use(
            "TaskStopTool",
            {"task_id": launch_payload["task_id"]},
            context=context,
        )
        assert stop_result["raw_result"]["stopped"] is True

        output_payload = await _wait_for_status(
            runtime,
            task_id=launch_payload["task_id"],
            context=context,
            expected={"stopped"},
        )
        assert output_payload["status"] == "stopped"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_enter_and_exit_worktree_respects_cleanup_policy() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-worktree",
            metadata={
                "worktree_root": str(temp_root / "worktrees"),
                "current_cwd": str(temp_root),
            },
        )

        entered_clean = await runtime.execute_tool_use(
            "EnterWorktreeTool",
            {"name": "clean-tree"},
            context=context,
        )
        clean_path = Path(entered_clean["raw_result"]["worktree_path"])
        assert clean_path.exists()

        exited_clean = await runtime.execute_tool_use(
            "ExitWorktreeTool",
            {"action": "auto"},
            context=context,
        )
        assert exited_clean["raw_result"]["kept"] is False
        assert not clean_path.exists()

        entered_dirty = await runtime.execute_tool_use(
            "EnterWorktreeTool",
            {"name": "dirty-tree"},
            context=context,
        )
        dirty_path = Path(entered_dirty["raw_result"]["worktree_path"])
        (dirty_path / "notes.txt").write_text("pending changes\n", encoding="utf-8")

        exited_dirty = await runtime.execute_tool_use(
            "ExitWorktreeTool",
            {"action": "auto"},
            context=context,
        )
        assert exited_dirty["raw_result"]["kept"] is True
        assert dirty_path.exists()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_agent_tool_resume_returns_existing_task_metadata() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-agent-resume",
            metadata={"task_root": str(temp_root / "tasks")},
        )

        launched = await runtime.execute_tool_use(
            "AgentTool",
            {"prompt": "background for resume", "run_in_background": True},
            context=context,
        )
        launch_payload = launched["raw_result"]

        resumed = await runtime.execute_tool_use(
            "AgentTool",
            {"resume_task_id": launch_payload["task_id"]},
            context=context,
        )
        resume_payload = resumed["raw_result"]
        assert resume_payload["status"] == "resumed"
        assert resume_payload["task_id"] == launch_payload["task_id"]
        assert resume_payload["agent_id"] == launch_payload["agent_id"]

        await runtime.execute_tool_use(
            "TaskStopTool",
            {"task_id": launch_payload["task_id"]},
            context=context,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_agent_tool_worktree_isolation_returns_worktree_metadata() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-agent-worktree-isolation",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "worktree_root": str(temp_root / "worktrees"),
                "current_cwd": str(temp_root),
            },
        )

        launched = await runtime.execute_tool_use(
            "AgentTool",
            {"prompt": "do isolated changes", "run_in_background": True, "isolation": "worktree"},
            context=context,
        )
        payload = launched["raw_result"]
        assert payload["effective_isolation"] == "worktree"
        assert payload["worktree_path"]
        assert Path(payload["worktree_path"]).exists()
        assert payload["worktree_branch"].startswith("worktree/")

        resumed = await runtime.execute_tool_use(
            "AgentTool",
            {"resume_task_id": payload["task_id"]},
            context=context,
        )
        resumed_payload = resumed["raw_result"]
        assert resumed_payload["worktree_path"] == payload["worktree_path"]
        assert resumed_payload["worktree_branch"] == payload["worktree_branch"]

        await runtime.execute_tool_use(
            "TaskStopTool",
            {"task_id": payload["task_id"]},
            context=context,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_agent_tool_foreground_worktree_with_verification_runs_orchestration() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-agent-worktree-orchestration",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "worktree_root": str(temp_root / "worktrees"),
                "current_cwd": str(temp_root),
            },
        )
        result = await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "refine implementation with verification",
                "run_in_background": False,
                "isolation": "worktree",
                "verification_commands": ["python -c \"print('ok')\""],
            },
            context=context,
        )
        payload = result["raw_result"]
        assert payload["effective_isolation"] == "worktree"
        assert payload["task_id"].startswith("task-")
        assert payload["agent_id"].startswith("agent-")
        assert Path(payload["output_file"]).exists()
        assert payload["worktree_path"]
        assert payload["worktree_branch"].startswith("worktree/")
        assert "orchestration" in payload
        assert payload["verification"]["status"] in {"passed", "failed"}
        assert "worktree_cleanup" in payload
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_agent_tool_background_with_verification_uses_orchestration_and_can_fail() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-agent-bg-orchestration",
            metadata={"task_root": str(temp_root / "tasks"), "current_cwd": str(temp_root)},
        )
        launched = await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "background code change with verification",
                "run_in_background": True,
                "verification_commands": ["python -c \"import sys; sys.exit(7)\""],
            },
            context=context,
        )
        launch_payload = launched["raw_result"]
        final_payload = await _wait_for_status(
            runtime,
            task_id=launch_payload["task_id"],
            context=context,
            expected={"failed", "completed"},
            timeout_s=4.0,
        )
        assert final_payload["status"] == "failed"
        assert "orchestration_status=failed" in final_payload["output"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
