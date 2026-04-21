from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


class TokenBudgetEstimator:
    def __init__(self, *, tokenizer: Any | None = None) -> None:
        self.tokenizer = tokenizer

    def estimate_text(self, text: str) -> int:
        if self.tokenizer is not None and hasattr(self.tokenizer, "encode"):
            encoded = self.tokenizer.encode(text)
            return max(1, len(encoded))
        chunks = re.findall(r"\S+", text)
        return max(1, len(chunks))

    def estimate_messages(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for message in messages:
            if isinstance(message, Mapping):
                payload = json.dumps(message, ensure_ascii=False, sort_keys=True)
            else:
                payload = str(message)
            total += self.estimate_text(payload)
        return total


_DEFAULT_ESTIMATOR = TokenBudgetEstimator()


def estimate_text_tokens(text: str) -> int:
    return _DEFAULT_ESTIMATOR.estimate_text(text)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return _DEFAULT_ESTIMATOR.estimate_messages(messages)
