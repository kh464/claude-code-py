from __future__ import annotations

import asyncio
import json
import inspect
from collections.abc import Mapping
from typing import Any

from agent.context.compaction import compact_messages
from agent.contracts import ToolContext
from agent.memory.retrieval import memory_search
from agent.messages import normalize_tool_messages
from agent.session_store.store import SessionStore
from agent.tools.runtime import ToolRuntime


class QueryLoop:
    def __init__(
        self,
        *,
        model_client: Any,
        runtime: ToolRuntime,
        max_rounds: int = 10,
        session_store: SessionStore | None = None,
        session_id: str | None = None,
        default_context: ToolContext | None = None,
        max_context_tokens: int | None = None,
        max_context_chars: int | None = None,
        compaction_keep_last: int = 8,
    ) -> None:
        self.model_client = model_client
        self.runtime = runtime
        self.max_rounds = max_rounds
        self.session_store = session_store
        self.session_id = session_id
        self.default_context = default_context
        self.max_context_tokens = max_context_tokens
        self.max_context_chars = max_context_chars
        self.compaction_keep_last = max(1, int(compaction_keep_last))

    @staticmethod
    def _estimate_context_chars(messages: list[dict[str, Any]]) -> int:
        total = 0
        for message in messages:
            try:
                total += len(json.dumps(message, ensure_ascii=False))
            except Exception:
                total += len(str(message))
        return total

    def _inject_memory_messages(
        self,
        transcript: list[dict[str, Any]],
        *,
        context: ToolContext | None,
    ) -> list[dict[str, Any]]:
        metadata = context.metadata if context is not None else {}
        memory_blocks = metadata.get("memory_injections")
        lines: list[str] = []
        if isinstance(memory_blocks, list):
            lines.extend(f"- {str(block)}" for block in memory_blocks if str(block).strip())

        memory_store = metadata.get("memory_store")
        if memory_store is not None and hasattr(memory_store, "list_entries"):
            query = str(metadata.get("memory_query", "")).strip()
            if not query:
                for message in reversed(transcript):
                    if message.get("role") == "user":
                        query = str(message.get("content", "")).strip()
                        break
            if query:
                top_k = int(metadata.get("memory_top_k", 3))
                retrieved = memory_search(store=memory_store, query=query, top_k=top_k)
                lines.extend(
                    f"- {item['key']}: {item['value']} (score={item['score']:.2f})"
                    for item in retrieved
                )

        if not lines:
            return transcript

        if any(
            message.get("role") == "system" and "[memory]" in str(message.get("content", ""))
            for message in transcript
            if isinstance(message, Mapping)
        ):
            return transcript

        memory_message = {"role": "system", "content": "[memory]\n" + "\n".join(lines)}
        return [memory_message, *transcript]

    def _compact_if_needed(self, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.max_context_tokens is not None and self.max_context_tokens > 0:
            return compact_messages(
                transcript,
                max_tokens=self.max_context_tokens,
                compaction_keep_last=self.compaction_keep_last,
            )

        if self.max_context_chars is None or self.max_context_chars <= 0:
            return transcript
        estimated = self._estimate_context_chars(transcript)
        if estimated <= self.max_context_chars:
            return transcript

        pinned_memory = [
            message
            for message in transcript
            if isinstance(message, Mapping)
            and message.get("role") == "system"
            and "[memory]" in str(message.get("content", ""))
        ]
        pinned_ids = {id(message) for message in pinned_memory}
        non_pinned = [message for message in transcript if id(message) not in pinned_ids]

        keep = min(self.compaction_keep_last, len(non_pinned))
        removed_count = max(0, len(transcript) - len(pinned_memory) - keep)
        compacted_tail = non_pinned[-keep:] if keep > 0 else []
        compacted_head = {
            "role": "system",
            "content": f"[compacted] removed {removed_count} messages to fit context budget",
        }
        compacted = [*pinned_memory, compacted_head, *compacted_tail]

        removable_indices = [
            index
            for index, message in enumerate(compacted)
            if not (
                isinstance(message, Mapping)
                and message.get("role") == "system"
                and ("[memory]" in str(message.get("content", "")) or "[compacted]" in str(message.get("content", "")))
            )
        ]
        while self._estimate_context_chars(compacted) > self.max_context_chars and removable_indices:
            remove_index = removable_indices.pop(0)
            compacted.pop(remove_index)
            removable_indices = [
                idx - 1 if idx > remove_index else idx for idx in removable_indices if idx != remove_index
            ]
            compacted_head["content"] = (
                f"[compacted] removed additional history to fit context budget (now {len(compacted) - 1} kept)"
            )
        if self._estimate_context_chars(compacted) > self.max_context_chars:
            for message in compacted:
                if (
                    isinstance(message, Mapping)
                    and message.get("role") == "system"
                    and "[memory]" in str(message.get("content", ""))
                ):
                    message["content"] = "[memory]\n- compacted memory summary"
                    break
        return compacted

    def _append_message(
        self,
        transcript: list[dict[str, Any]],
        message: dict[str, Any],
        *,
        session_id: str | None,
    ) -> None:
        transcript.append(message)
        if self.session_store is not None and session_id:
            self.session_store.append_message(session_id, message)

    def _normalize_tool_uses(
        self,
        tool_uses: list[Mapping[str, Any]],
        *,
        round_index: int,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for tool_use_index, tool_use in enumerate(tool_uses):
            if not isinstance(tool_use, Mapping):
                continue
            name = str(tool_use.get("name", "")).strip()
            if not name:
                continue
            tool_use_id = str(tool_use.get("id") or f"tooluse-{round_index + 1}-{tool_use_index + 1}")
            arguments_raw = tool_use.get("arguments", {})
            arguments = dict(arguments_raw) if isinstance(arguments_raw, Mapping) else {}
            normalized.append(
                {
                    "id": tool_use_id,
                    "name": name,
                    "arguments": arguments,
                }
            )
        return normalized

    @staticmethod
    def _error_message_from_exception(*, tool_name: str, exc: Exception) -> str:
        if isinstance(exc, KeyError):
            return f"Unknown tool: {tool_name}"
        message = str(exc).strip()
        if message:
            return message
        return f"{type(exc).__name__} while executing {tool_name}"

    async def _execute_tool_uses(
        self,
        *,
        tool_uses: list[dict[str, Any]],
        context: ToolContext | None,
        parent_message: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not tool_uses:
            return []

        all_known = all(tool_use["name"] in self.runtime.tools for tool_use in tool_uses)
        all_concurrency_safe = all(
            self.runtime.tools[tool_use["name"]].is_concurrency_safe() for tool_use in tool_uses if tool_use["name"] in self.runtime.tools
        )

        results: list[dict[str, Any]] = []
        if all_known and all_concurrency_safe and len(tool_uses) > 1:
            tasks = [
                self.runtime.execute_tool_use(
                    tool_use["name"],
                    tool_use["arguments"],
                    context=context,
                    parent_message=parent_message,
                )
                for tool_use in tool_uses
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            for tool_use, raw_result in zip(tool_uses, raw_results, strict=False):
                if isinstance(raw_result, Exception):
                    results.append(
                        {
                            "role": "tool",
                            "name": tool_use["name"],
                            "tool_use_id": tool_use["id"],
                            "is_error": True,
                            "content": {
                                "status": "error",
                                "content": self._error_message_from_exception(
                                    tool_name=tool_use["name"],
                                    exc=raw_result,
                                ),
                            },
                        }
                    )
                else:
                    results.append(
                        {
                            "role": "tool",
                            "name": tool_use["name"],
                            "tool_use_id": tool_use["id"],
                            "content": raw_result["tool_result"],
                        }
                    )
            return results

        for tool_use in tool_uses:
            try:
                execution = await self.runtime.execute_tool_use(
                    tool_use["name"],
                    tool_use["arguments"],
                    context=context,
                    parent_message=parent_message,
                )
                results.append(
                    {
                        "role": "tool",
                        "name": tool_use["name"],
                        "tool_use_id": tool_use["id"],
                        "content": execution["tool_result"],
                    }
                )
            except Exception as exc:  # pragma: no cover - explicit per-tool fallback path
                results.append(
                    {
                        "role": "tool",
                        "name": tool_use["name"],
                        "tool_use_id": tool_use["id"],
                        "is_error": True,
                        "content": {
                            "status": "error",
                            "content": self._error_message_from_exception(tool_name=tool_use["name"], exc=exc),
                        },
                    }
                )
        return results

    async def run(
        self,
        initial_messages: list[dict[str, Any]],
        *,
        context: ToolContext | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        effective_context = context if context is not None else self.default_context
        effective_session_id = session_id if session_id is not None else self.session_id

        transcript = normalize_tool_messages([dict(message) for message in initial_messages])
        transcript = self._inject_memory_messages(transcript, context=effective_context)
        for round_index in range(self.max_rounds):
            transcript = self._compact_if_needed(transcript)
            tool_names = list(self.runtime.tools.keys())
            response = self.model_client.generate(normalize_tool_messages(transcript), tool_names)
            if inspect.isawaitable(response):
                response = await response
            if not isinstance(response, Mapping):
                raise ValueError("model_client.generate must return a mapping")

            content = str(response.get("content", ""))
            raw_tool_uses = response.get("tool_uses", [])
            parsed_tool_uses = raw_tool_uses if isinstance(raw_tool_uses, list) else []
            normalized_tool_uses = self._normalize_tool_uses(parsed_tool_uses, round_index=round_index)

            assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
            if normalized_tool_uses:
                assistant_message["tool_uses"] = normalized_tool_uses
            self._append_message(transcript, assistant_message, session_id=effective_session_id)

            if not normalized_tool_uses:
                break

            tool_messages = await self._execute_tool_uses(
                tool_uses=normalized_tool_uses,
                context=effective_context,
                parent_message=assistant_message,
            )
            for tool_message in tool_messages:
                self._append_message(transcript, tool_message, session_id=effective_session_id)

        return normalize_tool_messages(transcript)
