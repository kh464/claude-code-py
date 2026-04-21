from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from agent.session_store.store import SessionStore


def test_session_store_jsonl_roundtrip() -> None:
    temp_dir = Path("tests/.tmp-python-agent") / f"store-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        store = SessionStore(temp_dir)
        store.append_event("s1", {"event": "tool_use_started", "tool": "BashTool"})
        store.append_event("s1", {"event": "tool_result", "tool": "BashTool"})

        events = store.load_events("s1")
        assert [event["event"] for event in events] == ["tool_use_started", "tool_result"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_session_store_task_state_roundtrip() -> None:
    temp_dir = Path("tests/.tmp-python-agent") / f"store-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        store = SessionStore(temp_dir)
        store.save_task_state("task-1", {"status": "running", "agent_id": "a1"})

        loaded = store.load_task_state("task-1")
        assert loaded["status"] == "running"
        assert loaded["agent_id"] == "a1"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_session_store_load_transcript_normalizes_pairs() -> None:
    temp_dir = Path("tests/.tmp-python-agent") / f"store-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        store = SessionStore(temp_dir)
        store.append_message(
            "s2",
            {
                "role": "assistant",
                "content": "use tools",
                "tool_uses": [{"id": "tu-1", "name": "FileReadTool", "arguments": {"path": "a.py"}}],
            },
        )
        transcript = store.load_transcript("s2")

        assert len(transcript) == 2
        assert transcript[0]["role"] == "assistant"
        assert transcript[1]["role"] == "tool"
        assert transcript[1]["tool_use_id"] == "tu-1"
        assert transcript[1]["is_error"] is True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
