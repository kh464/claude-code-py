from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from agent.parity.harness import run_parity_suite


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"parity-real-runner-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_parity_runner_executes_scenarios_and_emits_report() -> None:
    temp_root = _create_temp_dir()
    try:
        report_path = temp_root / "report.json"
        report = run_parity_suite(["single_file_fix"], report_path=report_path)

        assert report["total"] == 1
        assert report["details"][0]["status"] in {"passed", "failed"}
        assert "duration_ms" in report["details"][0]
        assert report_path.exists()

        payload = json.loads(report_path.read_text(encoding="utf-8"))
        assert payload["details"][0]["scenario"] == "single_file_fix"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
