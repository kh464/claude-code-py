from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .scenarios import execute_scenario


class ParityRunner:
    def __init__(self, *, scenario_executor: Callable[[str], dict[str, Any]] | None = None) -> None:
        self.scenario_executor = scenario_executor or execute_scenario

    def execute(self, scenario: str) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = dict(self.scenario_executor(scenario))
            status = str(result.get("status", "failed"))
            reason = str(result.get("reason", "unknown"))
        except Exception as exc:
            status = "failed"
            reason = f"runner error: {exc}"
            result = {"scenario": str(scenario)}
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        return {
            **result,
            "scenario": str(result.get("scenario", scenario)),
            "status": status,
            "reason": reason,
            "duration_ms": duration_ms,
        }
