from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .preflight import run_parity_preflight
from .report import build_parity_report
from .runner import ParityRunner


def _persist_report(*, report: dict, report_path: str | Path | None) -> dict:
    if report_path is not None:
        path = Path(report_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(path)
    return report


def _default_artifact_path() -> Path:
    artifact_dir_raw = os.environ.get("PY_AGENT_PARITY_ARTIFACT_DIR", "").strip()
    artifact_dir = Path(artifact_dir_raw).expanduser().resolve() if artifact_dir_raw else Path("artifacts/parity").resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (artifact_dir / f"parity-report-{stamp}-{uuid.uuid4().hex[:8]}.json").resolve()


def run_parity_suite(
    scenarios: list[str],
    *,
    report_path: str | Path | None = None,
    persist_artifact: bool = True,
    enforce_preflight: bool = True,
) -> dict:
    artifact_path = _default_artifact_path() if persist_artifact and report_path is None else None
    persist_path = report_path if report_path is not None else artifact_path
    preflight = run_parity_preflight() if enforce_preflight else {"status": "passed", "checks": [], "reason": "skipped"}
    if str(preflight.get("status", "failed")).lower() != "passed":
        details = [
            {
                "scenario": str(scenario),
                "status": "failed",
                "reason": f"environment_blocked: {preflight.get('reason', 'preflight failed')}",
                "score": 0.0,
                "duration_ms": 0.0,
                "checks": [{"name": "preflight_gate", "passed": False}],
                "verification": {
                    "status": "skipped",
                    "workdir": "",
                    "results": [],
                    "reason": "environment_blocked",
                },
            }
            for scenario in scenarios
        ]
        report = build_parity_report(details=details)
        report["preflight"] = preflight
        persisted = _persist_report(report=report, report_path=persist_path)
        if artifact_path is not None:
            persisted["artifact_path"] = str(artifact_path)
        return persisted

    runner = ParityRunner()
    details = [runner.execute(scenario) for scenario in scenarios]
    report = build_parity_report(details=details)
    report["preflight"] = preflight
    persisted = _persist_report(report=report, report_path=persist_path)
    if artifact_path is not None:
        persisted["artifact_path"] = str(artifact_path)
    return persisted
