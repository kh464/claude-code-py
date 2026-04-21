from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext
from agent.workspace_isolation.git_worktree import (
    create_git_worktree,
    detect_git_repo_root,
    remove_git_worktree,
)
from agent.workspace_isolation.recovery import (
    recover_worktree_sessions,
    remove_session_manifest,
    save_session_manifest,
)

@dataclass(slots=True)
class WorktreeExitStrategy:
    keep_worktree: bool
    reason: str


def decide_exit_strategy(*, has_changes: bool, auto_cleanup_when_clean: bool = True) -> WorktreeExitStrategy:
    if has_changes:
        return WorktreeExitStrategy(keep_worktree=True, reason="Worktree has uncommitted changes")
    if auto_cleanup_when_clean:
        return WorktreeExitStrategy(keep_worktree=False, reason="No changes, safe to cleanup")
    return WorktreeExitStrategy(keep_worktree=True, reason="Configured to keep worktree")


def validate_safe_delete(root: str | Path, target: str | Path) -> None:
    root_path = Path(root).resolve()
    target_path = Path(target).resolve()
    if target_path == root_path:
        return
    if root_path not in target_path.parents:
        raise ValueError(f"Unsafe delete target outside root: {target_path}")


@dataclass(slots=True)
class WorktreeSession:
    session_id: str
    original_cwd: str
    worktree_path: str
    worktree_name: str
    worktree_branch: str
    root_path: str
    baseline_snapshot: set[str]
    git_backed: bool = False
    git_repo_root: str | None = None


def _slugify(name: str) -> str:
    value = name.strip().replace("\\", "-").replace("/", "-").replace(" ", "-")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    slug = "".join(ch if ch in allowed else "-" for ch in value)
    slug = slug.strip("-.")
    return slug or f"worktree-{uuid.uuid4().hex[:8]}"


def _snapshot_directory(path: Path) -> set[str]:
    snapshot: set[str] = set()
    if not path.exists():
        return snapshot
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(path).as_posix()
        size = item.stat().st_size
        snapshot.add(f"{rel}:{size}")
    return snapshot


