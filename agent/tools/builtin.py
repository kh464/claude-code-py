from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agent.contracts import ToolDef, ToolMetadata
from agent.mcp_integration import MCPManager
from agent.subagents.task_manager import TaskManager

from .agent_tool import AgentTool
from .ask_user_question_tool import AskUserQuestionTool
from .bash_tool import BashTool
from .base import StaticTool, ToolFlags
from .enter_worktree_tool import EnterWorktreeTool
from .exit_worktree_tool import ExitWorktreeTool
from .file_safety import FileReadStateCache
from .file_edit_tool import FileEditTool
from .file_read_tool import FileReadTool
from .file_write_tool import FileWriteTool
from .glob_tool import GlobTool
from .grep_tool import GrepTool
from .lsp_tool import LSPTool
from .mcp_tools import DynamicMcpTool, ListMcpResourcesTool, ReadMcpResourceTool, ToolSearchTool
from .notebook_edit_tool import NotebookEditTool
from .operational_tools import build_operational_tools
from .powershell_tool import PowerShellTool
from .plan_mode_tools import EnterPlanModeTool, ExitPlanModeV2Tool
from .send_message_tool import SendMessageTool
from .task_output_tool import TaskOutputTool
from .task_stop_tool import TaskStopTool
from .todo_write_tool import TodoWriteTool
from .web_fetch_tool import WebFetchTool
from .web_search_tool import WebSearchTool
from agent.workspace_isolation.worktree import WorktreeManager


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    conditional: bool = False
    ant_only: bool = False
    testing_only: bool = False
    internal: bool = False
    read_only: bool = False
    destructive: bool = False
    concurrency_safe: bool = True


BUILTIN_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("BashTool"),
    ToolSpec("FileReadTool", read_only=True),
    ToolSpec("FileEditTool", destructive=True, concurrency_safe=False),
    ToolSpec("FileWriteTool", destructive=True, concurrency_safe=False),
    ToolSpec("GlobTool", read_only=True),
    ToolSpec("GrepTool", read_only=True),
    ToolSpec("NotebookEditTool", destructive=True, concurrency_safe=False),
    ToolSpec("LSPTool", conditional=True, read_only=True),
    ToolSpec("PowerShellTool", conditional=True),
    ToolSpec("AgentTool"),
    ToolSpec("SendMessageTool"),
    ToolSpec("TaskStopTool", destructive=True),
    ToolSpec("TaskOutputTool", read_only=True),
    ToolSpec("TeamCreateTool", conditional=True),
    ToolSpec("TeamDeleteTool", conditional=True, destructive=True),
    ToolSpec("ListPeersTool", conditional=True, read_only=True),
    ToolSpec("EnterPlanModeTool"),
    ToolSpec("ExitPlanModeV2Tool"),
    ToolSpec("TodoWriteTool"),
    ToolSpec("TaskCreateTool", conditional=True),
    ToolSpec("TaskGetTool", conditional=True, read_only=True),
    ToolSpec("TaskUpdateTool", conditional=True),
    ToolSpec("TaskListTool", conditional=True, read_only=True),
    ToolSpec("VerifyPlanExecutionTool", conditional=True, read_only=True),
    ToolSpec("WebSearchTool", read_only=True),
    ToolSpec("WebFetchTool", read_only=True),
    ToolSpec("WebBrowserTool", conditional=True),
    ToolSpec("SkillTool"),
    ToolSpec("AskUserQuestionTool"),
    ToolSpec("ToolSearchTool", conditional=True, read_only=True),
    ToolSpec("ListMcpResourcesTool", read_only=True),
    ToolSpec("ReadMcpResourceTool", read_only=True),
    ToolSpec("EnterWorktreeTool", conditional=True),
    ToolSpec("ExitWorktreeTool", conditional=True),
    ToolSpec("WorkflowTool", conditional=True),
    ToolSpec("SleepTool", conditional=True, read_only=True),
    ToolSpec("BriefTool", read_only=True),
    ToolSpec("SnipTool", conditional=True, read_only=True),
    ToolSpec("CtxInspectTool", conditional=True, read_only=True),
    ToolSpec("TerminalCaptureTool", conditional=True, read_only=True),
    ToolSpec("MonitorTool", conditional=True, read_only=True),
    ToolSpec("RemoteTriggerTool", conditional=True),
    ToolSpec("PushNotificationTool", conditional=True),
    ToolSpec("SubscribePRTool", conditional=True),
    ToolSpec("SuggestBackgroundPRTool", ant_only=True),
    ToolSpec("SendUserFileTool", conditional=True),
    ToolSpec("ReviewArtifactTool", conditional=True),
    ToolSpec("CronCreateTool"),
    ToolSpec("CronDeleteTool", destructive=True),
    ToolSpec("CronListTool", read_only=True),
    ToolSpec("ConfigTool", ant_only=True),
    ToolSpec("TungstenTool", ant_only=True),
    ToolSpec("REPLTool", ant_only=True),
    ToolSpec("OverflowTestTool", conditional=True, testing_only=True),
    ToolSpec("TestingPermissionTool", testing_only=True),
    ToolSpec("SyntheticOutputTool", internal=True),
)


