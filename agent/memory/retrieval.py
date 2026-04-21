from __future__ import annotations

import re
from typing import Any

from .store import MemoryStore


_ALIASES = {
    "auth": "authentication",
    "authentication": "authentication",
    "credential": "authentication",
    "credentials": "authentication",
    "fail": "failure",
    "fails": "failure",
    "failed": "failure",
    "failures": "failure",
    "signin": "authentication",
    "signon": "authentication",
    "login": "authentication",
    "expiry": "expire",
    "expired": "expire",
    "expires": "expire",
    "timeout": "expire",
}


def _normalize_text(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"\bsign[\s\-_]*in\b", "signin", normalized)
    normalized = re.sub(r"\bsign[\s\-_]*on\b", "signon", normalized)
    normalized = re.sub(r"[^a-z0-9_]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _normalize_token(token: str) -> str:
    normalized = token.lower().strip()
    normalized = _ALIASES.get(normalized, normalized)
    if normalized.endswith("ing") and len(normalized) > 5:
        normalized = normalized[:-3]
    if normalized.endswith("ed") and len(normalized) > 4:
        normalized = normalized[:-2]
    if normalized.endswith("s") and len(normalized) > 4:
        normalized = normalized[:-1]
    return _ALIASES.get(normalized, normalized)


def _tokenize(text: str) -> set[str]:
    normalized_text = _normalize_text(text)
    return {_normalize_token(token) for token in re.findall(r"[a-zA-Z0-9_]+", normalized_text) if token}


def _overlap_score(query_tokens: set[str], value_tokens: set[str]) -> float:
    if not query_tokens or not value_tokens:
        return 0.0
    overlap = query_tokens & value_tokens
    return float(len(overlap)) / float(len(query_tokens))


def _char_ngrams(text: str, *, n: int = 3) -> set[str]:
    normalized = _normalize_text(text)
    compact = normalized.replace(" ", "")
    if len(compact) < n:
        return {compact} if compact else set()
    return {compact[i : i + n] for i in range(0, len(compact) - n + 1)}


def _semantic_score(query: str, value: str) -> float:
    q_grams = _char_ngrams(query)
    v_grams = _char_ngrams(value)
    if not q_grams or not v_grams:
        return 0.0
    overlap = q_grams & v_grams
    union = q_grams | v_grams
    return float(len(overlap)) / float(len(union))


class MemoryRanker:
    def rank(self, *, query: str, entries: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
        query_tokens = _tokenize(query)
        updated_values = [float(entry.get("updated_at", 0.0)) for entry in entries]
        min_updated = min(updated_values) if updated_values else 0.0
        max_updated = max(updated_values) if updated_values else 0.0
        span_updated = max(max_updated - min_updated, 1e-9)
        ranked: list[dict[str, Any]] = []
        for entry in entries:
            value_text = str(entry["value"])
            key_text = str(entry.get("key", ""))
            lexical_score = _overlap_score(query_tokens, _tokenize(value_text))
            key_score = _overlap_score(query_tokens, _tokenize(key_text))
            semantic_score = _semantic_score(query, value_text)
            updated_at = float(entry["updated_at"])
            recency_score = (updated_at - min_updated) / span_updated

            score = (0.55 * lexical_score) + (0.25 * semantic_score) + (0.15 * key_score) + (0.05 * recency_score)
            if score <= 0:
                continue
            ranked.append(
                {
                    "key": key_text,
                    "value": value_text,
                    "updated_at": updated_at,
                    "score": round(score, 6),
                }
            )
        ranked.sort(key=lambda item: (item["score"], item["updated_at"]), reverse=True)
        return ranked[: max(1, int(top_k))]


def memory_search(*, store: MemoryStore, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    ranker = MemoryRanker()
    return ranker.rank(query=query, entries=store.list_entries(), top_k=top_k)
