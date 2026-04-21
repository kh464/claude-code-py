from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from agent.parity.harness import run_parity_suite
from agent.parity.scenarios import REAL_REPO_TASK_SCENARIOS, SCENARIOS


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"parity-e2e-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_parity_e2e_generates_report_artifact() -> None:
    temp_root = _create_temp_dir()
    try:
        report_path = temp_root / "parity-report.json"
        result = run_parity_suite(SCENARIOS, report_path=report_path)

        assert len(SCENARIOS) >= 50
        assert len(REAL_REPO_TASK_SCENARIOS) >= 20
        assert result["total"] == len(SCENARIOS)
        assert report_path.exists()

        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert "success_rate" in payload
        assert "quality_metrics" in payload
        assert "unresolved_gaps" in payload
        assert payload["total"] == len(SCENARIOS)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
