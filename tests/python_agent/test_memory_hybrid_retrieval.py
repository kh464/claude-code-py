from __future__ import annotations

from agent.memory.retrieval import MemoryRanker


def test_hybrid_retrieval_ranks_semantic_match_over_lexical_noise() -> None:
    ranker = MemoryRanker()
    entries = [
        {
            "key": "auth-expiry",
            "value": "login token expires and causes authentication failures",
            "updated_at": 10.0,
        },
        {
            "key": "ui-spacing",
            "value": "button margin and card spacing cleanup",
            "updated_at": 100.0,
        },
    ]

    ranked = ranker.rank(query="signin credential expiry problem", entries=entries, top_k=2)
    assert ranked
    assert ranked[0]["key"] == "auth-expiry"
    assert ranked[0]["score"] > 0.0

