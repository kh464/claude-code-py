from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MCPRequest:
    server: str
    tool: str
    arguments: dict[str, Any]


def classify_transport_error(error: Exception) -> tuple[bool, str]:
    if isinstance(error, TimeoutError):
        return True, "timeout"
    message = str(error).lower()
    if "bad request" in message or "malformed" in message or "invalid" in message:
        return False, "bad_request"
    if "permanent" in message:
        return False, "permanent"
    transient_markers = (
        "transient",
        "timeout",
        "temporarily",
        "connection reset",
        "unavailable",
    )
    if any(marker in message for marker in transient_markers):
        return True, "transient"
    return False, "unknown"


def invoke_with_retry(
    *,
    request: MCPRequest,
    invoker: Callable[[], Mapping[str, Any]],
    max_attempts: int = 3,
    base_delay_s: float = 0.05,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    attempt = 0
    while True:
        attempt += 1
        try:
            payload = dict(invoker())
            payload["attempts"] = attempt
            payload["retry_count"] = max(0, attempt - 1)
            return payload
        except Exception as exc:
            retryable, category = classify_transport_error(exc)
            should_retry = retryable and attempt < max_attempts
            if not should_retry:
                raise
            delay_s = base_delay_s * (2 ** (attempt - 1))
            sleep_fn(delay_s)
