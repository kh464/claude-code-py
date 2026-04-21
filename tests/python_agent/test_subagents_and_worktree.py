from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from agent.subagents.catalog import get_built_in_agents
from agent.workspace_isolation.worktree import decide_exit_strategy, validate_safe_delete


def test_built_in_agents_include_required_entries() -> None:
    names = {agent.name for agent in get_built_in_agents(include_conditionals=True)}

    assert "general-purpose" in names
    assert "statusline-setup" in names
    assert "claude-code-guide" in names


def test_worktree_exit_strategy_keeps_changes() -> None:
    strategy = decide_exit_strategy(has_changes=True)
    assert strategy.keep_worktree is True


def test_validate_safe_delete_rejects_escape() -> None:
    base = Path("tests/.tmp-python-agent") / f"worktree-{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=False)
    try:
        root = base / "root"
        root.mkdir()
        outside = base / "outside"
        outside.mkdir()

        with pytest.raises(ValueError):
            validate_safe_delete(root, outside)
    finally:
        shutil.rmtree(base, ignore_errors=True)
