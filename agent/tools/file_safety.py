from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256


class MissingReadError(ValueError):
    pass


class StaleReadError(ValueError):
    pass


class NonUniqueMatchError(ValueError):
    pass


def _digest(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


@dataclass
class FileReadStateCache:
    _snapshots: dict[str, str] = field(default_factory=dict)

    def record_read(self, path: str, content: str) -> None:
        self._snapshots[path] = _digest(content)

    def ensure_can_edit(
        self,
        path: str,
        current_content: str,
        old_string: str,
        *,
        replace_all: bool = False,
    ) -> None:
        if path not in self._snapshots:
            raise MissingReadError("Must read file before editing")
        if self._snapshots[path] != _digest(current_content):
            raise StaleReadError("File changed since last read")
        occurrences = current_content.count(old_string)
        if occurrences == 0:
            raise NonUniqueMatchError("old_string not found in current content")
        if occurrences > 1 and not replace_all:
            raise NonUniqueMatchError("old_string is not unique; use replace_all")
