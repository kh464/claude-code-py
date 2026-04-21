from __future__ import annotations

from agent.permissions.engine import PermissionEngine
from agent.permissions.models import PermissionMode, PermissionRule


def test_permission_engine_matches_ordered_rules() -> None:
    engine = PermissionEngine(
        [
            PermissionRule("FileWriteTool", PermissionMode.DENY, "policy"),
            PermissionRule("*Read*", PermissionMode.ALLOW, "user"),
        ],
        default_mode=PermissionMode.ASK,
    )

    deny = engine.check("FileWriteTool")
    allow = engine.check("FileReadTool")
    ask = engine.check("UnknownTool")

    assert deny.mode is PermissionMode.DENY
    assert deny.source == "policy"
    assert allow.mode is PermissionMode.ALLOW
    assert allow.source == "user"
    assert ask.mode is PermissionMode.ASK


def test_permission_retryability_for_denied_destructive_tool() -> None:
    engine = PermissionEngine([PermissionRule("FileWriteTool", PermissionMode.DENY, "policy")])
    decision = engine.check("FileWriteTool", is_destructive=True)

    assert decision.mode is PermissionMode.DENY
    assert decision.retryable is False


def test_permission_engine_supports_always_rule_sets_with_priority() -> None:
    engine = PermissionEngine(
        [PermissionRule("*", PermissionMode.ALLOW, "session")],
        always_allow_rules=[PermissionRule("FileReadTool", PermissionMode.ALLOW, "user")],
        always_ask_rules=[PermissionRule("FileReadTool", PermissionMode.ASK, "local")],
        always_deny_rules=[PermissionRule("FileReadTool", PermissionMode.DENY, "policy")],
    )

    decision = engine.check("FileReadTool")
    assert decision.mode is PermissionMode.DENY
    assert decision.source == "policy"
    assert "always_deny" in decision.reason


def test_permission_engine_tracks_always_ask_when_no_deny_match() -> None:
    engine = PermissionEngine(
        always_ask_rules=[PermissionRule("TaskCreateTool", PermissionMode.ASK, "session")]
    )

    decision = engine.check("TaskCreateTool")
    assert decision.mode is PermissionMode.ASK
    assert decision.source == "session"
