from __future__ import annotations

from agent.memory.retrieval import MemoryRanker


def test_memory_retrieval_prefers_semantic_similarity_over_keyword_overlap() -> None:
    ranker = MemoryRanker()
    entries = [
        {"key": "auth-fail", "value": "auth failures happen when login token expires", "updated_at": 10.0},
        {"key": "ui-theme", "value": "button colors and spacing", "updated_at": 20.0},
    ]

    ranked = ranker.rank(query="authentication failure", entries=entries, top_k=2)
    assert ranked
    assert ranked[0]["key"] == "auth-fail"
    assert ranked[0]["score"] >= ranked[-1]["score"]
