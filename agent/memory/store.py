from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MemoryEntry:
    key: str
    value: str
    updated_at: float


class MemoryStore:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self.file_path = Path(file_path).expanduser().resolve() if file_path is not None else None
        self._entries: dict[str, MemoryEntry] = {}
        if self.file_path is not None:
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        if self.file_path is None or not self.file_path.exists():
            return
        for line in self.file_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            key = str(payload["key"])
            value = str(payload["value"])
            updated_at = float(payload.get("updated_at", time.time()))
            self._entries[key] = MemoryEntry(key=key, value=value, updated_at=updated_at)

    def _persist(self) -> None:
        if self.file_path is None:
            return
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for entry in sorted(self._entries.values(), key=lambda item: item.updated_at):
            lines.append(
                json.dumps(
                    {
                        "key": entry.key,
                        "value": entry.value,
                        "updated_at": entry.updated_at,
                    },
                    ensure_ascii=False,
                )
            )
        self.file_path.write_text("\n".join(lines), encoding="utf-8")

    def upsert(self, key: str, value: str) -> None:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("key must not be empty")
        entry = MemoryEntry(key=normalized_key, value=str(value), updated_at=time.time())
        self._entries[normalized_key] = entry
        self._persist()

    def list_entries(self) -> list[dict[str, Any]]:
        return [
            {
                "key": entry.key,
                "value": entry.value,
                "updated_at": entry.updated_at,
            }
            for entry in sorted(self._entries.values(), key=lambda item: item.updated_at, reverse=True)
        ]
