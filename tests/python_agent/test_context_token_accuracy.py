from __future__ import annotations

from agent.context.budget import TokenBudgetEstimator


class FakeTokenizer:
    def encode(self, text: str) -> list[int]:
        return [ord(ch) for ch in text if not ch.isspace()]


def test_budget_uses_model_tokenizer_not_whitespace_estimator() -> None:
    estimator = TokenBudgetEstimator(tokenizer=FakeTokenizer())
    messages = [
        {"role": "user", "content": "a b c"},
        {"role": "assistant", "content": "xyz"},
    ]

    total = estimator.estimate_messages(messages)
    # fake tokenizer counts non-whitespace chars in serialized payload
    assert total > 6
