from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime
import agent.subagents.model_client as model_client_module


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"verification-required-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


def _mock_real_model_response(monkeypatch) -> None:
    def fake_urlopen(request, timeout=0):
        _ = timeout
        body = json.loads(request.data.decode("utf-8"))
        messages = list(body.get("messages", [])) if isinstance(body, dict) else []
        prompt_text = ""
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                prompt_text = content
                break

        if "planning phase" in prompt_text:
            content_payload = {
                "content": json.dumps(
                    {
                        "steps": ["analyze target files", "apply focused edits", "run verification"],
                        "risks": ["regression in adjacent modules"],
                        "verification_focus": ["targeted tests", "smoke checks"],
                    }
                ),
                "tool_uses": [],
            }
        elif "reviewer phase" in prompt_text:
            content_payload = {
                "content": json.dumps(
                    {
                        "verdict": "pass",
                        "score": 90,
                        "blocking_issues": [],
                        "fix_plan": [],
                    }
                ),
                "tool_uses": [],
            }
        else:
            content_payload = {
                "content": "verification workflow proceed",
                "tool_uses": [],
            }

        payload = {"choices": [{"message": {"content": json.dumps(content_payload)}}]}
        return _FakeHTTPResponse(payload)

    monkeypatch.setattr(model_client_module, "urlopen", fake_urlopen)


@pytest.mark.asyncio
async def test_code_change_task_without_verification_is_blocked() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-verification-required",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "current_cwd": str(temp_root),
                "is_code_change": True,
                "subagent_allow_implicit_deterministic": True,
            },
        )
        result = await runtime.execute_tool_use(
            "AgentTool",
            {"prompt": "modify function implementation", "run_in_background": False},
            context=context,
        )
        payload = result["raw_result"]
        assert payload["status"] == "blocked"
        assert "verification required" in payload["reason"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_code_change_task_with_verification_is_allowed(monkeypatch) -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        _mock_real_model_response(monkeypatch)
        context = ToolContext(
            session_id="session-verification-allowed",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "current_cwd": str(temp_root),
                "is_code_change": True,
                "subagent_model_backend": "openai_chat",
                "subagent_model_api_key": "test-key",
                "subagent_model_endpoint": "https://example.invalid/v1/chat/completions",
            },
        )
        result = await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "modify function implementation",
                "run_in_background": False,
                "verification_commands": ["python -c \"print('ok')\""],
            },
            context=context,
        )
        payload = result["raw_result"]
        assert payload["status"] == "completed"
        assert payload["verification"]["status"] in {"passed", "failed"}
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_code_change_task_uses_default_verification_commands_from_context(monkeypatch) -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        _mock_real_model_response(monkeypatch)
        context = ToolContext(
            session_id="session-verification-defaults",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "current_cwd": str(temp_root),
                "is_code_change": True,
                "default_verification_commands": ["python -c \"print('default-ok')\""],
                "subagent_model_backend": "openai_chat",
                "subagent_model_api_key": "test-key",
                "subagent_model_endpoint": "https://example.invalid/v1/chat/completions",
            },
        )
        result = await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "modify function implementation",
                "run_in_background": False,
            },
            context=context,
        )
        payload = result["raw_result"]
        assert payload["status"] in {"completed", "failed"}
        assert payload["verification"]["results"]
        assert payload["verification"]["results"][0]["command"] == "python -c \"print('default-ok')\""
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_code_change_task_defaults_to_strict_model_mode_without_implicit_deterministic() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        context = ToolContext(
            session_id="session-verification-strict-model",
            metadata={
                "task_root": str(temp_root / "tasks"),
                "current_cwd": str(temp_root),
                "is_code_change": True,
                "subagent_model_api_key_env": "NON_EXISTENT_SUBAGENT_MODEL_KEY",
            },
        )
        result = await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "modify function implementation",
                "run_in_background": False,
                "verification_commands": ["python -c \"print('ok')\""],
            },
            context=context,
        )
        payload = result["raw_result"]
        assert payload["status"] == "failed"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
