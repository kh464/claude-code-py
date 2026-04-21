from __future__ import annotations

from agent.tools.registry import ToolRegistry


EXPECTED_TOOL_NAMES = {
    "BashTool",
    "FileReadTool",
    "FileEditTool",
    "FileWriteTool",
    "GlobTool",
    "GrepTool",
    "NotebookEditTool",
    "LSPTool",
    "PowerShellTool",
    "AgentTool",
    "SendMessageTool",
    "TaskStopTool",
    "TaskOutputTool",
    "TeamCreateTool",
    "TeamDeleteTool",
    "ListPeersTool",
    "EnterPlanModeTool",
    "ExitPlanModeV2Tool",
    "TodoWriteTool",
    "TaskCreateTool",
    "TaskGetTool",
    "TaskUpdateTool",
    "TaskListTool",
    "VerifyPlanExecutionTool",
    "WebSearchTool",
    "WebFetchTool",
    "WebBrowserTool",
    "SkillTool",
    "AskUserQuestionTool",
    "ToolSearchTool",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
    "EnterWorktreeTool",
    "ExitWorktreeTool",
    "WorkflowTool",
    "SleepTool",
    "BriefTool",
    "SnipTool",
    "CtxInspectTool",
    "TerminalCaptureTool",
    "MonitorTool",
    "RemoteTriggerTool",
    "PushNotificationTool",
    "SubscribePRTool",
    "SuggestBackgroundPRTool",
    "SendUserFileTool",
    "ReviewArtifactTool",
    "CronCreateTool",
    "CronDeleteTool",
    "CronListTool",
    "ConfigTool",
    "TungstenTool",
    "REPLTool",
    "OverflowTestTool",
    "TestingPermissionTool",
    "SyntheticOutputTool",
}


def test_registry_contains_all_static_tools() -> None:
    registry = ToolRegistry(include_conditionals=True)
    names = {tool.metadata.name for tool in registry.get_all_base_tools()}

    assert names == EXPECTED_TOOL_NAMES
    assert len(names) == 56


def test_registry_hides_conditionals_when_disabled() -> None:
    registry = ToolRegistry(include_conditionals=False)
    names = {tool.metadata.name for tool in registry.get_all_base_tools()}

    assert "LSPTool" not in names
    assert "WebBrowserTool" not in names
    assert "BashTool" in names


def test_registry_supports_dynamic_mcp_tool_injection() -> None:
    registry = ToolRegistry(include_conditionals=True)
    registry.inject_mcp_tools("github", ["search_issues"])

    tool = registry.get("mcp__github__search_issues")
    assert tool.metadata.name == "mcp__github__search_issues"