def _tool_handler(name: str):
    def _handler(args):
        if name == "BriefTool":
            text = str(args.get("text", ""))
            return {"summary": text[:200]}
        return {"tool": name, "arguments": dict(args)}

    return _handler


def build_builtin_tools(include_conditionals: bool, *, mcp_manager: MCPManager | None = None) -> list[ToolDef]:
    read_cache = FileReadStateCache()
    task_manager = TaskManager()
    worktree_manager = WorktreeManager()
    manager = mcp_manager or MCPManager()
    concrete_tools = {
        "BashTool": BashTool(),
        "FileReadTool": FileReadTool(read_cache=read_cache),
        "FileEditTool": FileEditTool(read_cache=read_cache),
        "FileWriteTool": FileWriteTool(),
        "GlobTool": GlobTool(),
        "GrepTool": GrepTool(),
        "NotebookEditTool": NotebookEditTool(),
        "LSPTool": LSPTool(),
        "PowerShellTool": PowerShellTool(),
        "AgentTool": AgentTool(task_manager=task_manager, worktree_manager=worktree_manager),
        "SendMessageTool": SendMessageTool(task_manager=task_manager),
        "TaskStopTool": TaskStopTool(task_manager=task_manager),
        "TaskOutputTool": TaskOutputTool(task_manager=task_manager),
        "EnterPlanModeTool": EnterPlanModeTool(),
        "ExitPlanModeV2Tool": ExitPlanModeV2Tool(),
        "TodoWriteTool": TodoWriteTool(),
        "AskUserQuestionTool": AskUserQuestionTool(),
        "ListMcpResourcesTool": ListMcpResourcesTool(manager=manager),
        "ReadMcpResourceTool": ReadMcpResourceTool(manager=manager),
        "ToolSearchTool": ToolSearchTool(manager=manager),
        "WebSearchTool": WebSearchTool(),
        "WebFetchTool": WebFetchTool(),
        "EnterWorktreeTool": EnterWorktreeTool(manager=worktree_manager),
        "ExitWorktreeTool": ExitWorktreeTool(manager=worktree_manager),
    }
    concrete_tools.update(build_operational_tools())

    tools = []
    for spec in BUILTIN_TOOL_SPECS:
        if not include_conditionals and (spec.conditional or spec.ant_only or spec.testing_only):
            continue
        concrete = concrete_tools.get(spec.name)
        if concrete is not None:
            tools.append(concrete)
            continue
        metadata = ToolMetadata(name=spec.name)
        flags = ToolFlags(
            concurrency_safe=spec.concurrency_safe,
            read_only=spec.read_only,
            destructive=spec.destructive,
        )
        tools.append(StaticTool(metadata=metadata, flags=flags, handler=_tool_handler(spec.name)))
    return tools


def build_dynamic_mcp_tools(
    server: str,
    tool_names: Iterable[str],
    *,
    mcp_manager: MCPManager | None = None,
) -> list[ToolDef]:
    manager = mcp_manager or MCPManager()
    tools: list[ToolDef] = []
    for name in tool_names:
        tools.append(DynamicMcpTool(manager=manager, server=server, tool_name=name))
    return tools
