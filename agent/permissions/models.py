from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PermissionMode(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass(slots=True)
class PermissionRule:
    pattern: str
    mode: PermissionMode
    source: str


@dataclass(slots=True)
class PermissionDecision:
    mode: PermissionMode
    source: str
    retryable: bool
    reason: str = ""
