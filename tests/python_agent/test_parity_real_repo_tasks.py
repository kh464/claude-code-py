from __future__ import annotations

from agent.parity.harness import run_parity_suite
from agent.parity.scenarios import (
    REAL_REPO_TASK_SCENARIOS,
    SCENARIOS,
    _REAL_REPO_TASK_SCENARIO_SPECS,
    execute_scenario,
)


def test_parity_real_repo_scenarios_have_required_schema_fields() -> None:
    required = {"workspace_template", "task_prompt", "verification_commands", "expected_artifacts", "scoring_weights"}
    assert len(REAL_REPO_TASK_SCENARIOS) >= 20
    for name in REAL_REPO_TASK_SCENARIOS:
        spec = _REAL_REPO_TASK_SCENARIO_SPECS[name]
        assert required.issubset(set(spec.keys()))
        assert isinstance(spec["verification_commands"], list)
        assert spec["verification_commands"]
        assert isinstance(spec["scoring_weights"], dict)


def test_parity_real_repo_scenario_runs_with_verification_and_quality_metrics() -> None:
    result = execute_scenario(REAL_REPO_TASK_SCENARIOS[0])
    assert result["status"] in {"passed", "failed"}
    assert "verification" in result
    assert "quality_metrics" in result
    quality = result["quality_metrics"]
    assert "decision_quality_score" in quality
    assert "edit_correctness_score" in quality
    assert "verification_pass_rate" in quality


def test_parity_real_repo_suite_report_exposes_quality_dimensions() -> None:
    report = run_parity_suite(REAL_REPO_TASK_SCENARIOS[:3])
    assert report["total"] == 3
    assert "quality_metrics" in report
    quality = report["quality_metrics"]
    assert "decision_quality_score" in quality
    assert "edit_correctness_score" in quality
    assert "verification_pass_rate" in quality
    for detail in report["details"]:
        assert "quality_metrics" in detail
        assert "verification" in detail


def test_parity_scenario_coverage_target_for_p0_2() -> None:
    assert len(SCENARIOS) >= 50
    assert len(REAL_REPO_TASK_SCENARIOS) >= 20
