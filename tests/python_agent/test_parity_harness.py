from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from agent.parity.harness import run_parity_suite


def test_parity_harness_reports_scores() -> None:
    result = run_parity_suite(["simple-edit"])

    assert "success_rate" in result
    assert "quality_metrics" in result
    assert "decision_quality_score" in result["quality_metrics"]
    assert "edit_correctness_score" in result["quality_metrics"]
    assert "verification_pass_rate" in result["quality_metrics"]
    assert result["total"] >= 1


def test_parity_harness_persists_artifact_by_default() -> None:
    with tempfile.TemporaryDirectory(prefix="parity-artifacts-") as temp_dir:
        previous = os.environ.get("PY_AGENT_PARITY_ARTIFACT_DIR")
        os.environ["PY_AGENT_PARITY_ARTIFACT_DIR"] = temp_dir
        try:
            result = run_parity_suite(["simple-edit"], enforce_preflight=False)
        finally:
            if previous is None:
                os.environ.pop("PY_AGENT_PARITY_ARTIFACT_DIR", None)
            else:
                os.environ["PY_AGENT_PARITY_ARTIFACT_DIR"] = previous
        artifact_path = Path(str(result["artifact_path"])).resolve()
        assert artifact_path.exists()
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert payload["total"] == 1
        assert payload["details"][0]["scenario"] == "simple-edit"


def test_parity_harness_can_disable_artifact_persistence() -> None:
    with tempfile.TemporaryDirectory(prefix="parity-artifacts-") as temp_dir:
        previous = os.environ.get("PY_AGENT_PARITY_ARTIFACT_DIR")
        os.environ["PY_AGENT_PARITY_ARTIFACT_DIR"] = temp_dir
        try:
            result = run_parity_suite(["simple-edit"], enforce_preflight=False, persist_artifact=False)
        finally:
            if previous is None:
                os.environ.pop("PY_AGENT_PARITY_ARTIFACT_DIR", None)
            else:
                os.environ["PY_AGENT_PARITY_ARTIFACT_DIR"] = previous
        assert "artifact_path" not in result
        assert list(Path(temp_dir).glob("*.json")) == []
