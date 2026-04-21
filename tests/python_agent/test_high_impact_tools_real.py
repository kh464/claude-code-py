from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"high-impact-tools-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "session")]),
    )


@pytest.mark.asyncio
async def test_web_fetch_returns_content_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _build_runtime()

    class _FakeResponse:
        headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self) -> int:
            return 200

        def read(self, _size: int = -1) -> bytes:
            return b"<html><title>Example</title><body>ok</body></html>"

    monkeypatch.setattr("agent.tools.web_fetch_tool.urlopen", lambda *_args, **_kwargs: _FakeResponse())

    result = await runtime.execute_tool_use("WebFetchTool", {"url": "https://example.com"})
    payload = result["raw_result"]
    assert payload["status_code"] == 200
    assert "Example" in payload["content"]


@pytest.mark.asyncio
async def test_web_search_returns_structured_results(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _build_runtime()

    def fake_request(*, query: str, timeout_s: int) -> dict:
        _ = timeout_s
        return {
            "query": query,
            "results": [
                {"title": "Python Agent Design", "url": "https://example.com/a", "snippet": "A"},
                {"title": "Claude Code Notes", "url": "https://example.com/b", "snippet": "B"},
            ],
        }

    monkeypatch.setattr("agent.tools.web_search_tool.perform_search_request", fake_request)

    result = await runtime.execute_tool_use("WebSearchTool", {"query": "python agent"})
    payload = result["raw_result"]
    assert payload["query"] == "python agent"
    assert len(payload["results"]) == 2
    assert payload["results"][0]["title"] == "Python Agent Design"


@pytest.mark.asyncio
async def test_notebook_edit_updates_target_cell() -> None:
    temp_root = _create_temp_dir()
    try:
        runtime = _build_runtime()
        notebook_path = temp_root / "sample.ipynb"
        notebook = {
            "cells": [
                {"cell_type": "code", "source": ["print('a')\n"], "metadata": {}, "outputs": [], "execution_count": None},
                {"cell_type": "markdown", "source": ["# title\n"], "metadata": {}},
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        notebook_path.write_text(json.dumps(notebook), encoding="utf-8")

        result = await runtime.execute_tool_use(
            "NotebookEditTool",
            {
                "path": str(notebook_path),
                "cell_index": 0,
                "new_source": "print('b')\n",
            },
        )
        payload = result["raw_result"]
        assert payload["updated"] is True
        updated_notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        assert updated_notebook["cells"][0]["source"] == ["print('b')\n"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