class WorktreeManager:
    def __init__(self, default_root: str | Path | None = None) -> None:
        self.default_root = (
            Path(default_root).resolve()
            if default_root is not None
            else (Path.cwd() / ".claude" / "worktrees").resolve()
        )
        self.default_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, WorktreeSession] = {}

    def _resolve_root(self, context: ToolContext | None) -> Path:
        metadata = context.metadata if context is not None else {}
        configured = metadata.get("worktree_root")
        if configured is None:
            root = self.default_root
        else:
            root = Path(str(configured)).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _resolve_original_cwd(self, context: ToolContext | None) -> Path:
        metadata = context.metadata if context is not None else {}
        configured = metadata.get("current_cwd")
        if configured is None:
            return Path.cwd().resolve()
        return Path(str(configured)).expanduser().resolve()

    def _resolve_git_repo_root(self, *, context: ToolContext | None, original_cwd: Path) -> Path | None:
        metadata = context.metadata if context is not None else {}
        configured = metadata.get("git_worktree_repo_root")
        if configured is not None:
            return Path(str(configured)).expanduser().resolve()
        return detect_git_repo_root(original_cwd)

    def enter(self, *, name: str | None, context: ToolContext | None) -> dict[str, Any]:
        session_id = (context.session_id if context is not None else None) or f"session-{uuid.uuid4().hex[:8]}"
        if session_id in self._sessions:
            session = self._sessions[session_id]
            return {
                "session_id": session.session_id,
                "worktree_path": session.worktree_path,
                "worktree_name": session.worktree_name,
                "worktree_branch": session.worktree_branch,
                "original_cwd": session.original_cwd,
            }

        root = self._resolve_root(context)
        original_cwd = self._resolve_original_cwd(context)
        slug = _slugify(name or f"wt-{uuid.uuid4().hex[:8]}")
        git_repo_root = self._resolve_git_repo_root(context=context, original_cwd=original_cwd)
        git_backed = False
        effective_git_repo_root: str | None = str(git_repo_root) if git_repo_root is not None else None
        if git_repo_root is not None:
            created = create_git_worktree(
                repo_root=git_repo_root,
                slug=slug,
                worktree_root=root,
            )
            worktree_path = Path(created["worktree_path"]).resolve()
            worktree_branch = str(created["worktree_branch"])
            git_backed = bool(created.get("git_backed", True))
            if created.get("git_repo_root"):
                effective_git_repo_root = str(created.get("git_repo_root"))
        else:
            worktree_path = (root / slug).resolve()
            worktree_path.mkdir(parents=True, exist_ok=True)
            worktree_branch = f"worktree/{slug}"
        baseline = _snapshot_directory(worktree_path)
        session = WorktreeSession(
            session_id=session_id,
            original_cwd=str(original_cwd),
            worktree_path=str(worktree_path),
            worktree_name=slug,
            worktree_branch=worktree_branch,
            root_path=str(root),
            baseline_snapshot=baseline,
            git_backed=git_backed,
            git_repo_root=effective_git_repo_root if git_backed else None,
        )
        self._sessions[session_id] = session
        save_session_manifest(
            root=Path(session.root_path),
            payload={
                "session_id": session.session_id,
                "original_cwd": session.original_cwd,
                "worktree_path": session.worktree_path,
                "worktree_name": session.worktree_name,
                "worktree_branch": session.worktree_branch,
                "root_path": session.root_path,
                "git_backed": session.git_backed,
                "git_repo_root": session.git_repo_root,
            },
        )
        return {
            "session_id": session.session_id,
            "worktree_path": session.worktree_path,
            "worktree_name": session.worktree_name,
            "worktree_branch": session.worktree_branch,
            "original_cwd": session.original_cwd,
            "git_backed": session.git_backed,
            "git_repo_root": session.git_repo_root,
        }

    def exit(
        self,
        *,
        action: str = "auto",
        context: ToolContext | None,
        auto_cleanup_when_clean: bool = True,
    ) -> dict[str, Any]:
        session_id = (context.session_id if context is not None else None) or ""
        if not session_id or session_id not in self._sessions:
            raise ValueError("No active worktree session")

        session = self._sessions[session_id]
        worktree_path = Path(session.worktree_path)
        has_changes = _snapshot_directory(worktree_path) != session.baseline_snapshot
        if action == "keep":
            strategy = WorktreeExitStrategy(keep_worktree=True, reason="Requested keep")
        elif action == "remove":
            strategy = WorktreeExitStrategy(keep_worktree=False, reason="Requested remove")
        else:
            strategy = decide_exit_strategy(
                has_changes=has_changes,
                auto_cleanup_when_clean=auto_cleanup_when_clean,
            )

        kept = strategy.keep_worktree
        removed = False
        if not kept and worktree_path.exists():
            validate_safe_delete(session.root_path, worktree_path)
            if session.git_backed and session.git_repo_root is not None:
                remove_git_worktree(
                    repo_root=Path(session.git_repo_root),
                    path=worktree_path,
                    branch=session.worktree_branch,
                )
                removed = not worktree_path.exists()
            else:
                shutil.rmtree(worktree_path, ignore_errors=False)
                removed = True

        remove_session_manifest(root=Path(session.root_path), session_id=session_id)
        del self._sessions[session_id]
        return {
            "session_id": session_id,
            "worktree_path": session.worktree_path,
            "worktree_name": session.worktree_name,
            "worktree_branch": session.worktree_branch,
            "has_changes": has_changes,
            "kept": kept,
            "removed": removed,
            "reason": strategy.reason,
            "git_backed": session.git_backed,
            "git_repo_root": session.git_repo_root,
        }

    def recover(self, *, context: ToolContext | None) -> list[dict[str, Any]]:
        root = self._resolve_root(context)
        recovered_payloads = recover_worktree_sessions(root=root)
        recovered: list[dict[str, Any]] = []
        for payload in recovered_payloads:
            session_id = str(payload.get("session_id", "")).strip()
            if not session_id:
                continue
            if session_id in self._sessions:
                continue
            worktree_path = str(payload.get("worktree_path", ""))
            worktree_name = str(payload.get("worktree_name", ""))
            worktree_branch = str(payload.get("worktree_branch", ""))
            original_cwd = str(payload.get("original_cwd", Path.cwd()))
            session = WorktreeSession(
                session_id=session_id,
                original_cwd=original_cwd,
                worktree_path=worktree_path,
                worktree_name=worktree_name,
                worktree_branch=worktree_branch,
                root_path=str(root),
                baseline_snapshot=_snapshot_directory(Path(worktree_path)),
                git_backed=bool(payload.get("git_backed", False)),
                git_repo_root=str(payload.get("git_repo_root")) if payload.get("git_repo_root") else None,
            )
            self._sessions[session_id] = session
            recovered.append(
                {
                    "session_id": session.session_id,
                    "worktree_path": session.worktree_path,
                    "worktree_name": session.worktree_name,
                    "worktree_branch": session.worktree_branch,
                }
            )
        return recovered
