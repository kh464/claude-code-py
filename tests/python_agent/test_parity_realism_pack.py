from __future__ import annotations

from agent.parity.harness import run_parity_suite
from agent.parity.scenarios import (
    BLIND_REAL_REPO_TASK_SCENARIOS,
    REAL_REPO_TASK_SCENARIOS,
    SCENARIOS,
    _EXPLICIT_PATCH_SCENARIO_SPECS,
)


def _template_fallback_ratio() -> float:
    patch_scenarios = [name for name in SCENARIOS if name not in {"implement_verification_gate", "worktree_cleanup_regression"}]
    if not patch_scenarios:
        return 0.0
    explicit = set(_EXPLICIT_PATCH_SCENARIO_SPECS.keys())
    template_count = sum(1 for name in patch_scenarios if name not in explicit)
    return float(template_count) / float(len(patch_scenarios))


def test_parity_realism_inventory_targets() -> None:
    assert len(SCENARIOS) >= 80
    assert len(REAL_REPO_TASK_SCENARIOS) >= 40
    assert len(BLIND_REAL_REPO_TASK_SCENARIOS) >= 12
    assert _template_fallback_ratio() <= 0.10


def test_parity_realism_weighted_quality_target() -> None:
    report = run_parity_suite(SCENARIOS)
    assert report["quality_metrics"]["weighted_quality_score"] >= 0.90
