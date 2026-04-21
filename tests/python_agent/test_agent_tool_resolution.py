from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.errors import ToolExecutionError
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"agent-resolution-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_agent_tool_applies_named_agent_defaults_and_tool_filters() -> None:
    temp_root = _create_temp_dir()
    try:
        project_agents = temp_root / ".claude" / "agents"
        project_agents.mkdir(parents=True, exist_ok=True)
        (project_agents / "reviewer.md").write_text(
            """---
name: reviewer
description: review specialist
tools: Read, Glob, Grep
disallowedTools: Glob
model: inherit
permissionMode: plan
background: true
isolation: worktree
initialPrompt: /search TODO
---
You are a reviewer.
""",
            encoding="utf-8",
        )

        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-agent-resolution",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "project_agents_dir": str(project_agents),
                "available_tools": [
                    "BashTool",
                    "FileReadTool",
                    "GlobTool",
                    "GrepTool",
                    "FileWriteTool",
                ],
            },
        )
        result = await runtime.execute_tool_use(
            "AgentTool",
            {"subagent_type": "reviewer", "prompt": "analyze repo"},
            context=context,
        )

        payload = result["raw_result"]
        assert payload["status"] == "async_launched"
        assert payload["name"] == "reviewer"
        assert payload["selected_agent"]["name"] == "reviewer"
        assert payload["effective_model"] == "inherit"
        assert payload["effective_isolation"] == "worktree"
        assert payload["effective_permission_mode"] == "plan"
        assert payload["effective_prompt"].startswith("/search TODO\n")
        assert payload["resolved_tools"] == ["FileReadTool", "GrepTool"]

        await runtime.execute_tool_use(
            "TaskStopTool",
            {"task_id": payload["task_id"]},
            context=context,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_agent_tool_rejects_unknown_subagent_type() -> None:
    runtime = _build_runtime()
    context = ToolContext(session_id="session-agent-unknown")

    with pytest.raises(ToolExecutionError, match="Unknown subagent_type"):
        await runtime.execute_tool_use(
            "AgentTool",
            {"subagent_type": "does-not-exist", "prompt": "hello"},
            context=context,
        )
