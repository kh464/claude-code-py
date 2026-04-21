from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.subagents.executor import SubagentExecutor
from agent.subagents.task_manager import TaskManager
from agent.tools.agent_tool import AgentTool


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"subagent-executor-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


class BlockingExecutor(SubagentExecutor):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def run(self, *, task_id: str, prompt: str, context: ToolContext) -> dict:
        _ = task_id, prompt, context
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


async def agent_tool_call(tool: AgentTool, args: dict, *, context: ToolContext) -> dict:
    events: list[dict] = []

    def on_progress(event: dict) -> None:
        events.append(event)

    result = await tool.call(args, context, lambda _: True, None, on_progress)
    assert events
    return result


@pytest.mark.asyncio
async def test_subagent_executor_spawn_resume_stop() -> None:
    temp_root = _create_temp_dir()
    try:
        executor = BlockingExecutor()
        task_manager = TaskManager(default_root=temp_root / "tasks", executor=executor)
        tool = AgentTool(task_manager=task_manager)
        context = ToolContext(session_id="session-subagent-executor")

        launched = await agent_tool_call(
            tool,
            {"prompt": "edit file", "run_in_background": True},
            context=context,
        )
        await asyncio.wait_for(executor.started.wait(), timeout=1.0)

        resumed = await agent_tool_call(
            tool,
            {"resume_task_id": launched["task_id"]},
            context=context,
        )

        assert resumed["status"] == "resumed"
        assert resumed["task_id"] == launched["task_id"]

        stopped = await task_manager.stop(task_id=launched["task_id"], context=context)
        assert stopped["stopped"] is True
        assert stopped["status"] == "stopped"
        assert executor.cancelled is True
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
