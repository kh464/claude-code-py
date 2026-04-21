from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest

from agent.contracts import ToolContext
from agent.workspace_isolation.git_worktree import create_git_worktree, remove_git_worktree
from agent.workspace_isolation.worktree import WorktreeManager


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"git-worktree-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_create_git_worktree_invokes_git_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    temp_root = _create_temp_dir()
    try:
        repo_root = temp_root / "repo"
        repo_root.mkdir()
        worktree_root = temp_root / "worktrees"
        worktree_root.mkdir()
        calls: list[dict[str, Any]] = []

        def fake_run(
            command: list[str],
            *,
            cwd: Path | str,
            check: bool,
            capture_output: bool,
            text: bool,
            **_kwargs,
        ):
            calls.append({"command": command, "cwd": str(cwd), "check": check})
            if command[:3] == ["git", "worktree", "add"]:
                Path(command[5]).mkdir(parents=True, exist_ok=True)

            class _Result:
                stdout = ""
                stderr = ""
                returncode = 0

            return _Result()

        monkeypatch.setattr("agent.workspace_isolation.git_worktree.subprocess.run", fake_run)

        created = create_git_worktree(repo_root=repo_root, slug="feature-a", worktree_root=worktree_root)
        assert created["worktree_branch"] == "worktree/feature-a"
        assert Path(created["worktree_path"]).exists()

        remove_git_worktree(
            repo_root=repo_root,
            path=Path(created["worktree_path"]),
            branch=created["worktree_branch"],
        )

        assert calls[0]["command"][:3] == ["git", "worktree", "add"]
        assert calls[1]["command"][:3] == ["git", "worktree", "remove"]
        assert calls[2]["command"][:3] == ["git", "branch", "-D"]
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_git_worktree_create_reuse_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    temp_root = _create_temp_dir()
    try:
        repo_root = temp_root / "repo"
        repo_root.mkdir()
        worktree_root = temp_root / "worktrees"
        worktree_root.mkdir()

        created_calls: list[tuple[str, str, str]] = []
        remove_calls: list[tuple[str, str, str]] = []

        def fake_detect_git_repo_root(start: Path) -> Path | None:
            _ = start
            return repo_root

        def fake_create_git_worktree(*, repo_root: Path, slug: str, worktree_root: Path) -> dict[str, Any]:
            created_calls.append((str(repo_root), slug, str(worktree_root)))
            worktree_path = worktree_root / slug
            worktree_path.mkdir(parents=True, exist_ok=True)
            return {
                "worktree_path": str(worktree_path),
                "worktree_branch": f"worktree/{slug}",
                "git_backed": True,
                "git_repo_root": str(repo_root),
                "created": True,
            }

        def fake_remove_git_worktree(*, repo_root: Path, path: Path, branch: str) -> None:
            remove_calls.append((str(repo_root), str(path), branch))
            shutil.rmtree(path, ignore_errors=True)

        monkeypatch.setattr("agent.workspace_isolation.worktree.detect_git_repo_root", fake_detect_git_repo_root)
        monkeypatch.setattr("agent.workspace_isolation.worktree.create_git_worktree", fake_create_git_worktree)
        monkeypatch.setattr("agent.workspace_isolation.worktree.remove_git_worktree", fake_remove_git_worktree)

        manager = WorktreeManager()
        clean_context = ToolContext(
            session_id="session-worktree-clean",
            metadata={
                "worktree_root": str(worktree_root),
                "current_cwd": str(repo_root),
            },
        )

        entered_clean = manager.enter(name="feature-a", context=clean_context)
        reused_clean = manager.enter(name="ignored", context=clean_context)
        assert reused_clean["worktree_path"] == entered_clean["worktree_path"]
        assert reused_clean["worktree_branch"] == entered_clean["worktree_branch"]
        assert created_calls

        exited_clean = manager.exit(action="auto", context=clean_context)
        assert exited_clean["removed"] is True
        assert exited_clean["kept"] is False
        assert remove_calls and remove_calls[0][2].startswith("worktree/")

        dirty_context = ToolContext(
            session_id="session-worktree-dirty",
            metadata={
                "worktree_root": str(worktree_root),
                "current_cwd": str(repo_root),
            },
        )
        entered_dirty = manager.enter(name="feature-b", context=dirty_context)
        dirty_path = Path(entered_dirty["worktree_path"])
        (dirty_path / "notes.txt").write_text("pending changes\n", encoding="utf-8")

        exited_dirty = manager.exit(action="auto", context=dirty_context)
        assert exited_dirty["kept"] is True
        assert exited_dirty["removed"] is False
        assert len(remove_calls) == 1
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
