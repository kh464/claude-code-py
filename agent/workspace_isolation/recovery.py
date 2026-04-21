from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


MANIFEST_DIR_NAME = ".sessions"


def _manifest_dir(root: Path) -> Path:
    return root / MANIFEST_DIR_NAME


def _manifest_path(root: Path, session_id: str) -> Path:
    safe_session_id = session_id.replace(":", "__")
    return _manifest_dir(root) / f"{safe_session_id}.json"


def save_session_manifest(*, root: Path, payload: dict[str, Any]) -> Path:
    root = root.expanduser().resolve()
    manifest_dir = _manifest_dir(root)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = _manifest_path(root, str(payload["session_id"]))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def remove_session_manifest(*, root: Path, session_id: str) -> None:
    root = root.expanduser().resolve()
    path = _manifest_path(root, session_id)
    if path.exists():
        path.unlink()


def recover_worktree_sessions(*, root: Path) -> list[dict[str, Any]]:
    root = root.expanduser().resolve()
    manifest_dir = _manifest_dir(root)
    if not manifest_dir.exists():
        return []
    recovered: list[dict[str, Any]] = []
    for path in sorted(manifest_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        worktree_path = Path(str(payload.get("worktree_path", ""))).expanduser().resolve()
        if not worktree_path.exists():
            continue
        recovered.append(payload)
    return recovered


def collect_stale_worktrees(*, root: Path, active_session_ids: set[str]) -> dict[str, Any]:
    root = root.expanduser().resolve()
    stale_payloads = recover_worktree_sessions(root=root)
    removed_paths: list[str] = []
    removed_sessions: list[str] = []
    for payload in stale_payloads:
        session_id = str(payload.get("session_id", ""))
        if session_id in active_session_ids:
            continue
        worktree_path = Path(str(payload.get("worktree_path", ""))).expanduser().resolve()
        if root not in worktree_path.parents:
            continue
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)
            removed_paths.append(str(worktree_path))
        remove_session_manifest(root=root, session_id=session_id)
        removed_sessions.append(session_id)

    return {
        "removed_count": len(removed_paths),
        "removed_paths": removed_paths,
        "removed_sessions": removed_sessions,
    }
