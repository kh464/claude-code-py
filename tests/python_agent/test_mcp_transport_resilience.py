from __future__ import annotations

from typing import Any

import pytest

from agent.mcp_integration.manager import MCPManager
from agent.mcp_integration.transport import MCPRequest, invoke_with_retry


def test_mcp_retries_transient_errors_with_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    def fake_sleep(delay_s: float) -> None:
        delays.append(delay_s)

    def flaky_invoker() -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient: timeout")
        return {"ok": True}

    result = invoke_with_retry(
        request=MCPRequest(server="demo", tool="ping", arguments={"x": 1}),
        invoker=flaky_invoker,
        max_attempts=4,
        base_delay_s=0.01,
        sleep_fn=fake_sleep,
    )
    assert result["ok"] is True
    assert result["attempts"] == 3
    assert delays == [0.01, 0.02]


def test_mcp_retries_are_exposed_through_manager_invoke() -> None:
    manager = MCPManager()
    manager.register_server(
        "ops",
        tools={"ping": {"mode": "echo", "transient_failures": 2, "allow_simulated": True}},
        resources={},
    )

    result = manager.invoke_tool("ops", "ping", {"value": "x"})
    assert result["server"] == "ops"
    assert result["tool"] == "ping"
    assert result["arguments"]["value"] == "x"
    assert result["attempts"] >= 3


def test_mcp_non_transient_errors_do_not_retry() -> None:
    def permanent_invoker() -> dict[str, Any]:
        raise ValueError("permanent: bad request")

    with pytest.raises(ValueError, match="bad request"):
        invoke_with_retry(
            request=MCPRequest(server="demo", tool="ping", arguments={}),
            invoker=permanent_invoker,
            max_attempts=3,
            base_delay_s=0.01,
            sleep_fn=lambda _delay: None,
        )
