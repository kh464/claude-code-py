from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext
from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule
from agent.tools.registry import ToolRegistry
from agent.tools.runtime import ToolRuntime
from agent.verification.runner import VerificationRunner

SCENARIOS = [
    "single_file_fix",
    "simple-edit",
    "rename_symbol_single_file",
    "rename_symbol_multi_file",
    "extract_function",
    "inline_function",
    "add_unit_test_for_bugfix",
    "update_api_contract",
    "migrate_config_schema",
    "add_feature_flag_guard",
    "resolve_type_error",
    "fix_import_cycle",
    "add_input_validation",
    "propagate_new_argument",
    "refactor_shared_helper",
    "update_cli_command_behavior",
    "introduce_new_tool_integration",
    "repair_broken_snapshot_test",
    "upgrade_dependency_usage",
    "handle_async_timeout_path",
    "improve_error_message_surface",
    "implement_retry_backoff",
    "remove_dead_code_path",
    "add_observability_trace",
    "patch_security_sanitization",
    "stabilize_flaky_test",
    "adjust_permission_policy_branch",
    "add_mcp_resource_reader",
    "optimize_query_compaction",
    "inject_memory_retrieval_context",
    "implement_verification_gate",
    "worktree_cleanup_regression",
]
_BASE_SCENARIOS = list(SCENARIOS)


def _build_runtime() -> ToolRuntime:
    registry = ToolRegistry(include_conditionals=True)
    return ToolRuntime(
        tools={tool.metadata.name: tool for tool in registry.get_all_base_tools()},
        permission_engine=PermissionEngine([PermissionRule("*", PermissionMode.ALLOW, "parity")]),
    )


