from __future__ import annotations

import subprocess
import sys
import tempfile
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

CheckFn = Callable[[], tuple[bool, str] | bool]


def _check_workspace_writable() -> tuple[bool, str]:
    configured_root = os.environ.get("PY_AGENT_PARITY_WORKSPACE_ROOT", "").strip()
    candidates: list[Path] = []
    if configured_root:
        candidates.append(Path(configured_root).expanduser().resolve())
    candidates.extend(
        [
            (Path.cwd() / ".parity-workspaces").resolve(),
            Path("tests/.tmp-python-agent/parity-workspaces").resolve(),
            (Path(tempfile.gettempdir()) / "py-agent-parity-workspaces").resolve(),
        ]
    )
    errors: list[str] = []
    for root in candidates:
        try:
            root.mkdir(parents=True, exist_ok=True)
            temp_dir = (root / f"preflight-{uuid.uuid4().hex}").resolve()
            temp_dir.mkdir(parents=True, exist_ok=False)
            marker = temp_dir / "marker.txt"
            marker.write_text("ok\n", encoding="utf-8")
            _ = marker.read_text(encoding="utf-8")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return True, f"workspace writable: {root}"
        except Exception as exc:  # pragma: no cover - platform/environment dependent
            errors.append(f"{root}: {exc}")
    return False, "workspace not writable: " + " | ".join(errors)


def _check_python_executable() -> tuple[bool, str]:
    completed = subprocess.run(
        [sys.executable, "-c", "print('preflight-python-ok')"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    if int(completed.returncode or 0) != 0:
        return False, f"python command failed: {completed.stderr.strip()}"
    return True, "python executable available"


def _check_git_available() -> tuple[bool, str]:
    completed = subprocess.run(
        ["git", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    if int(completed.returncode or 0) != 0:
        return False, f"git unavailable: {completed.stderr.strip()}"
    return True, "git available"


def _check_shell_exec() -> tuple[bool, str]:
    completed = subprocess.run(
        "echo preflight-shell-ok",
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    if int(completed.returncode or 0) != 0:
        return False, f"shell exec failed: {completed.stderr.strip()}"
    return True, "shell executable"


def run_parity_preflight(*, checks: list[tuple[str, CheckFn]] | None = None) -> dict[str, Any]:
    selected_checks = checks or [
        ("workspace_writable", _check_workspace_writable),
        ("python_executable", _check_python_executable),
        ("git_available", _check_git_available),
        ("shell_exec", _check_shell_exec),
    ]
    results: list[dict[str, Any]] = []
    failed_names: list[str] = []
    for name, check_fn in selected_checks:
        try:
            raw = check_fn()
            if isinstance(raw, tuple):
                passed = bool(raw[0])
                detail = str(raw[1]) if len(raw) > 1 else ""
            else:
                passed = bool(raw)
                detail = ""
        except Exception as exc:  # pragma: no cover - defensive path
            passed = False
            detail = str(exc)
        if not passed:
            failed_names.append(str(name))
        results.append({"name": str(name), "passed": passed, "detail": detail})

    total = len(results)
    failed = len(failed_names)
    passed = total - failed
    status = "passed" if failed == 0 else "failed"
    reason = "ok" if status == "passed" else f"{', '.join(failed_names)} failed"
    return {
        "status": status,
        "total": total,
        "passed": passed,
        "failed": failed,
        "reason": reason,
        "checks": results,
    }
