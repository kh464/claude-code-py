from __future__ import annotations

from agent.parity.report import build_parity_report


def test_parity_report_exposes_perfect_parity_contract_fields() -> None:
    report = build_parity_report(
        details=[
            {
                "scenario": "semantic_refactor_move_cross_file",
                "status": "passed",
                "score": 1.0,
                "checks": [
                    {"name": "glob_locate", "passed": True},
                    {"name": "edit_applied", "passed": True},
                    {"name": "verification_pytest", "passed": True},
                ],
            }
        ]
    )

    assert report["contract_version"] == "2026-04-18-perfect-parity-v1"
    assert "capability_matrix" in report
    assert "quality_dimension_matrix" in report
    assert "failure_taxonomy" in report

    capability_matrix = report["capability_matrix"]
    required_capabilities = {
        "tooling",
        "orchestration",
        "recovery",
        "verification",
        "subagent",
        "semantic_navigation",
        "semantic_refactor",
        "mcp",
    }
    assert required_capabilities.issubset(set(capability_matrix.keys()))
    for item in required_capabilities:
        payload = capability_matrix[item]
        assert "covered" in payload
        assert "passed" in payload
        assert "failed" in payload
        assert "success_rate" in payload

    quality_matrix = report["quality_dimension_matrix"]
    assert set(quality_matrix.keys()) == {
        "decision_quality",
        "edit_correctness",
        "verification",
        "weighted_quality",
    }
    for payload in quality_matrix.values():
        assert "score" in payload
        assert "threshold" in payload
        assert "passed" in payload


def test_parity_report_failure_taxonomy_covers_required_categories() -> None:
    report = build_parity_report(
        details=[
            {"scenario": "s-model", "status": "failed", "score": 0.0, "reason": "model backend timeout"},
            {"scenario": "s-tool", "status": "failed", "score": 0.0, "reason": "tool call failed: file_edit stale"},
            {"scenario": "s-orch", "status": "failed", "score": 0.0, "reason": "planner protocol invalid"},
            {"scenario": "s-semantic", "status": "failed", "score": 0.0, "reason": "semantic rename mismatch"},
            {"scenario": "s-verify", "status": "failed", "score": 0.0, "reason": "verification command failed: pytest"},
            {
                "scenario": "s-env",
                "status": "failed",
                "score": 0.0,
                "reason": "scenario execution error: [WinError 5] access denied",
            },
        ]
    )

    taxonomy = report["failure_taxonomy"]
    assert taxonomy["model"] == 1
    assert taxonomy["tool"] == 1
    assert taxonomy["orchestration"] == 1
    assert taxonomy["semantic"] == 1
    assert taxonomy["verification"] == 1
    assert taxonomy["environment"] == 1

    failed_details = [item for item in report["details"] if item["status"] == "failed"]
    assert failed_details
    assert all("failure_taxonomy_category" in item for item in failed_details)
