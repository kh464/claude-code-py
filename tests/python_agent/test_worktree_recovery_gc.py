from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from agent.contracts import ToolContext
from agent.workspace_isolation.recovery import collect_stale_worktrees
from agent.workspace_isolation.worktree import WorktreeManager


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"worktree-recovery-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_worktree_recovery_rebinds_running_task_after_restart() -> None:
    temp_root = _create_temp_dir()
    try:
        worktree_root = temp_root / "worktrees"
        context = ToolContext(
            session_id="session-recover",
            metadata={"worktree_root": str(worktree_root), "current_cwd": str(temp_root)},
        )
        manager = WorktreeManager(default_root=worktree_root)
        entered = manager.enter(name="recover-me", context=context)
        assert Path(entered["worktree_path"]).exists()

        restarted_manager = WorktreeManager(default_root=worktree_root)
        recovered = restarted_manager.recover(context=context)
        assert recovered
        assert recovered[0]["session_id"] == "session-recover"

        exited = restarted_manager.exit(action="keep", context=context)
        assert exited["session_id"] == "session-recover"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_worktree_gc_removes_stale_entries_without_active_sessions() -> None:
    temp_root = _create_temp_dir()
    try:
        worktree_root = temp_root / "worktrees"
        manager = WorktreeManager(default_root=worktree_root)
        context_a = ToolContext(
            session_id="session-active",
            metadata={"worktree_root": str(worktree_root), "current_cwd": str(temp_root)},
        )
        context_b = ToolContext(
            session_id="session-stale",
            metadata={"worktree_root": str(worktree_root), "current_cwd": str(temp_root)},
        )
        entered_a = manager.enter(name="keep-me", context=context_a)
        entered_b = manager.enter(name="drop-me", context=context_b)

        result = collect_stale_worktrees(root=worktree_root, active_session_ids={"session-active"})
        assert result["removed_count"] >= 1
        assert Path(entered_a["worktree_path"]).exists()
        assert not Path(entered_b["worktree_path"]).exists()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
