from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def must_verify(*, prompt: str, metadata: Mapping[str, Any] | None = None) -> bool:
    _ = prompt
    data = metadata or {}
    return bool(data.get("is_code_change") or data.get("require_verification"))
