from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _entry_key(entry: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(entry.get("symbol", "")),
        str(entry.get("path", "")),
        int(entry.get("line_number", 0)),
    )


@dataclass(slots=True)
class SemanticGraph:
    definitions: list[dict[str, Any]] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)

    def add_definitions(self, entries: list[dict[str, Any]]) -> None:
        self.definitions = self._merge(self.definitions, entries)

    def add_references(self, entries: list[dict[str, Any]]) -> None:
        self.references = self._merge(self.references, entries)

    @staticmethod
    def _merge(base: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[tuple[str, str, int], dict[str, Any]] = {}
        for entry in [*base, *incoming]:
            deduped[_entry_key(entry)] = dict(entry)
        merged = list(deduped.values())
        merged.sort(key=lambda item: (str(item.get("path", "")), int(item.get("line_number", 0))))
        return merged
