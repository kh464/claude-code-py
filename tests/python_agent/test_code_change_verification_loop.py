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
    root = Path("tests/.tmp-python-agent") / f"verification-loop-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_agent_requires_verification_before_complete() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-verification-pass",
            metadata={"task_root": str(temp_root / "tasks"), "current_cwd": str(temp_root)},
        )

        result = await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "apply edit and verify",
                "run_in_background": False,
                "verification_commands": ["python -c \"print('verification-ok')\""],
            },
            context=context,
        )
        payload = result["raw_result"]
        assert payload["status"] == "completed"
        assert payload["verification"]["status"] in {"passed", "failed"}
        assert payload["verification"]["results"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_agent_verification_reports_failed_command() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-verification-fail",
            metadata={"task_root": str(temp_root / "tasks"), "current_cwd": str(temp_root)},
        )

        result = await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "apply edit and verify",
                "run_in_background": False,
                "verification_commands": ["python -c \"import sys; sys.exit(3)\""],
            },
            context=context,
        )
        payload = result["raw_result"]
        assert payload["status"] == "failed"
        assert payload["verification"]["status"] == "failed"
        assert payload["verification"]["results"][0]["returncode"] != 0
        assert "orchestration" in payload
        assert payload["orchestration"]["decision_trace"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
