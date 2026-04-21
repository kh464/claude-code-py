from __future__ import annotations

from agent.parity.report import build_parity_report
from agent.parity.scenarios import _error_result, _quality_from_checks


def test_quality_defaults_do_not_award_missing_dimensions() -> None:
    quality = _quality_from_checks(
        checks=[{"name": "edit_applied", "passed": True}],
        verification=None,
    )
    assert quality["edit_correctness_score"] == 1.0
    assert quality["decision_quality_score"] == 0.0
    assert quality["verification_pass_rate"] == 0.0


def test_error_result_does_not_inflate_missing_dimensions() -> None:
    payload = _error_result(
        scenario="single_file_fix",
        reason="scenario execution error: [WinError 5] access denied",
    )
    quality = payload["quality_metrics"]
    assert quality["edit_correctness_score"] == 0.0
    assert quality["decision_quality_score"] == 0.0
    assert quality["verification_pass_rate"] == 0.0


def test_parity_report_includes_failure_bucket_rates() -> None:
    report = build_parity_report(
        details=[
            {
                "scenario": "s1",
                "status": "failed",
                "reason": "scenario execution error: [WinError 5] access denied",
                "score": 0.0,
                "checks": [{"name": "scenario_execution", "passed": False}],
            },
            {
                "scenario": "s2",
                "status": "failed",
                "reason": "planner protocol invalid",
                "score": 0.0,
                "checks": [{"name": "planner_contract", "passed": False}],
            },
        ]
    )
    assert report["total"] == 2
    assert report["environment_failure_rate"] == 0.5
    assert report["capability_failure_rate"] == 0.5
    assert report["failure_breakdown"]["environment"] == 1
    assert report["failure_breakdown"]["capability"] == 1