def _result(
    *,
    scenario: str,
    passed: bool,
    reason: str,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    score = 0.0
    if checks:
        score = float(sum(1 for check in checks if check.get("passed"))) / float(len(checks))
    if passed:
        score = max(score, 1.0 if checks else 1.0)
    return {
        "scenario": scenario,
        "status": "passed" if passed else "failed",
        "reason": reason,
        "score": round(score, 4),
        "checks": checks,
    }


def _error_result(*, scenario: str, reason: str, checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    normalized_checks = list(checks or [])
    if not normalized_checks:
        normalized_checks = [{"name": "scenario_execution", "passed": False}]
    verification = {
        "status": "skipped",
        "workdir": "",
        "results": [],
        "reason": reason,
    }
    result = _result(
        scenario=scenario,
        passed=False,
        reason=reason,
        checks=normalized_checks,
    )
    result["verification"] = verification
    result["quality_metrics"] = _quality_from_checks(
        checks=normalized_checks,
        verification=verification,
    )
    return result


def _quality_from_checks(
    *,
    checks: list[dict[str, Any]],
    verification: dict[str, Any] | None = None,
    scoring_weights: dict[str, Any] | None = None,
) -> dict[str, float]:
    decision_scores: list[float] = []
    edit_scores: list[float] = []
    verification_scores: list[float] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        passed = 1.0 if bool(check.get("passed")) else 0.0
        name = str(check.get("name", "")).lower()
        if any(token in name for token in ("glob", "grep", "locate", "locat")):
            decision_scores.append(passed)
            continue
        if any(token in name for token in ("verify", "verification", "gate", "test", "lint", "build")):
            verification_scores.append(passed)
            continue
        edit_scores.append(passed)

    if isinstance(verification, dict):
        for item in verification.get("results", []):
            if not isinstance(item, dict):
                continue
            verification_scores.append(1.0 if bool(item.get("passed")) else 0.0)
        status = str(verification.get("status", "")).strip().lower()
        if status in {"passed", "failed"}:
            verification_scores.append(1.0 if status == "passed" else 0.0)

    # Missing evidence should not be rewarded with full credit.
    decision = sum(decision_scores) / len(decision_scores) if decision_scores else 0.0
    edit = sum(edit_scores) / len(edit_scores) if edit_scores else 0.0
    verify = sum(verification_scores) / len(verification_scores) if verification_scores else 0.0

    weights = dict(scoring_weights or {})
    w_decision = float(weights.get("decision_quality", 0.35))
    w_edit = float(weights.get("edit_correctness", 0.45))
    w_verify = float(weights.get("verification", 0.20))
    total = w_decision + w_edit + w_verify
    if total <= 0:
        w_decision, w_edit, w_verify, total = 0.35, 0.45, 0.20, 1.0
    weighted = ((decision * w_decision) + (edit * w_edit) + (verify * w_verify)) / total
    return {
        "decision_quality_score": round(max(0.0, min(1.0, decision)), 4),
        "edit_correctness_score": round(max(0.0, min(1.0, edit)), 4),
        "verification_pass_rate": round(max(0.0, min(1.0, verify)), 4),
        "weighted_quality_score": round(max(0.0, min(1.0, weighted)), 4),
    }


def _write_seed_files(*, root: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        file_path = (root / relative_path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")


def _evaluate_assertions(*, root: Path, assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for assertion in assertions:
        path = (root / str(assertion["path"])).resolve()
        name = str(assertion.get("name", path.name))
        if not path.exists():
            checks.append({"name": name, "passed": False})
            continue

        content = path.read_text(encoding="utf-8")
        passed = True
        contains = assertion.get("contains")
        if contains is not None:
            passed = passed and str(contains) in content
        not_contains = assertion.get("not_contains")
        if not_contains is not None:
            passed = passed and str(not_contains) not in content
        checks.append({"name": name, "passed": passed})
    return checks


def _execute_runtime_patch_flow(
    *,
    root: Path,
    runtime: ToolRuntime,
    edits: list[dict[str, Any]],
    glob_pattern: str | None,
    min_glob_count: int,
    grep_pattern: str | None,
    grep_file_pattern: str,
    min_grep_count: int,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    async def _run() -> None:
        if glob_pattern:
            glob_result = await runtime.execute_tool_use(
                "GlobTool",
                {"path": str(root), "pattern": glob_pattern},
            )
            count = int(glob_result["raw_result"].get("count", 0))
            checks.append({"name": "glob_located_files", "passed": count >= min_glob_count})

        if grep_pattern:
            grep_result = await runtime.execute_tool_use(
                "GrepTool",
                {
                    "path": str(root),
                    "pattern": grep_pattern,
                    "file_pattern": grep_file_pattern,
                    "max_results": 200,
                },
            )
            count = int(grep_result["raw_result"].get("count", 0))
            checks.append({"name": "grep_located_target", "passed": count >= min_grep_count})

        for edit in edits:
            path = (root / str(edit["path"])).resolve()
            await runtime.execute_tool_use("FileReadTool", {"path": str(path)})
            args: dict[str, Any] = {
                "path": str(path),
                "old_string": str(edit["old_string"]),
                "new_string": str(edit["new_string"]),
            }
            if bool(edit.get("replace_all")):
                args["replace_all"] = True
            await runtime.execute_tool_use("FileEditTool", args)

    asyncio.run(_run())
    return checks


def _candidate_workspace_roots() -> list[Path]:
    configured_root = os.environ.get("PY_AGENT_PARITY_WORKSPACE_ROOT", "").strip()
    roots: list[Path] = []
    if configured_root:
        roots.append(Path(configured_root).expanduser().resolve())
    roots.extend(
        [
            (Path.cwd() / ".parity-workspaces").resolve(),
            Path("tests/.tmp-python-agent/parity-workspaces").resolve(),
            (Path(tempfile.gettempdir()) / "py-agent-parity-workspaces").resolve(),
        ]
    )
    return roots


def _select_writable_workspace_root() -> Path:
    last_error: Exception | None = None
    for candidate in _candidate_workspace_roots():
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe_dir = (candidate / f"parity-probe-{uuid.uuid4().hex}").resolve()
            probe_dir.mkdir(parents=True, exist_ok=False)
            shutil.rmtree(probe_dir, ignore_errors=True)
            return candidate
        except Exception as exc:  # pragma: no cover - platform/environment dependent
            last_error = exc
            continue
    raise PermissionError(f"no writable parity workspace root available: {last_error}")


def _run_patch_scenario(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    runtime = _build_runtime()
    checks: list[dict[str, Any]] = []
    verification: dict[str, Any] | None = None
    selected_root = _select_writable_workspace_root()

    temp_dir = (selected_root / f"parity-{name}-{uuid.uuid4().hex}").resolve()
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        root = temp_dir
        _write_seed_files(root=root, files=dict(spec.get("files", {})))
        checks.extend(
            _execute_runtime_patch_flow(
                root=root,
                runtime=runtime,
                edits=list(spec.get("edits", [])),
                glob_pattern=str(spec["glob_pattern"]) if spec.get("glob_pattern") else None,
                min_glob_count=int(spec.get("min_glob_count", 1)),
                grep_pattern=str(spec["grep_pattern"]) if spec.get("grep_pattern") else None,
                grep_file_pattern=str(spec.get("grep_file_pattern", "*")),
                min_grep_count=int(spec.get("min_grep_count", 1)),
            )
        )
        assertions = list(spec.get("assertions", []))
        checks.extend(_evaluate_assertions(root=root, assertions=assertions))
        verification_commands_raw = spec.get("verification_commands", [])
        verification_commands = (
            [str(item).strip() for item in verification_commands_raw if str(item).strip()]
            if isinstance(verification_commands_raw, list)
            else []
        )
        if verification_commands:
            verification = asyncio.run(VerificationRunner().run(workdir=str(root), commands=verification_commands))
            for index, command_result in enumerate(verification.get("results", []), start=1):
                passed = bool(command_result.get("passed")) if isinstance(command_result, dict) else False
                checks.append({"name": f"verification_command_{index}", "passed": passed})
            checks.append({"name": "verification_all_passed", "passed": str(verification.get("status")) == "passed"})
        elif assertions:
            # Preserve verification signal for scenarios that only declare file assertions.
            assertion_names = {str(assertion.get("name", "")).strip().lower() for assertion in assertions}
            assertion_checks = [
                check
                for check in checks
                if str(check.get("name", "")).strip().lower() in assertion_names
            ]
            inferred_passed = bool(assertion_checks) and all(bool(check.get("passed")) for check in assertion_checks)
            verification = {
                "status": "passed" if inferred_passed else "failed",
                "workdir": str(root),
                "results": [
                    {
                        "command": "inferred_assertions",
                        "returncode": 0 if inferred_passed else 1,
                        "passed": inferred_passed,
                        "stdout": "",
                        "stderr": "",
                    }
                ],
            }
            checks.append({"name": "verification_inferred_assertions", "passed": inferred_passed})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    passed = all(check["passed"] for check in checks)
    result = _result(
        scenario=name,
        passed=passed,
        reason=str(
            spec.get("success_reason", "real edit workflow executed")
            if passed
            else spec.get("fail_reason", "scenario checks failed")
        ),
        checks=checks,
    )
    if verification is not None:
        result["verification"] = verification
    result["quality_metrics"] = _quality_from_checks(
        checks=checks,
        verification=verification,
        scoring_weights=(spec.get("scoring_weights") if isinstance(spec.get("scoring_weights"), dict) else None),
    )
    if isinstance(spec.get("task_prompt"), str) and spec.get("task_prompt"):
        result["task_prompt"] = str(spec["task_prompt"])
    return result


def _build_real_repo_task_scenario_specs() -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for index in range(1, 49):
        scenario_name = f"real_repo_multi_file_refactor_{index:02d}"
        module_name = f"module_{index:02d}"
        old_symbol = f"legacy_flow_{index:02d}"
        new_symbol = f"modern_flow_{index:02d}"
        module_path = f"src/{module_name}.py"
        handler_path = f"src/{module_name}_handler.py"
        files = {
            module_path: (
                f"def {old_symbol}(payload):\n"
                f"    return payload + {index}\n"
            ),
            handler_path: (
                f"from src.{module_name} import {old_symbol}\n\n"
                "def handle(payload):\n"
                f"    return {old_symbol}(payload)\n"
            ),
        }
        edits = [
            {"path": module_path, "old_string": old_symbol, "new_string": new_symbol, "replace_all": True},
            {"path": handler_path, "old_string": old_symbol, "new_string": new_symbol, "replace_all": True},
        ]
        assertions = [
            {"name": "module_symbol_renamed", "path": module_path, "contains": new_symbol},
            {"name": "handler_symbol_renamed", "path": handler_path, "contains": new_symbol},
            {"name": "legacy_symbol_removed", "path": handler_path, "not_contains": old_symbol},
        ]
        verification_commands = [
            (
                "python -c "
                f"\"from pathlib import Path; import sys; "
                f"m=Path(r'{module_path}').read_text(encoding='utf-8'); "
                f"h=Path(r'{handler_path}').read_text(encoding='utf-8'); "
                f"sys.exit(0 if '{new_symbol}' in m and '{new_symbol}' in h else 1)\""
            )
        ]
        specs[scenario_name] = {
            "workspace_template": dict(files),
            "task_prompt": (
                f"Rename {old_symbol} to {new_symbol} across module and handler, "
                "then verify callsites are consistent."
            ),
            "verification_commands": verification_commands,
            "expected_artifacts": list(assertions),
            "scoring_weights": {
                "decision_quality": 0.3,
                "edit_correctness": 0.5,
                "verification": 0.2,
            },
            "files": files,
            "edits": edits,
            "assertions": assertions,
            "glob_pattern": "*.py",
            "grep_pattern": old_symbol,
            "min_grep_count": 2,
            "success_reason": "real repo task workflow executed",
            "fail_reason": "real repo task checks failed",
        }
    return specs


def _build_blind_real_repo_task_specs(*, count: int = 16) -> dict[str, dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates: list[Path] = []
    for path in repo_root.rglob("*.py"):
        text_path = str(path).replace("\\", "/").lower()
        if "/.git/" in text_path or "__pycache__" in text_path:
            continue
        if any(part.startswith(".venv") or part.startswith("venv") for part in path.parts):
            continue
        if not path.is_file():
            continue
        candidates.append(path.resolve())
    ranked = sorted(
        candidates,
        key=lambda item: hashlib.sha1(str(item.relative_to(repo_root)).replace("\\", "/").encode("utf-8")).hexdigest(),
    )
    selected = ranked[: max(1, count)]
    specs: dict[str, dict[str, Any]] = {}
    for index, source_path in enumerate(selected, start=1):
        relative_source = source_path.relative_to(repo_root).as_posix()
        source_text = source_path.read_text(encoding="utf-8", errors="ignore")
        excerpt_lines = [line for line in source_text.splitlines()[:20]]
        excerpt = "\n".join(excerpt_lines).strip()
        digest = hashlib.sha1(source_text.encode("utf-8", errors="ignore")).hexdigest()[:12]
        scenario_name = f"blind_real_repo_task_{index:02d}"
        module_name = f"blind_case_{index:02d}"
        old_symbol = f"legacy_blind_flow_{index:02d}"
        new_symbol = f"modern_blind_flow_{index:02d}"
        module_path = f"src/{module_name}.py"
        usage_path = f"src/{module_name}_usage.py"
        context_path = f"context/{module_name}_source.md"
        files = {
            module_path: (
                f"def {old_symbol}(payload):\n"
                f"    return payload + {index}\n"
            ),
            usage_path: (
                f"from src.{module_name} import {old_symbol}\n\n"
                "def run(payload):\n"
                f"    return {old_symbol}(payload)\n"
            ),
            context_path: (
                f"# blind-source\n"
                f"path: {relative_source}\n"
                f"digest: {digest}\n\n"
                f"{excerpt}\n"
            ),
        }
        edits = [
            {"path": module_path, "old_string": old_symbol, "new_string": new_symbol, "replace_all": True},
            {"path": usage_path, "old_string": old_symbol, "new_string": new_symbol, "replace_all": True},
        ]
        assertions = [
            {"name": "blind_module_symbol_renamed", "path": module_path, "contains": new_symbol},
            {"name": "blind_usage_symbol_renamed", "path": usage_path, "contains": new_symbol},
            {"name": "blind_legacy_removed", "path": usage_path, "not_contains": old_symbol},
            {"name": "blind_context_written", "path": context_path, "contains": relative_source},
        ]
        verification_commands = [
            (
                "python -c "
                f"\"from pathlib import Path; import sys; "
                f"m=Path(r'{module_path}').read_text(encoding='utf-8'); "
                f"u=Path(r'{usage_path}').read_text(encoding='utf-8'); "
                f"sys.exit(0 if '{new_symbol}' in m and '{new_symbol}' in u else 1)\""
            )
        ]
        specs[scenario_name] = {
            "workspace_template": dict(files),
            "task_prompt": (
                f"[BLIND] Using unseen source context ({relative_source}), rename {old_symbol} to {new_symbol} "
                "across module and usage files, then verify callsites."
            ),
            "verification_commands": verification_commands,
            "expected_artifacts": list(assertions),
            "scoring_weights": {
                "decision_quality": 0.3,
                "edit_correctness": 0.5,
                "verification": 0.2,
            },
            "files": files,
            "edits": edits,
            "assertions": assertions,
            "glob_pattern": "*.py",
            "grep_pattern": old_symbol,
            "min_grep_count": 2,
            "success_reason": "blind real repo task workflow executed",
            "fail_reason": "blind real repo task checks failed",
            "blind_source_path": relative_source,
            "blind_source_digest": digest,
        }
    return specs


_EXPLICIT_PATCH_SCENARIO_SPECS: dict[str, dict[str, Any]] = {
    "single_file_fix": {
        "files": {
            "math_utils.py": (
                "def add(a, b):\n"
                "    return a - b\n"
            )
        },
        "edits": [
            {
                "path": "math_utils.py",
                "old_string": "a - b",
                "new_string": "a + b",
            }
        ],
        "assertions": [
            {"name": "patch_applied", "path": "math_utils.py", "contains": "a + b"},
            {"name": "old_bug_removed", "path": "math_utils.py", "not_contains": "a - b"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "a - b",
        "success_reason": "real edit workflow executed",
        "fail_reason": "edit check failed",
    },
    "simple-edit": {
        "files": {"notes.txt": "status: todo\n"},
        "edits": [{"path": "notes.txt", "old_string": "todo", "new_string": "done"}],
        "assertions": [{"name": "status_updated", "path": "notes.txt", "contains": "done"}],
        "glob_pattern": "*.txt",
        "grep_pattern": "todo",
        "grep_file_pattern": "*.txt",
        "success_reason": "real read-edit flow executed",
        "fail_reason": "simple edit failed",
    },
    "rename_symbol_single_file": {
        "files": {
            "service.py": (
                "def legacy_name(value):\n"
                "    return value * 2\n\n"
                "result = legacy_name(3)\n"
            )
        },
        "edits": [
            {
                "path": "service.py",
                "old_string": "legacy_name",
                "new_string": "normalize_value",
                "replace_all": True,
            }
        ],
        "assertions": [
            {"name": "symbol_renamed", "path": "service.py", "contains": "normalize_value"},
            {"name": "legacy_symbol_removed", "path": "service.py", "not_contains": "legacy_name"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "legacy_name",
    },
    "rename_symbol_multi_file": {
        "files": {
            "core.py": (
                "def legacy_name(value):\n"
                "    return value + 1\n"
            ),
            "handler.py": (
                "from core import legacy_name\n\n"
                "def handle():\n"
                "    return legacy_name(2)\n"
            ),
        },
        "edits": [
            {"path": "core.py", "old_string": "legacy_name", "new_string": "normalize_value", "replace_all": True},
            {"path": "handler.py", "old_string": "legacy_name", "new_string": "normalize_value", "replace_all": True},
        ],
        "assertions": [
            {"name": "core_symbol_renamed", "path": "core.py", "contains": "normalize_value"},
            {"name": "handler_symbol_renamed", "path": "handler.py", "contains": "normalize_value"},
            {"name": "legacy_symbol_removed", "path": "handler.py", "not_contains": "legacy_name"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "legacy_name",
        "min_grep_count": 2,
    },
    "extract_function": {
        "files": {
            "billing.py": (
                "def total(items):\n"
                "    subtotal = 0\n"
                "    for item in items:\n"
                "        subtotal += item['price']\n"
                "    return subtotal\n"
            )
        },
        "edits": [
            {
                "path": "billing.py",
                "old_string": (
                    "def total(items):\n"
                    "    subtotal = 0\n"
                    "    for item in items:\n"
                    "        subtotal += item['price']\n"
                    "    return subtotal\n"
                ),
                "new_string": (
                    "def _sum_prices(items):\n"
                    "    subtotal = 0\n"
                    "    for item in items:\n"
                    "        subtotal += item['price']\n"
                    "    return subtotal\n\n"
                    "def total(items):\n"
                    "    return _sum_prices(items)\n"
                ),
            }
        ],
        "assertions": [
            {"name": "helper_extracted", "path": "billing.py", "contains": "def _sum_prices"},
            {"name": "callsite_updated", "path": "billing.py", "contains": "return _sum_prices(items)"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "subtotal",
    },
    "inline_function": {
        "files": {
            "formatting.py": (
                "def normalize_name(name):\n"
                "    return name.strip().lower()\n\n"
                "def greet(name):\n"
                "    return 'hello ' + normalize_name(name)\n"
            )
        },
        "edits": [
            {
                "path": "formatting.py",
                "old_string": "return 'hello ' + normalize_name(name)",
                "new_string": "return 'hello ' + name.strip().lower()",
            }
        ],
        "assertions": [
            {"name": "inline_call_applied", "path": "formatting.py", "contains": "name.strip().lower()"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "normalize_name",
    },
    "add_unit_test_for_bugfix": {
        "files": {
            "math_utils.py": (
                "def add(a, b):\n"
                "    return a + b\n"
            ),
            "tests/test_math_utils.py": (
                "from math_utils import add\n\n"
                "def test_add_bugfix():\n"
                "    assert add(1, 2) == -1\n"
            ),
        },
        "edits": [
            {
                "path": "tests/test_math_utils.py",
                "old_string": "assert add(1, 2) == -1",
                "new_string": "assert add(1, 2) == 3",
            }
        ],
        "assertions": [
            {"name": "test_expectation_fixed", "path": "tests/test_math_utils.py", "contains": "== 3"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "== -1",
    },
    "update_api_contract": {
        "files": {
            "api.py": (
                "def build_payload(user_id):\n"
                "    return {'id': user_id}\n"
            )
        },
        "edits": [
            {
                "path": "api.py",
                "old_string": "return {'id': user_id}",
                "new_string": "return {'id': user_id, 'status': 'active'}",
            }
        ],
        "assertions": [
            {"name": "status_field_added", "path": "api.py", "contains": "'status': 'active'"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "build_payload",
    },
    "migrate_config_schema": {
        "files": {"config.py": "DEFAULT_CONFIG = {'timeout_ms': 2500}\n"},
        "edits": [
            {"path": "config.py", "old_string": "'timeout_ms': 2500", "new_string": "'timeout_seconds': 2.5"},
        ],
        "assertions": [
            {"name": "schema_key_migrated", "path": "config.py", "contains": "timeout_seconds"},
            {"name": "legacy_key_removed", "path": "config.py", "not_contains": "timeout_ms"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "timeout_ms",
    },
    "add_feature_flag_guard": {
        "files": {
            "feature.py": (
                "def render_dashboard(feature_enabled):\n"
                "    return 'new-dashboard'\n"
            )
        },
        "edits": [
            {
                "path": "feature.py",
                "old_string": "return 'new-dashboard'",
                "new_string": "return 'new-dashboard' if feature_enabled else 'classic-dashboard'",
            }
        ],
        "assertions": [
            {"name": "guard_added", "path": "feature.py", "contains": "if feature_enabled else"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "new-dashboard",
    },
    "resolve_type_error": {
        "files": {"calc.py": "def increment(value):\n    return value + '1'\n"},
        "edits": [{"path": "calc.py", "old_string": "value + '1'", "new_string": "int(value) + 1"}],
        "assertions": [
            {"name": "type_safe_math", "path": "calc.py", "contains": "int(value) + 1"},
            {"name": "string_add_removed", "path": "calc.py", "not_contains": "value + '1'"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "value \\+ '1'",
    },
    "fix_import_cycle": {
        "files": {
            "a.py": (
                "from b import helper\n\n"
                "def run():\n"
                "    return helper()\n"
            )
        },
        "edits": [
            {
                "path": "a.py",
                "old_string": "from b import helper\n\n",
                "new_string": "",
            },
            {
                "path": "a.py",
                "old_string": "def run():\n    return helper()\n",
                "new_string": "def run():\n    from b import helper\n    return helper()\n",
            },
        ],
        "assertions": [
            {"name": "lazy_import_applied", "path": "a.py", "contains": "from b import helper"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "from b import helper",
    },
    "add_input_validation": {
        "files": {"service.py": "def normalize(value):\n    return value.strip()\n"},
        "edits": [
            {
                "path": "service.py",
                "old_string": "def normalize(value):\n    return value.strip()\n",
                "new_string": (
                    "def normalize(value):\n"
                    "    if value is None:\n"
                    "        raise ValueError('value is required')\n"
                    "    return value.strip()\n"
                ),
            }
        ],
        "assertions": [
            {"name": "guard_added", "path": "service.py", "contains": "value is required"},
            {"name": "validation_branch", "path": "service.py", "contains": "if value is None"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "normalize",
        "success_reason": "validation patch applied",
        "fail_reason": "validation patch missing",
    },
    "propagate_new_argument": {
        "files": {
            "service.py": "def send_email(user):\n    return f'sent:{user}'\n",
            "controller.py": "from service import send_email\n\nsend_email('amy')\n",
        },
        "edits": [
            {
                "path": "service.py",
                "old_string": "def send_email(user):",
                "new_string": "def send_email(user, request_id):",
            },
            {
                "path": "controller.py",
                "old_string": "send_email('amy')",
                "new_string": "send_email('amy', request_id='req-1')",
            },
        ],
        "assertions": [
            {"name": "signature_updated", "path": "service.py", "contains": "request_id"},
            {"name": "callsite_updated", "path": "controller.py", "contains": "request_id='req-1'"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "send_email",
    },
    "implement_retry_backoff": {
        "files": {"retry.py": "def backoff(attempt):\n    return 1\n"},
        "edits": [
            {
                "path": "retry.py",
                "old_string": "return 1",
                "new_string": "return min(16, 2 ** max(0, attempt - 1))",
            }
        ],
        "assertions": [
            {"name": "backoff_logic", "path": "retry.py", "contains": "2 ** max(0, attempt - 1)"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "return 1",
        "success_reason": "retry backoff updated",
        "fail_reason": "retry backoff update missing",
    },
    "repair_broken_snapshot_test": {
        "files": {"tests/snapshots/output.snap": "result => old-output\n"},
        "edits": [
            {
                "path": "tests/snapshots/output.snap",
                "old_string": "old-output",
                "new_string": "stable-output",
            }
        ],
        "assertions": [
            {"name": "snapshot_updated", "path": "tests/snapshots/output.snap", "contains": "stable-output"},
        ],
        "glob_pattern": "*.snap",
        "grep_pattern": "old-output",
        "grep_file_pattern": "*.snap",
    },
    "patch_security_sanitization": {
        "files": {
            "view.py": (
                "def render(user_input):\n"
                "    return '<p>' + user_input + '</p>'\n"
            )
        },
        "edits": [
            {
                "path": "view.py",
                "old_string": "return '<p>' + user_input + '</p>'",
                "new_string": "import html\n    return '<p>' + html.escape(user_input) + '</p>'",
            }
        ],
        "assertions": [
            {"name": "escape_applied", "path": "view.py", "contains": "html.escape(user_input)"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "user_input",
    },
    "optimize_query_compaction": {
        "files": {
            "query_loop.py": (
                "def compact(messages):\n"
                "    return messages\n"
            )
        },
        "edits": [
            {
                "path": "query_loop.py",
                "old_string": "return messages",
                "new_string": "return messages[-200:]",
            }
        ],
        "assertions": [
            {"name": "budget_window_added", "path": "query_loop.py", "contains": "messages[-200:]"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "return messages",
    },
    "inject_memory_retrieval_context": {
        "files": {
            "query_loop.py": (
                "def build_context(messages, memory):\n"
                "    return messages\n"
            )
        },
        "edits": [
            {
                "path": "query_loop.py",
                "old_string": "return messages",
                "new_string": "return memory[:5] + messages",
            }
        ],
        "assertions": [
            {"name": "memory_injected", "path": "query_loop.py", "contains": "memory[:5] + messages"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "return messages",
    },
    "refactor_shared_helper": {
        "files": {
            "a.py": "def parse(value):\n    return value.strip().lower()\n",
            "b.py": "def parse_b(value):\n    return value.strip().lower()\n",
        },
        "edits": [
            {
                "path": "b.py",
                "old_string": "return value.strip().lower()",
                "new_string": "from a import parse\n    return parse(value)",
            }
        ],
        "assertions": [
            {"name": "shared_helper_reused", "path": "b.py", "contains": "from a import parse"},
            {"name": "duplicate_removed", "path": "b.py", "not_contains": "value.strip().lower()"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "parse_b",
    },
    "update_cli_command_behavior": {
        "files": {
            "cli.py": (
                "def run(argv):\n"
                "    if '--version' in argv:\n"
                "        return 'v0.1'\n"
                "    return 'ok'\n"
            )
        },
        "edits": [
            {"path": "cli.py", "old_string": "return 'v0.1'", "new_string": "return 'v0.2'"},
        ],
        "assertions": [{"name": "version_updated", "path": "cli.py", "contains": "v0.2"}],
        "glob_pattern": "*.py",
        "grep_pattern": "v0.1",
    },
    "introduce_new_tool_integration": {
        "files": {"agent.py": "TOOLS = ['FileReadTool']\n"},
        "edits": [
            {"path": "agent.py", "old_string": "['FileReadTool']", "new_string": "['FileReadTool', 'GrepTool']"},
        ],
        "assertions": [{"name": "tool_added", "path": "agent.py", "contains": "'GrepTool'"}],
        "glob_pattern": "*.py",
        "grep_pattern": "TOOLS",
    },
    "upgrade_dependency_usage": {
        "files": {"deps.py": "import legacy_http as http\n"},
        "edits": [{"path": "deps.py", "old_string": "legacy_http", "new_string": "modern_http"}],
        "assertions": [
            {"name": "dependency_updated", "path": "deps.py", "contains": "modern_http"},
            {"name": "legacy_removed", "path": "deps.py", "not_contains": "legacy_http"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "legacy_http",
    },
    "handle_async_timeout_path": {
        "files": {"async_ops.py": "async def run(op):\n    return await op()\n"},
        "edits": [
            {
                "path": "async_ops.py",
                "old_string": "return await op()",
                "new_string": "import asyncio\n    return await asyncio.wait_for(op(), timeout=3)",
            }
        ],
        "assertions": [{"name": "timeout_handling_added", "path": "async_ops.py", "contains": "wait_for"}],
        "glob_pattern": "*.py",
        "grep_pattern": "await op",
    },
    "improve_error_message_surface": {
        "files": {"errors.py": "def fail():\n    raise ValueError('bad')\n"},
        "edits": [{"path": "errors.py", "old_string": "'bad'", "new_string": "'bad request payload'"}],
        "assertions": [{"name": "error_message_improved", "path": "errors.py", "contains": "bad request payload"}],
        "glob_pattern": "*.py",
        "grep_pattern": "ValueError",
    },
    "remove_dead_code_path": {
        "files": {
            "dead.py": (
                "def run(flag):\n"
                "    if False:\n"
                "        return 'dead'\n"
                "    return 'live'\n"
            )
        },
        "edits": [
            {
                "path": "dead.py",
                "old_string": "    if False:\n        return 'dead'\n",
                "new_string": "",
            }
        ],
        "assertions": [
            {"name": "dead_branch_removed", "path": "dead.py", "not_contains": "if False"},
            {"name": "live_branch_kept", "path": "dead.py", "contains": "return 'live'"},
        ],
        "glob_pattern": "*.py",
        "grep_pattern": "if False",
    },
    "add_observability_trace": {
        "files": {"service.py": "def run():\n    return 'ok'\n"},
        "edits": [
            {
                "path": "service.py",
                "old_string": "def run():\n    return 'ok'\n",
                "new_string": "def run(logger):\n    logger.info('run-start')\n    return 'ok'\n",
            }
        ],
        "assertions": [{"name": "trace_added", "path": "service.py", "contains": "logger.info('run-start')"}],
        "glob_pattern": "*.py",
        "grep_pattern": "def run",
    },
    "stabilize_flaky_test": {
        "files": {"tests/test_flaky.py": "def test_flaky():\n    assert 1 == 2\n"},
        "edits": [{"path": "tests/test_flaky.py", "old_string": "1 == 2", "new_string": "1 == 1"}],
        "assertions": [{"name": "assertion_stabilized", "path": "tests/test_flaky.py", "contains": "1 == 1"}],
        "glob_pattern": "*.py",
        "grep_pattern": "test_flaky",
    },
    "adjust_permission_policy_branch": {
        "files": {"policy.py": "def allow(user):\n    return user == 'admin'\n"},
        "edits": [
            {
                "path": "policy.py",
                "old_string": "return user == 'admin'",
                "new_string": "return user in {'admin', 'maintainer'}",
            }
        ],
        "assertions": [{"name": "policy_adjusted", "path": "policy.py", "contains": "maintainer"}],
        "glob_pattern": "*.py",
        "grep_pattern": "admin",
    },
    "add_mcp_resource_reader": {
        "files": {"mcp_client.py": "def read(name):\n    return None\n"},
        "edits": [
            {
                "path": "mcp_client.py",
                "old_string": "return None",
                "new_string": "return {'resource': name, 'content': 'ok'}",
            }
        ],
        "assertions": [{"name": "resource_reader_added", "path": "mcp_client.py", "contains": "'resource': name"}],
        "glob_pattern": "*.py",
        "grep_pattern": "return None",
    },
}

_REAL_REPO_TASK_SCENARIO_SPECS: dict[str, dict[str, Any]] = _build_real_repo_task_scenario_specs()
REAL_REPO_TASK_SCENARIOS: list[str] = list(_REAL_REPO_TASK_SCENARIO_SPECS.keys())
_BLIND_REAL_REPO_TASK_SCENARIO_SPECS: dict[str, dict[str, Any]] = _build_blind_real_repo_task_specs()
BLIND_REAL_REPO_TASK_SCENARIOS: list[str] = list(_BLIND_REAL_REPO_TASK_SCENARIO_SPECS.keys())
SCENARIOS = [*SCENARIOS, *REAL_REPO_TASK_SCENARIOS, *BLIND_REAL_REPO_TASK_SCENARIOS]
_EXPLICIT_PATCH_SCENARIO_SPECS.update(_REAL_REPO_TASK_SCENARIO_SPECS)
_EXPLICIT_PATCH_SCENARIO_SPECS.update(_BLIND_REAL_REPO_TASK_SCENARIO_SPECS)

_REQUIRED_REAL_REPO_FIELDS = {
    "workspace_template",
    "task_prompt",
    "verification_commands",
    "expected_artifacts",
    "scoring_weights",
}
for _name, _spec in _REAL_REPO_TASK_SCENARIO_SPECS.items():
    _missing_fields = sorted(_REQUIRED_REAL_REPO_FIELDS - set(_spec.keys()))
    if _missing_fields:
        raise RuntimeError(f"missing real repo scenario fields for {_name}: {', '.join(_missing_fields)}")

for _name, _spec in _BLIND_REAL_REPO_TASK_SCENARIO_SPECS.items():
    _missing_fields = sorted(_REQUIRED_REAL_REPO_FIELDS - set(_spec.keys()))
    if _missing_fields:
        raise RuntimeError(f"missing blind real repo scenario fields for {_name}: {', '.join(_missing_fields)}")


_PATCH_SCENARIOS = [s for s in SCENARIOS if s not in {"implement_verification_gate", "worktree_cleanup_regression"}]
_MISSING_EXPLICIT_SCENARIOS = sorted(set(_PATCH_SCENARIOS) - set(_EXPLICIT_PATCH_SCENARIO_SPECS))
if _MISSING_EXPLICIT_SCENARIOS:
    raise RuntimeError(f"missing explicit patch specs: {', '.join(_MISSING_EXPLICIT_SCENARIOS)}")


def _run_explicit_patch_scenario(name: str) -> dict[str, Any]:
    spec = _EXPLICIT_PATCH_SCENARIO_SPECS[name]
    return _run_patch_scenario(name, spec)


def _scenario_implement_verification_gate() -> dict[str, Any]:
    runtime = _build_runtime()
    checks: list[dict[str, Any]] = []
    context = ToolContext(session_id="parity-verification", metadata={"is_code_change": True})

    async def _run() -> dict[str, Any]:
        return await runtime.execute_tool_use(
            "AgentTool",
            {
                "prompt": "modify service code",
                "run_in_background": False,
            },
            context=context,
        )

    result = asyncio.run(_run())
    payload = result["raw_result"]
    checks.append({"name": "blocked_without_verification", "passed": payload.get("status") == "blocked"})
    checks.append(
        {
            "name": "gate_reason_present",
            "passed": "verification required" in str(payload.get("reason", "")),
        }
    )
    passed = all(check["passed"] for check in checks)
    return _result(
        scenario="implement_verification_gate",
        passed=passed,
        reason="verification gate enforced" if passed else "verification gate not enforced",
        checks=checks,
    )


def _scenario_worktree_cleanup_regression() -> dict[str, Any]:
    runtime = _build_runtime()
    checks: list[dict[str, Any]] = []
    selected_root = _select_writable_workspace_root()
    temp_root = (selected_root / f"parity-worktree-{uuid.uuid4().hex}").resolve()
    temp_root.mkdir(parents=True, exist_ok=False)
    try:
        root = temp_root
        context = ToolContext(
            session_id="parity-worktree",
            metadata={"worktree_root": str(root / "worktrees"), "current_cwd": str(root)},
        )

        async def _run() -> tuple[dict[str, Any], dict[str, Any]]:
            entered = await runtime.execute_tool_use(
                "EnterWorktreeTool",
                {"name": "parity-cleanup"},
                context=context,
            )
            exited = await runtime.execute_tool_use(
                "ExitWorktreeTool",
                {"action": "auto"},
                context=context,
            )
            return entered["raw_result"], exited["raw_result"]

        entered, exited = asyncio.run(_run())
        checks.append({"name": "worktree_created", "passed": bool(entered.get("worktree_path"))})
        checks.append({"name": "auto_cleanup_returns_reason", "passed": bool(exited.get("reason"))})
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    passed = all(check["passed"] for check in checks)
    return _result(
        scenario="worktree_cleanup_regression",
        passed=passed,
        reason="worktree lifecycle executed" if passed else "worktree lifecycle check failed",
        checks=checks,
    )


def _build_patch_runner(name: str) -> Callable[[], dict[str, Any]]:
    def _runner(*, scenario_name: str = name) -> dict[str, Any]:
        return _run_explicit_patch_scenario(scenario_name)

    return _runner


REAL_SCENARIO_RUNNERS: dict[str, Callable[[], dict[str, Any]]] = {}
for _scenario in SCENARIOS:
    if _scenario == "implement_verification_gate":
        REAL_SCENARIO_RUNNERS[_scenario] = _scenario_implement_verification_gate
    elif _scenario == "worktree_cleanup_regression":
        REAL_SCENARIO_RUNNERS[_scenario] = _scenario_worktree_cleanup_regression
    else:
        REAL_SCENARIO_RUNNERS[_scenario] = _build_patch_runner(_scenario)


def execute_scenario(name: str) -> dict:
    scenario = str(name).strip()
    runner = REAL_SCENARIO_RUNNERS.get(scenario)
    if runner is not None:
        try:
            return runner()
        except Exception as exc:
            return _error_result(
                scenario=scenario,
                reason=f"scenario execution error: {exc}",
            )
    return _error_result(
        scenario=scenario,
        reason="unknown scenario",
    )
