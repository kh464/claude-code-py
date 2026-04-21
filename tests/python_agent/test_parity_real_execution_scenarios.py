from __future__ import annotations

from agent.parity.scenarios import (
    REAL_SCENARIO_RUNNERS,
    SCENARIOS,
    _MISSING_EXPLICIT_SCENARIOS,
    execute_scenario,
)


def test_parity_real_scenario_runs_real_execution_checks() -> None:
    result = execute_scenario("single_file_fix")
    assert result["scenario"] == "single_file_fix"
    assert result["status"] in {"passed", "failed"}
    assert "checks" in result
    assert isinstance(result["checks"], list)
    assert "score" in result


def test_parity_rename_symbol_multi_file_runs_real_execution() -> None:
    result = execute_scenario("rename_symbol_multi_file")
    assert result["status"] in {"passed", "failed"}
    assert "not yet implemented with real execution runner" not in result["reason"]
    assert isinstance(result["checks"], list)
    assert result["checks"]


def test_all_parity_scenarios_have_real_runners() -> None:
    assert set(SCENARIOS).issubset(set(REAL_SCENARIO_RUNNERS))
    assert _MISSING_EXPLICIT_SCENARIOS == []
    for scenario in SCENARIOS:
        result = execute_scenario(scenario)
        assert "not yet implemented with real execution runner" not in result["reason"]
        assert isinstance(result.get("checks"), list)
        assert result["checks"]
