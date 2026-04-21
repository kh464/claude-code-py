from __future__ import annotations

import pytest

from agent.tools.file_safety import FileReadStateCache, MissingReadError, NonUniqueMatchError, StaleReadError


def test_edit_requires_prior_read() -> None:
    cache = FileReadStateCache()
    with pytest.raises(MissingReadError):
        cache.ensure_can_edit("a.py", "print('x')", "x")


def test_edit_rejects_stale_read() -> None:
    cache = FileReadStateCache()
    cache.record_read("a.py", "print('x')")
    with pytest.raises(StaleReadError):
        cache.ensure_can_edit("a.py", "print('y')", "x")


def test_edit_requires_unique_match_without_replace_all() -> None:
    cache = FileReadStateCache()
    cache.record_read("a.py", "x\nx")
    with pytest.raises(NonUniqueMatchError):
        cache.ensure_can_edit("a.py", "x\nx", "x")


def test_edit_accepts_replace_all_for_multiple_matches() -> None:
    cache = FileReadStateCache()
    cache.record_read("a.py", "x\nx")
    cache.ensure_can_edit("a.py", "x\nx", "x", replace_all=True)
