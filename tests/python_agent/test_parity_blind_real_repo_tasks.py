from __future__ import annotations

from agent.parity.harness import run_parity_suite
from agent.parity.scenarios import (
    BLIND_REAL_REPO_TASK_SCENARIOS,
    _BLIND_REAL_REPO_TASK_SCENARIO_SPECS,
    execute_scenario,
)


def test_parity_blind_real_repo_inventory_and_schema() -> None:
    required = {
        "workspace_template",
        "task_prompt",
        "verification_commands",
        "expected_artifacts",
        "scoring_weights",
        "blind_source_path",
        "blind_source_digest",
    }
    assert len(BLIND_REAL_REPO_TASK_SCENARIOS) >= 12
    for name in BLIND_REAL_REPO_TASK_SCENARIOS:
        spec = _BLIND_REAL_REPO_TASK_SCENARIO_SPECS[name]
        assert required.issubset(set(spec.keys()))
        assert str(spec["blind_source_path"]).strip()
        assert str(spec["blind_source_digest"]).strip()
        assert "[BLIND]" in str(spec["task_prompt"])


def test_parity_blind_real_repo_scenario_executes_with_quality_metrics() -> None:
    result = execute_scenario(BLIND_REAL_REPO_TASK_SCENARIOS[0])
    assert result["status"] in {"passed", "failed"}
    assert "verification" in result
    assert "quality_metrics" in result
    quality = result["quality_metrics"]
    assert "decision_quality_score" in quality
    assert "edit_correctness_score" in quality
    assert "verification_pass_rate" in quality


def test_parity_blind_real_repo_suite_quality_target() -> None:
    report = run_parity_suite(BLIND_REAL_REPO_TASK_SCENARIOS[:3])
    assert report["total"] == 3
    assert report["quality_metrics"]["weighted_quality_score"] >= 0.90
