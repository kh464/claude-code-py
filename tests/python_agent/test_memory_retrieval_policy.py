from __future__ import annotations

import pytest

from agent.contracts import ToolContext
from agent.memory.retrieval import memory_search
from agent.memory.store import MemoryStore
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.query_loop import QueryLoop
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


class RecordingModel:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def generate(self, messages, tools):
        _ = tools
        self.calls.append([dict(message) for message in messages])
        return {"content": "done", "tool_uses": []}


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


def test_memory_retrieval_returns_high_relevance_entries() -> None:
    store = MemoryStore()
    store.upsert("auth-bug", "auth login bug around oauth callback")
    store.upsert("ui-theme", "button color palette and spacing")
    store.upsert("auth-test", "add auth regression test for token refresh bug")

    results = memory_search(store=store, query="auth bug", top_k=3)
    assert results
    assert results[0]["score"] >= results[-1]["score"]
    assert "auth" in results[0]["value"]


@pytest.mark.asyncio
async def test_query_loop_injects_topk_memory_from_store() -> None:
    store = MemoryStore()
    store.upsert("auth-1", "auth module had bug in token refresh")
    store.upsert("doc-1", "release notes for docs")
    store.upsert("auth-2", "oauth login issue and auth middleware fix")

    model = RecordingModel()
    loop = QueryLoop(model_client=model, runtime=_build_runtime())
    context = ToolContext(
        session_id="session-memory-store",
        metadata={
            "memory_store": store,
            "memory_top_k": 2,
        },
    )

    await loop.run([{"role": "user", "content": "please fix auth bug"}], context=context)
    assert model.calls
    first_call = model.calls[0]
    memory_messages = [
        msg for msg in first_call if msg.get("role") == "system" and "[memory]" in str(msg.get("content", ""))
    ]
    assert memory_messages
    memory_content = memory_messages[0]["content"]
    assert "auth-1" in memory_content or "auth-2" in memory_content
