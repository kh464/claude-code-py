from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from .models import PermissionDecision, PermissionMode, PermissionRule


@dataclass
class PermissionEngine:
    rules: list[PermissionRule] = field(default_factory=list)
    default_mode: PermissionMode = PermissionMode.ASK
    always_allow_rules: list[PermissionRule] = field(default_factory=list)
    always_deny_rules: list[PermissionRule] = field(default_factory=list)
    always_ask_rules: list[PermissionRule] = field(default_factory=list)

    def add_rule(self, rule: PermissionRule) -> None:
        self.rules.append(rule)

    def add_always_allow_rule(self, rule: PermissionRule) -> None:
        self.always_allow_rules.append(rule)

    def add_always_deny_rule(self, rule: PermissionRule) -> None:
        self.always_deny_rules.append(rule)

    def add_always_ask_rule(self, rule: PermissionRule) -> None:
        self.always_ask_rules.append(rule)

    @staticmethod
    def _first_match(tool_name: str, rules: list[PermissionRule]) -> PermissionRule | None:
        for rule in rules:
            if fnmatch.fnmatch(tool_name, rule.pattern):
                return rule
        return None

    @staticmethod
    def _build_decision(
        rule: PermissionRule,
        *,
        is_destructive: bool,
        bucket: str,
    ) -> PermissionDecision:
        retryable = not (rule.mode is PermissionMode.DENY and is_destructive)
        return PermissionDecision(
            mode=rule.mode,
            source=rule.source,
            retryable=retryable,
            reason=f"Matched {bucket} rule {rule.pattern}",
        )

    def check(self, tool_name: str, *, is_destructive: bool = False) -> PermissionDecision:
        deny_rule = self._first_match(tool_name, self.always_deny_rules)
        if deny_rule is not None:
            return self._build_decision(deny_rule, is_destructive=is_destructive, bucket="always_deny")

        ask_rule = self._first_match(tool_name, self.always_ask_rules)
        if ask_rule is not None:
            return self._build_decision(ask_rule, is_destructive=is_destructive, bucket="always_ask")

        allow_rule = self._first_match(tool_name, self.always_allow_rules)
        if allow_rule is not None:
            return self._build_decision(allow_rule, is_destructive=is_destructive, bucket="always_allow")

        standard_rule = self._first_match(tool_name, self.rules)
        if standard_rule is not None:
            return self._build_decision(standard_rule, is_destructive=is_destructive, bucket="rules")

        return PermissionDecision(
            mode=self.default_mode,
            source="default",
            retryable=True,
            reason="No matching rule",
        )
