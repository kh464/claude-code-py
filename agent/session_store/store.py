from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agent.messages import normalize_tool_messages


class SessionStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.transcript_dir = self.root / "transcripts"
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "tasks.sqlite3"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS task_state (task_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            conn.commit()

    def _session_path(self, session_id: str) -> Path:
        return self.transcript_dir / f"{session_id}.jsonl"

    def append_event(self, session_id: str, event: dict[str, Any]) -> None:
        path = self._session_path(session_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        self.append_event(session_id, {"event": "message", "message": message})

    def load_events(self, session_id: str) -> list[dict[str, Any]]:
        path = self._session_path(session_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def load_transcript(self, session_id: str, *, normalize: bool = True) -> list[dict[str, Any]]:
        events = self.load_events(session_id)
        messages: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            message = event.get("message")
            if isinstance(message, dict):
                messages.append(dict(message))
        if normalize:
            return normalize_tool_messages(messages)
        return messages

    def save_task_state(self, task_id: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO task_state (task_id, payload) VALUES (?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload",
                (task_id, json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()

    def load_task_state(self, task_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT payload FROM task_state WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return {}
        return json.loads(row[0])

    def load_all_task_states(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT payload FROM task_state").fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            if not row:
                continue
            try:
                payload = json.loads(row[0])
            except Exception:
                continue
            if isinstance(payload, dict):
                results.append(payload)
        return results
