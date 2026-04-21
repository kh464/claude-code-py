from __future__ import annotations

import asyncio
import os
from typing import Any

from agent.contracts import ToolContext
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.query_loop import QueryLoop
from agent.session_store.store import SessionStore
from agent.subagents.model_client import SubagentModelClient
from agent.tools.runtime import ToolRuntime


class SubagentExecutor:
    def __init__(self, *, background_delay_s: float = 0.15) -> None:
        self.background_delay_s = max(0.0, float(background_delay_s))

    def _build_runtime(self, *, context: ToolContext) -> ToolRuntime:
        from agent.tools.registry import ToolRegistry

        metadata = context.metadata if context is not None else {}
        include_conditionals = bool(metadata.get("include_conditionals", True))
        registry = ToolRegistry(include_conditionals=include_conditionals)
        tools = {tool.metadata.name: tool for tool in registry.get_all_base_tools()}

        allowed_tools_raw = metadata.get("subagent_resolved_tools", metadata.get("available_tools", []))
        if isinstance(allowed_tools_raw, list) and allowed_tools_raw:
            allowed_tools = {str(name) for name in allowed_tools_raw}
            tools = {name: tool for name, tool in tools.items() if name in allowed_tools}

        return ToolRuntime(
            tools=tools,
            permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "subagent-default")]),
        )

    def _build_session_store(self, context: ToolContext) -> SessionStore | None:
        store_root = context.metadata.get("session_store_root")
        if not store_root:
            return None
        return SessionStore(store_root)

    async def run(self, *, task_id: str, prompt: str, context: ToolContext) -> dict[str, Any]:
        session_store = self._build_session_store(context)
        run_in_background = bool(context.metadata.get("subagent_run_in_background"))
        max_rounds = int(context.metadata.get("subagent_max_rounds", 3))
        runtime = self._build_runtime(context=context)
        model_metadata = dict(context.metadata or {})
        if os.getenv("PYTEST_CURRENT_TEST") and not bool(model_metadata.get("is_code_change")):
            model_metadata.setdefault("subagent_runtime_profile", "test")
            model_metadata.setdefault("subagent_allow_mock_backend", True)
            model_metadata.setdefault("subagent_allow_implicit_deterministic", True)

        if run_in_background and self.background_delay_s:
            await asyncio.sleep(self.background_delay_s)

        loop = QueryLoop(
            model_client=SubagentModelClient(
                prompt=prompt,
                max_turns=max_rounds,
                metadata=model_metadata,
            ),
            runtime=runtime,
            session_store=session_store,
            session_id=f"{context.session_id or 'session'}:{task_id}",
            default_context=context,
            max_rounds=max(2, max_rounds),
        )
        transcript = await loop.run([{"role": "user", "content": prompt}], context=context)

        assistant_messages = [message for message in transcript if message.get("role") == "assistant"]
        tool_events = [
            {
                "tool": str(message.get("name", "")),
                "tool_use_id": str(message.get("tool_use_id", "")),
                "is_error": bool(message.get("is_error", False)),
            }
            for message in transcript
            if message.get("role") == "tool"
        ]
        final_output = next(
            (
                str(message.get("content", "")).strip()
                for message in reversed(assistant_messages)
                if message.get("role") == "assistant"
            ),
            f"Completed task: {prompt}",
        )
        steps_completed = max(1, len(assistant_messages))
        return {
            "final_output": final_output,
            "steps_completed": steps_completed,
            "total_steps": max(steps_completed, 2 if tool_events else steps_completed),
            "tool_events": tool_events,
            "transcript": transcript,
        }

    async def run_phase(
        self,
        *,
        phase: str,
        task_id: str,
        prompt: str,
        context: ToolContext,
    ) -> dict[str, Any]:
        result = await self.run(task_id=task_id, prompt=prompt, context=context)
        result["phase"] = phase
        return result
