from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_CONTRACT_VERSION = "2026-04-18-perfect-parity-v1"


def _safe_score(raw: Any, *, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return max(0.0, min(1.0, float(default)))
    return max(0.0, min(1.0, value))


def _classify_failure_reason(reason: str) -> str:
    text = str(reason or "").strip().lower()
    if any(
        token in text
        for token in (
            "winerror",
            "permission denied",
            "access denied",
            "read-only",
            "readonly",
            "operation not permitted",
            "environment_blocked",
        )
    ):
        return "environment"
    if any(
        token in text
        for token in (
            "runner error",
            "timeout",
            "interrupted",
            "task was destroyed",
            "runtime error",
        )
    ):
        return "runtime"
    return "capability"


def _classify_failure_taxonomy_reason(reason: str) -> str:
    text = str(reason or "").strip().lower()
    if any(
        token in text
        for token in (
            "winerror",
            "permission denied",
            "access denied",
            "read-only",
            "readonly",
            "operation not permitted",
            "environment_blocked",
        )
    ):
        return "environment"
    if any(token in text for token in ("model", "backend", "llm", "provider", "api key", "completion")):
        return "model"
    if any(
        token in text
        for token in (
            "verification",
            "verify",
            "pytest",
            "lint",
            "build failed",
            "test failed",
            "verification gate",
        )
    ):
        return "verification"
    if any(token in text for token in ("semantic", "rename", "refactor", "lsp", "definition", "reference")):
        return "semantic"
    if any(token in text for token in ("planner", "review", "autofix", "orchestr", "protocol", "quality gate")):
        return "orchestration"
    if any(
        token in text
        for token in ("tool", "file_edit", "file_read", "glob", "grep", "shell", "bash", "powershell", "mcp")
    ):
        return "tool"
    return "tool"


def _detail_text(detail: dict[str, Any]) -> str:
    scenario = str(detail.get("scenario", "")).strip().lower()
    reason = str(detail.get("reason", "")).strip().lower()
    checks = detail.get("checks", [])
    check_names: list[str] = []
    if isinstance(checks, list):
        for item in checks:
            if isinstance(item, dict):
                check_names.append(str(item.get("name", "")).strip().lower())
    return " ".join([scenario, reason, *check_names]).strip()


def _detail_capabilities(detail: dict[str, Any]) -> set[str]:
    text = _detail_text(detail)
    capability_tokens: dict[str, tuple[str, ...]] = {
        "tooling": ("tool", "file_", "glob", "grep", "bash", "powershell", "edit", "write", "read", "shell"),
        "orchestration": ("planner", "review", "autofix", "orchestr", "quality_gate", "plan_contract"),
        "recovery": ("resume", "recover", "restore", "retry", "reconnect", "interrupt", "rollback", "gc"),
        "verification": ("verification", "verify", "pytest", "lint", "build", "test", "gate"),
        "subagent": ("subagent", "agent_tool", "worktree", "spawn", "task_manager"),
        "semantic_navigation": ("definition", "reference", "diagnostic", "navigation", "find_diagnostics", "lsp"),
        "semantic_refactor": ("rename", "refactor", "move", "extract", "inline", "organize_imports"),
        "mcp": ("mcp", "transport", "resource", "server", "tool_sync"),
    }
    hits: set[str] = set()
    for capability, tokens in capability_tokens.items():
        if any(token in text for token in tokens):
            hits.add(capability)
    return hits


def _build_quality_dimension_matrix(quality_metrics: dict[str, float]) -> dict[str, dict[str, float | bool]]:
    thresholds = {
        "decision_quality": 0.90,
        "edit_correctness": 0.90,
        "verification": 0.90,
        "weighted_quality": 0.90,
    }
    scores = {
        "decision_quality": float(quality_metrics.get("decision_quality_score", 0.0)),
        "edit_correctness": float(quality_metrics.get("edit_correctness_score", 0.0)),
        "verification": float(quality_metrics.get("verification_pass_rate", 0.0)),
        "weighted_quality": float(quality_metrics.get("weighted_quality_score", 0.0)),
    }
    matrix: dict[str, dict[str, float | bool]] = {}
    for key, threshold in thresholds.items():
        score = max(0.0, min(1.0, scores.get(key, 0.0)))
        matrix[key] = {
            "score": round(score, 4),
            "threshold": threshold,
            "passed": bool(score >= threshold),
        }
    return matrix


def _build_capability_matrix(details: list[dict[str, Any]]) -> dict[str, dict[str, float | int | bool]]:
    base = {
        "tooling": {"covered": False, "passed": 0, "failed": 0},
        "orchestration": {"covered": False, "passed": 0, "failed": 0},
        "recovery": {"covered": False, "passed": 0, "failed": 0},
        "verification": {"covered": False, "passed": 0, "failed": 0},
        "subagent": {"covered": False, "passed": 0, "failed": 0},
        "semantic_navigation": {"covered": False, "passed": 0, "failed": 0},
        "semantic_refactor": {"covered": False, "passed": 0, "failed": 0},
        "mcp": {"covered": False, "passed": 0, "failed": 0},
    }
    for detail in details:
        status = str(detail.get("status", "")).strip().lower()
        passed = status == "passed"
        for capability in _detail_capabilities(detail):
            payload = base.get(capability)
            if payload is None:
                continue
            payload["covered"] = True
            if passed:
                payload["passed"] = int(payload["passed"]) + 1
            else:
                payload["failed"] = int(payload["failed"]) + 1
    matrix: dict[str, dict[str, float | int | bool]] = {}
    for capability, payload in base.items():
        passed = int(payload["passed"])
        failed = int(payload["failed"])
        total = passed + failed
        matrix[capability] = {
            "covered": bool(payload["covered"]),
            "passed": passed,
            "failed": failed,
            "success_rate": round(float(passed) / float(total), 4) if total else 0.0,
        }
    return matrix


def _derive_quality_dimensions(detail: dict[str, Any], *, base_score: float) -> tuple[float, float, float]:
    quality_raw = detail.get("quality_metrics", {})
    quality = quality_raw if isinstance(quality_raw, dict) else {}

    decision_raw = quality.get("decision_quality_score", detail.get("decision_quality_score"))
    edit_raw = quality.get("edit_correctness_score", detail.get("edit_correctness_score"))
    verification_raw = quality.get("verification_pass_rate", detail.get("verification_pass_rate"))

    decision: float | None = None
    edit: float | None = None
    verification: float | None = None
    if decision_raw is not None:
        decision = _safe_score(decision_raw, default=base_score)
    if edit_raw is not None:
        edit = _safe_score(edit_raw, default=base_score)
    if verification_raw is not None:
        verification = _safe_score(verification_raw, default=base_score)

    checks = detail.get("checks", [])
    if isinstance(checks, list) and checks:
        decision_checks = []
        verification_checks = []
        edit_checks = []
        for check in checks:
            if not isinstance(check, dict):
                continue
            name = str(check.get("name", "")).strip().lower()
            passed = bool(check.get("passed"))
            target = edit_checks
            if any(token in name for token in ("glob", "grep", "locate", "locat")):
                target = decision_checks
            elif any(token in name for token in ("verify", "verification", "gate", "test", "lint", "build")):
                target = verification_checks
            target.append(1.0 if passed else 0.0)

        if decision_checks:
            decision = round(sum(decision_checks) / len(decision_checks), 4)
        if edit_checks:
            edit = round(sum(edit_checks) / len(edit_checks), 4)
        if verification_checks:
            verification = round(sum(verification_checks) / len(verification_checks), 4)

    if decision is None:
        decision = 0.0
    if edit is None:
        edit = 0.0
    if verification is None:
        verification = 0.0

    return decision, edit, verification


def build_parity_report(*, details: list[dict[str, Any]]) -> dict[str, Any]:
    enriched_details: list[dict[str, Any]] = []
    scores: list[float] = []
    decision_scores: list[float] = []
    edit_scores: list[float] = []
    verification_scores: list[float] = []
    failure_breakdown = {"environment": 0, "runtime": 0, "capability": 0}
    failure_taxonomy = {
        "model": 0,
        "tool": 0,
        "orchestration": 0,
        "semantic": 0,
        "verification": 0,
        "environment": 0,
    }
    for detail in details:
        item = dict(detail)
        raw_score = item.get("score")
        try:
            score_value = float(raw_score)
        except (TypeError, ValueError):
            score_value = 1.0 if item.get("status") == "passed" else 0.0
        bounded_score = max(0.0, min(1.0, score_value))
        scores.append(bounded_score)

        decision, edit, verification = _derive_quality_dimensions(item, base_score=bounded_score)
        item["decision_quality_score"] = round(decision, 4)
        item["edit_correctness_score"] = round(edit, 4)
        item["verification_pass_rate"] = round(verification, 4)
        item["quality_metrics"] = {
            "decision_quality_score": item["decision_quality_score"],
            "edit_correctness_score": item["edit_correctness_score"],
            "verification_pass_rate": item["verification_pass_rate"],
            "weighted_quality_score": round(
                (item["decision_quality_score"] * 0.35)
                + (item["edit_correctness_score"] * 0.45)
                + (item["verification_pass_rate"] * 0.20),
                4,
            ),
        }

        decision_scores.append(item["decision_quality_score"])
        edit_scores.append(item["edit_correctness_score"])
        verification_scores.append(item["verification_pass_rate"])
        if item.get("status") != "passed":
            category = _classify_failure_reason(str(item.get("reason", "")))
            item["failure_category"] = category
            failure_breakdown[category] = int(failure_breakdown.get(category, 0)) + 1
            taxonomy_category = _classify_failure_taxonomy_reason(str(item.get("reason", "")))
            item["failure_taxonomy_category"] = taxonomy_category
            failure_taxonomy[taxonomy_category] = int(failure_taxonomy.get(taxonomy_category, 0)) + 1
        enriched_details.append(item)

    total = len(enriched_details)
    passed = sum(1 for detail in enriched_details if detail.get("status") == "passed")
    failed = total - passed
    success_rate = float(passed) / float(total) if total else 0.0
    average_score = float(sum(scores)) / float(len(scores)) if scores else 0.0
    unresolved_gaps = sorted({str(detail.get("reason", "")) for detail in enriched_details if detail.get("status") != "passed"})
    quality_metrics = {
        "decision_quality_score": round(float(sum(decision_scores)) / float(len(decision_scores)), 4)
        if decision_scores
        else 0.0,
        "edit_correctness_score": round(float(sum(edit_scores)) / float(len(edit_scores)), 4) if edit_scores else 0.0,
        "verification_pass_rate": round(float(sum(verification_scores)) / float(len(verification_scores)), 4)
        if verification_scores
        else 0.0,
    }
    quality_metrics["weighted_quality_score"] = round(
        (quality_metrics["decision_quality_score"] * 0.35)
        + (quality_metrics["edit_correctness_score"] * 0.45)
        + (quality_metrics["verification_pass_rate"] * 0.20),
        4,
    )
    environment_failures = int(failure_breakdown.get("environment", 0))
    runtime_failures = int(failure_breakdown.get("runtime", 0))
    capability_failures = int(failure_breakdown.get("capability", 0))
    denominator = float(total) if total else 1.0
    capability_scope_total = max(0, total - environment_failures - runtime_failures)
    capability_success_rate = (
        round(float(passed) / float(capability_scope_total), 4) if capability_scope_total > 0 else 0.0
    )
    capability_matrix = _build_capability_matrix(enriched_details)
    quality_dimension_matrix = _build_quality_dimension_matrix(quality_metrics)
    return {
        "contract_version": _CONTRACT_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "success_rate": round(success_rate, 4),
        "capability_success_rate": capability_success_rate,
        "average_score": round(average_score, 4),
        "quality_metrics": quality_metrics,
        "quality_dimension_matrix": quality_dimension_matrix,
        "capability_matrix": capability_matrix,
        "failure_breakdown": failure_breakdown,
        "failure_taxonomy": failure_taxonomy,
        "environment_failure_rate": round(environment_failures / denominator, 4),
        "runtime_failure_rate": round(runtime_failures / denominator, 4),
        "capability_failure_rate": round(capability_failures / denominator, 4),
        "details": enriched_details,
        "unresolved_gaps": unresolved_gaps,
    }
