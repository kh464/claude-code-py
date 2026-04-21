from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.subagents.task_manager import TaskManager
from agent.tools.agent_tool import AgentTool


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"subagent-runtime-v2-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


async def _agent_tool_call(tool: AgentTool, args: dict, *, context: ToolContext) -> dict:
    events: list[dict] = []

    def on_progress(event: dict) -> None:
        events.append(event)

    result = await tool.call(args, context, lambda _: True, None, on_progress)
    assert events
    return result


@pytest.mark.asyncio
async def test_subagent_runtime_v2_runs_multi_turn_with_tool_events() -> None:
    temp_root = _create_temp_dir()
    try:
        manager = TaskManager(default_root=temp_root / "tasks")
        tool = AgentTool(task_manager=manager)
        context = ToolContext(
            session_id="session-runtime-v2",
            metadata={
                "available_tools": ["BriefTool"],
                "include_conditionals": True,
            },
        )

        result = await _agent_tool_call(
            tool,
            {"prompt": "Read, edit, and summarize", "run_in_background": False},
            context=context,
        )
        assert result["status"] == "completed"
        phases = result.get("orchestration", {}).get("phases", [])
        assert phases
        assert "plan" in phases
        assert "review" in phases
        assert result["steps_completed"] == len(phases)
        assert result["total_steps"] == len(phases)
        assert result["output"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_subagent_runtime_v2_enforces_orchestrator_even_if_disabled_flag_set() -> None:
    temp_root = _create_temp_dir()
    try:
        manager = TaskManager(default_root=temp_root / "tasks")
        tool = AgentTool(task_manager=manager)
        context = ToolContext(
            session_id="session-runtime-v2-force-orchestrator",
            metadata={
                "available_tools": ["BriefTool"],
                "include_conditionals": True,
                "subagent_use_orchestrator": False,
            },
        )

        result = await _agent_tool_call(
            tool,
            {"prompt": "Read, edit, and summarize", "run_in_background": False},
            context=context,
        )
        assert result["status"] == "completed"
        assert result.get("orchestration")
        assert result["orchestration"]["phases"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
