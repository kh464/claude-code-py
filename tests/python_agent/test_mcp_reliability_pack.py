from __future__ import annotations

import pytest

from agent.mcp_integration.transport import classify_transport_error, invoke_with_retry, MCPRequest


def test_mcp_retry_stops_on_non_retryable_classification() -> None:
    attempts = 0

    def bad_request():
        nonlocal attempts
        attempts += 1
        raise ValueError("bad request: malformed payload")

    with pytest.raises(ValueError):
        invoke_with_retry(
            request=MCPRequest(server="x", tool="y", arguments={}),
            invoker=bad_request,
            max_attempts=5,
            base_delay_s=0.01,
            sleep_fn=lambda _delay: None,
        )
    assert attempts == 1


def test_classify_transport_error_marks_timeouts_retryable() -> None:
    retryable, category = classify_transport_error(TimeoutError("timed out"))
    assert retryable is True
    assert category == "timeout"
