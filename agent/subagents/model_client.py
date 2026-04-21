from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen


def _resolve_runtime_profile(metadata: dict[str, Any]) -> str:
    profile_raw = str(metadata.get("subagent_runtime_profile", os.getenv("PY_AGENT_PROFILE", ""))).strip().lower()
    if profile_raw in {"prod", "production"}:
        return "prod"
    if profile_raw in {"test", "testing"}:
        return "test"
    if os.getenv("PYTEST_CURRENT_TEST"):
        return "test"
    return "prod"


class SubagentModelClient:
    """Deterministic multi-turn model adapter used by SubagentExecutor.

    This keeps runtime behavior testable while allowing the executor to run
    real QueryLoop/tool-use rounds instead of a single echo turn.
    """

    def __init__(
        self,
        *,
        prompt: str,
        max_turns: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.prompt = prompt.strip()
        self.max_turns = max(1, int(max_turns))
        self._turn = 0
        self.metadata = dict(metadata or {})
        self._config = _ModelConfig.from_metadata(self.metadata)

    def _select_tool(self, tools: Sequence[str]) -> str | None:
        for candidate in ("BriefTool", "ToolSearchTool", "GlobTool", "GrepTool", "FileReadTool"):
            if candidate in tools:
                return candidate
        return None

    async def _generate_deterministic(self, messages, tools):
        _ = messages
        self._turn += 1
        selected_tool = self._select_tool(list(tools))
        prompt = self.prompt or ""
        is_plan = "You are the planning phase." in prompt
        is_review = "You are the reviewer phase." in prompt
        is_implement = "You are the implementation phase." in prompt
        is_autofix = "You are the autofix phase." in prompt

        if is_plan:
            return {
                "content": json.dumps(
                    {
                        "steps": ["analyze target files", "apply focused edits", "run verification"],
                        "risks": ["regression in adjacent modules"],
                        "verification_focus": ["targeted tests", "smoke checks"],
                    },
                    ensure_ascii=False,
                ),
                "tool_uses": [],
            }

        if is_review:
            return {
                "content": json.dumps(
                    {
                        "verdict": "pass",
                        "score": 90,
                        "blocking_issues": [],
                        "fix_plan": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_uses": [],
            }

        if is_implement or is_autofix:
            return {
                "content": f"Completed task: {self.prompt or 'subagent task'}",
                "tool_uses": [],
            }

        # First round performs one safe tool-use when possible.
        if self._turn == 1 and selected_tool == "BriefTool":
            return {
                "content": "Planning and preparing execution context.",
                "tool_uses": [
                    {
                        "id": "subagent-brief-1",
                        "name": "BriefTool",
                        "arguments": {"text": self.prompt or "subagent task"},
                    }
                ],
            }

        # Finalize after at least 2 assistant turns when a tool round occurred.
        return {
            "content": f"Completed task: {self.prompt or 'subagent task'}",
            "tool_uses": [],
        }

    @staticmethod
    def _stringify_message(message: Any) -> str:
        if not isinstance(message, dict):
            return str(message)
        role = str(message.get("role", "unknown"))
        content = message.get("content", "")
        if isinstance(content, str):
            text = content
        else:
            text = json.dumps(content, ensure_ascii=False)
        if role == "tool":
            name = str(message.get("name", "tool"))
            tool_use_id = str(message.get("tool_use_id", ""))
            return f"[tool_result name={name} id={tool_use_id}] {text}"
        return f"[{role}] {text}"

    @staticmethod
    def _extract_json_payload(text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if not stripped:
            return None
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            return loaded

        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.DOTALL)
        if fenced:
            try:
                loaded = json.loads(fenced.group(1))
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                return loaded

        object_match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if object_match:
            candidate = object_match.group(0)
            try:
                loaded = json.loads(candidate)
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                return loaded
        return None

    @staticmethod
    def _sanitize_tool_uses(raw_tool_uses: Any, available_tools: Sequence[str]) -> list[dict[str, Any]]:
        if not isinstance(raw_tool_uses, list):
            return []
        allowed = {str(name) for name in available_tools}
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(raw_tool_uses, start=1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name or name not in allowed:
                continue
            arguments_raw = item.get("arguments", {})
            arguments = dict(arguments_raw) if isinstance(arguments_raw, dict) else {}
            tool_id = str(item.get("id") or f"subagent-tool-{index}")
            normalized.append({"id": tool_id, "name": name, "arguments": arguments})
        return normalized

    async def _call_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._config.api_key:
            raise ValueError("Real model backend requires API key")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
        }
        if self._config.extra_headers:
            headers.update(self._config.extra_headers)

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        def _blocking_request() -> dict[str, Any]:
            request = Request(self._config.endpoint, data=body, headers=headers, method="POST")
            with urlopen(request, timeout=self._config.timeout_s) as response:
                raw = response.read()
            data = json.loads(raw.decode("utf-8", errors="ignore"))
            if not isinstance(data, dict):
                raise ValueError("Model response must be a JSON object")
            return data

        return await asyncio.to_thread(_blocking_request)

    async def _generate_real(self, messages: Sequence[Any], tools: Sequence[str]) -> dict[str, Any]:
        available_tools = [str(name) for name in tools]
        system_prompt = (
            "You are a coding subagent. Return strict JSON only.\n"
            "JSON schema: {\"content\": string, \"tool_uses\": [{\"id\": string, \"name\": string, \"arguments\": object}]}\n"
            "Use tool_uses only when you need tool results to proceed.\n"
            "Allowed tools: "
            + ", ".join(available_tools)
        )

        model_messages = [{"role": "system", "content": system_prompt}]
        transcript = [self._stringify_message(message) for message in messages]
        if transcript:
            model_messages.append({"role": "user", "content": "\n".join(transcript[-12:])})
        model_messages.append({"role": "user", "content": f"Task: {self.prompt or 'subagent task'}"})

        payload = {
            "model": self._config.model,
            "messages": model_messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        response = await self._call_chat_completion(payload)
        choices = response.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise ValueError("Model response missing choices")
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message", {})
        content_text = ""
        if isinstance(message, dict):
            content_raw = message.get("content", "")
            content_text = str(content_raw)
        payload_json = self._extract_json_payload(content_text)
        if payload_json is None:
            return {"content": content_text.strip() or "No model content returned.", "tool_uses": []}

        content = str(payload_json.get("content", "")).strip()
        tool_uses = self._sanitize_tool_uses(payload_json.get("tool_uses", []), available_tools)
        if not content:
            content = f"Completed task: {self.prompt or 'subagent task'}"
        return {"content": content, "tool_uses": tool_uses}

    async def generate(self, messages, tools):
        if self._config.enabled:
            try:
                return await self._generate_real(messages, tools)
            except Exception as exc:
                raise RuntimeError(f"real model backend failed: {type(exc).__name__}: {exc}") from exc
        return await self._generate_deterministic(messages, tools)


@dataclass(slots=True, frozen=True)
class _ModelConfig:
    enabled: bool
    endpoint: str
    model: str
    api_key: str | None
    timeout_s: int
    temperature: float
    max_tokens: int
    extra_headers: dict[str, str]
    runtime_profile: str

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> _ModelConfig:
        runtime_profile = _resolve_runtime_profile(metadata)
        is_code_change = bool(metadata.get("is_code_change"))
        api_key = str(metadata.get("subagent_model_api_key", "")).strip() or None
        api_key_env = str(metadata.get("subagent_model_api_key_env", "OPENAI_API_KEY")).strip() or "OPENAI_API_KEY"
        if api_key is None:
            api_key = os.getenv(api_key_env)
        explicit_allow_mock = metadata.get("subagent_allow_mock_backend")
        allow_mock_backend = bool(explicit_allow_mock) if explicit_allow_mock is not None else False
        if runtime_profile == "prod":
            allow_mock_backend = False
        if runtime_profile != "test" and allow_mock_backend:
            raise ValueError("mock model backend is only allowed in test profile")

        default_implicit_deterministic = allow_mock_backend
        if is_code_change:
            default_implicit_deterministic = False
        allow_implicit_deterministic = bool(
            metadata.get("subagent_allow_implicit_deterministic", default_implicit_deterministic)
        )

        backend = str(metadata.get("subagent_model_backend", "")).strip().lower()
        if backend in {"deterministic", "stub", "none", "disabled"}:
            if is_code_change:
                raise ValueError("mock model backend is disabled for code-change tasks")
            if runtime_profile == "prod":
                raise ValueError("mock model backend is disabled in production profile")
            if not allow_mock_backend:
                raise ValueError("mock model backend is disabled; configure a real backend")
        if not backend:
            if api_key:
                backend = "openai_chat"
            else:
                backend = "deterministic" if (allow_mock_backend and allow_implicit_deterministic) else "openai_chat"
        enabled = backend not in {"deterministic", "stub", "none", "disabled"}
        endpoint = str(
            metadata.get("subagent_model_endpoint", "https://api.openai.com/v1/chat/completions")
        ).strip()
        model = str(metadata.get("subagent_model", metadata.get("model", "gpt-4.1-mini"))).strip()
        timeout_s = int(metadata.get("subagent_model_timeout_s", 20))
        temperature = float(metadata.get("subagent_model_temperature", 0.1))
        max_tokens = int(metadata.get("subagent_model_max_tokens", 1200))

        headers_raw = metadata.get("subagent_model_headers", {})
        headers: dict[str, str] = {}
        if isinstance(headers_raw, dict):
            for key, value in headers_raw.items():
                key_str = str(key).strip()
                value_str = str(value).strip()
                if key_str and value_str:
                    headers[key_str] = value_str
        return cls(
            enabled=enabled,
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            timeout_s=max(1, timeout_s),
            temperature=temperature,
            max_tokens=max(128, max_tokens),
            extra_headers=headers,
            runtime_profile=runtime_profile,
        )
