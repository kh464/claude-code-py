from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef
from agent.errors import (
    InputValidationError,
    PermissionDeniedError,
    ToolExecutionError,
    ToolInterruptedError,
)
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode


def _type_matches(value: Any, type_name: str) -> bool:
    match type_name:
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        case "boolean":
            return isinstance(value, bool)
        case "array":
            return isinstance(value, list)
        case "object":
            return isinstance(value, dict)
        case _:
            return True


def validate_schema(args: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    schema_type = schema.get("type")
    if schema_type == "object" and not isinstance(args, Mapping):
        raise InputValidationError("Tool arguments must be an object")
    required = schema.get("required", [])
    for key in required:
        if key not in args:
            raise InputValidationError(f"Missing required field: {key}")
    properties = schema.get("properties", {})
    for key, prop_schema in properties.items():
        if key in args:
            expected_type = prop_schema.get("type")
            if expected_type and not _type_matches(args[key], expected_type):
                raise InputValidationError(f"Field '{key}' must be of type {expected_type}")


class ToolRuntime:
    def __init__(
        self,
        *,
        tools: dict[str, ToolDef],
        permission_engine: PermissionEngine | None = None,
        pre_tool_use_hooks: list[Callable[..., Any]] | None = None,
        post_tool_use_hooks: list[Callable[..., Any]] | None = None,
        failure_tool_use_hooks: list[Callable[..., Any]] | None = None,
        permission_ask_resolver: Callable[..., Any] | None = None,
    ) -> None:
        self.tools = tools
        self.permission_engine = permission_engine or PermissionEngine()
        self.pre_tool_use_hooks = pre_tool_use_hooks or []
        self.post_tool_use_hooks = post_tool_use_hooks or []
        self.failure_tool_use_hooks = failure_tool_use_hooks or []
        self.permission_ask_resolver = permission_ask_resolver

    async def _run_failure_hooks(
        self,
        tool: ToolDef,
        args: Mapping[str, Any],
        error: Exception,
        context: ToolContext | None,
    ) -> None:
        for hook in self.failure_tool_use_hooks:
            maybe_awaitable = hook(tool, args, error, context)
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable

    async def execute_tool_use(
        self,
        tool_name: str,
        args: Mapping[str, Any],
        *,
        context: ToolContext | None = None,
        parent_message: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        tool = self.tools[tool_name]
        processed_args = args
        validate_schema(processed_args, tool.input_schema)
        tool.validate_input(processed_args)
        for hook in self.pre_tool_use_hooks:
            maybe_awaitable = hook(tool, processed_args, context)
            if inspect.isawaitable(maybe_awaitable):
                maybe_awaitable = await maybe_awaitable
            if isinstance(maybe_awaitable, Mapping):
                processed_args = maybe_awaitable

        decision = self.permission_engine.check(tool_name, is_destructive=tool.is_destructive())
        if decision.mode is PermissionMode.DENY:
            error = PermissionDeniedError(f"{tool_name} denied by {decision.source}")
            await self._run_failure_hooks(tool, processed_args, error, context)
            raise error
        if decision.mode is PermissionMode.ASK:
            if self.permission_ask_resolver is None:
                error = PermissionDeniedError(f"{tool_name} requires approval (source={decision.source})")
                await self._run_failure_hooks(tool, processed_args, error, context)
                raise error
            allow_result = self.permission_ask_resolver(tool, processed_args, decision, context)
            if inspect.isawaitable(allow_result):
                allow_result = await allow_result
            if not bool(allow_result):
                error = PermissionDeniedError(
                    f"{tool_name} approval rejected (source={decision.source})"
                )
                await self._run_failure_hooks(tool, processed_args, error, context)
                raise error

        progress_events: list[dict[str, Any]] = []

        def on_progress(event: dict[str, Any]) -> None:
            progress_events.append(event)

        try:
            raw_result = tool.call(processed_args, context, lambda _: True, parent_message, on_progress)
            if inspect.isawaitable(raw_result):
                raw_result = await raw_result
        except ToolInterruptedError as exc:
            await self._run_failure_hooks(tool, processed_args, exc, context)
            raise
        except Exception as exc:  # pragma: no cover - explicit error mapping path
            await self._run_failure_hooks(tool, processed_args, exc, context)
            raise ToolExecutionError(str(exc)) from exc

        try:
            for hook in self.post_tool_use_hooks:
                maybe_awaitable = hook(tool, processed_args, raw_result, context)
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable
        except Exception as exc:  # pragma: no cover - post hook failure path
            await self._run_failure_hooks(tool, processed_args, exc, context)
            raise ToolExecutionError(str(exc)) from exc

        mapped = tool.map_tool_result_to_tool_result_block_param(raw_result)
        return {
            "tool_name": tool_name,
            "raw_result": raw_result,
            "tool_result": mapped,
            "progress_events": progress_events,
        }

    async def execute_many(
        self,
        tool_uses: list[tuple[str, Mapping[str, Any]]],
        *,
        context: ToolContext | None = None,
    ) -> list[dict[str, Any]]:
        if all(self.tools[name].is_concurrency_safe() for name, _ in tool_uses):
            tasks: list[Awaitable[dict[str, Any]]] = [
                self.execute_tool_use(name, args, context=context) for name, args in tool_uses
            ]
            return list(await asyncio.gather(*tasks))

        results: list[dict[str, Any]] = []
        for name, args in tool_uses:
            results.append(await self.execute_tool_use(name, args, context=context))
        return results
