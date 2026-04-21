from __future__ import annotations

import shutil
import subprocess
import hashlib
from pathlib import Path
from typing import Any


def _run_git(
    *,
    repo_root: Path,
    args: list[str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )


def detect_git_repo_root(start: Path) -> Path | None:
    try:
        result = _run_git(repo_root=start, args=["rev-parse", "--show-toplevel"])
    except Exception:
        return None
    root = result.stdout.strip()
    if not root:
        return None
    return Path(root).expanduser().resolve()


def create_git_worktree(
    *,
    repo_root: Path,
    slug: str,
    worktree_root: Path,
    base_ref: str = "HEAD",
) -> dict[str, Any]:
    resolved_repo_root = repo_root.expanduser().resolve()
    resolved_worktree_root = worktree_root.expanduser().resolve()
    resolved_worktree_root.mkdir(parents=True, exist_ok=True)

    branch = f"worktree/{slug}"
    worktree_path = (resolved_worktree_root / slug).resolve()
    created = False
    permission_fallback = False

    def _is_permission_error(text: str) -> bool:
        lowered = text.lower()
        return (
            "permission denied" in lowered
            or "access is denied" in lowered
            or "cannot lock ref" in lowered
        )

    def _fallback_local_worktree(*, reason: str) -> dict[str, Any]:
        worktree_path.mkdir(parents=True, exist_ok=True)
        return {
            "worktree_path": str(worktree_path),
            "worktree_branch": branch,
            "git_backed": False,
            "git_repo_root": str(resolved_repo_root),
            "created": created,
            "fallback_reason": reason,
        }

    if not worktree_path.exists():
        try:
            _run_git(
                repo_root=resolved_repo_root,
                args=["worktree", "add", "-b", branch, str(worktree_path), base_ref],
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").lower()
            if _is_permission_error(stderr):
                permission_fallback = True
            if permission_fallback:
                created = True
                return _fallback_local_worktree(reason=stderr or "permission denied")
            if "already exists" not in stderr and "already checked out" not in stderr:
                raise
            try:
                _run_git(
                    repo_root=resolved_repo_root,
                    args=["worktree", "add", str(worktree_path), branch],
                )
            except subprocess.CalledProcessError as reuse_exc:
                reuse_stderr = (reuse_exc.stderr or "").lower()
                if _is_permission_error(reuse_stderr):
                    created = True
                    return _fallback_local_worktree(reason=reuse_stderr or "permission denied")
                if "already used by worktree" not in reuse_stderr:
                    raise
                suffix = hashlib.sha1(str(worktree_path).encode("utf-8")).hexdigest()[:8]
                branch = f"{branch}-{suffix}"
                try:
                    _run_git(
                        repo_root=resolved_repo_root,
                        args=["worktree", "add", "-b", branch, str(worktree_path), base_ref],
                    )
                except subprocess.CalledProcessError as suffix_exc:
                    suffix_stderr = (suffix_exc.stderr or "").lower()
                    if _is_permission_error(suffix_stderr):
                        created = True
                        return _fallback_local_worktree(reason=suffix_stderr or "permission denied")
                    raise
        created = True
    worktree_path.mkdir(parents=True, exist_ok=True)
    return {
        "worktree_path": str(worktree_path),
        "worktree_branch": branch,
        "git_backed": True,
        "git_repo_root": str(resolved_repo_root),
        "created": created,
    }


def remove_git_worktree(*, repo_root: Path, path: Path, branch: str) -> None:
    resolved_repo_root = repo_root.expanduser().resolve()
    resolved_path = path.expanduser().resolve()

    _run_git(
        repo_root=resolved_repo_root,
        args=["worktree", "remove", "--force", str(resolved_path)],
        check=False,
    )
    _run_git(
        repo_root=resolved_repo_root,
        args=["branch", "-D", branch],
        check=False,
    )
    if resolved_path.exists():
        shutil.rmtree(resolved_path, ignore_errors=True)
