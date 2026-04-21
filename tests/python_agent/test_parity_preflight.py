from __future__ import annotations

import pytest

from agent.parity.harness import run_parity_suite
from agent.parity.preflight import run_parity_preflight


def test_preflight_reports_pass_when_all_checks_pass() -> None:
    report = run_parity_preflight(
        checks=[
            ("workspace_writable", lambda: (True, "ok")),
            ("python_executable", lambda: (True, "ok")),
        ]
    )
    assert report["status"] == "passed"
    assert report["failed"] == 0
    assert all(bool(item["passed"]) for item in report["checks"])


def test_preflight_reports_failed_when_any_check_fails() -> None:
    report = run_parity_preflight(
        checks=[
            ("workspace_writable", lambda: (True, "ok")),
            ("shell_exec", lambda: (False, "permission denied")),
        ]
    )
    assert report["status"] == "failed"
    assert report["failed"] == 1
    assert "shell_exec" in report["reason"]


def test_parity_suite_short_circuits_when_preflight_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agent.parity.harness.run_parity_preflight",
        lambda: {
            "status": "failed",
            "total": 1,
            "passed": 0,
            "failed": 1,
            "reason": "workspace_writable failed",
            "checks": [{"name": "workspace_writable", "passed": False, "detail": "denied"}],
        },
    )

    report = run_parity_suite(["single_file_fix"])
    assert report["total"] == 1
    assert report["failed"] == 1
    assert report["details"][0]["reason"].startswith("environment_blocked:")
    assert report["environment_failure_rate"] == 1.0
    assert report["preflight"]["status"] == "failed"
