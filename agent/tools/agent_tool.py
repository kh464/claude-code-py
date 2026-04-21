from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.subagents.loader import get_active_agents, resolve_agent_tools
from agent.subagents.models import AgentDescriptor
from agent.subagents.task_manager import TaskManager
from agent.verification.policy import must_verify
from agent.workspace_isolation.worktree import WorktreeManager


class AgentTool(ToolDef):
    metadata = ToolMetadata(name="AgentTool")
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "name": {"type": "string"},
            "subagent_type": {"type": "string"},
            "model": {"type": "string"},
            "isolation": {"type": "string"},
            "run_in_background": {"type": "boolean"},
            "fork_context": {"type": "boolean"},
            "max_rounds": {"type": "integer"},
            "recover_worktrees": {"type": "boolean"},
            "resume_task_id": {"type": "string"},
            "resume_agent_id": {"type": "string"},
            "verification_commands": {"type": "array"},
        },
        "required": [],
    }
    output_schema = {"type": "object"}

    def __init__(
        self,
        *,
        task_manager: TaskManager,
        worktree_manager: WorktreeManager | None = None,
    ) -> None:
        self.task_manager = task_manager
        self.worktree_manager = worktree_manager

    def validate_input(self, args: Mapping[str, Any]) -> None:
        has_resume_target = bool(args.get("resume_task_id") or args.get("resume_agent_id"))
        if has_resume_target:
            return
        prompt = str(args.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("prompt must not be empty unless resume_task_id/resume_agent_id is provided")

    def _load_active_agents(self, context: ToolContext | None) -> list[AgentDescriptor]:
        metadata = context.metadata if context is not None else {}
        return get_active_agents(
            include_conditionals=bool(metadata.get("include_conditionals", True)),
            user_agents_dir=metadata.get("user_agents_dir"),
            project_agents_dir=metadata.get("project_agents_dir"),
        )

    def _resolve_selected_agent(
        self,
        *,
        subagent_type: str | None,
        active_agents: list[AgentDescriptor],
    ) -> AgentDescriptor | None:
        if not subagent_type:
            return None
        for descriptor in active_agents:
            if descriptor.name == subagent_type:
                return descriptor
        raise ValueError(f"Unknown subagent_type: {subagent_type}")

    @staticmethod
    def _resolve_verification_commands(
        *,
        args: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> list[str]:
        raw_candidates = args.get("verification_commands")
        if not (isinstance(raw_candidates, list) and raw_candidates):
            raw_candidates = metadata.get("default_verification_commands")
        if not (isinstance(raw_candidates, list) and raw_candidates):
            raw_candidates = metadata.get("verification_commands")
        if not isinstance(raw_candidates, list):
            return []
        commands: list[str] = []
        seen: set[str] = set()
        for item in raw_candidates:
            command = str(item).strip()
            if not command or command in seen:
                continue
            seen.add(command)
            commands.append(command)
        return commands

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = can_use_tool, parent_message
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "launching"})

        resume_task_id = str(args["resume_task_id"]) if args.get("resume_task_id") else None
        resume_agent_id = str(args["resume_agent_id"]) if args.get("resume_agent_id") else None
        if resume_task_id or resume_agent_id:
            resumed = await self.task_manager.resume(
                task_id=resume_task_id,
                agent_id=resume_agent_id,
                context=context,
            )
            on_progress(
                {
                    "event": "tool_progress",
                    "tool": self.metadata.name,
                    "stage": "resumed",
                    "task_id": resumed.get("task_id"),
                    "agent_id": resumed.get("agent_id"),
                }
            )
            return resumed

        subagent_type = str(args["subagent_type"]) if args.get("subagent_type") else None
        active_agents = self._load_active_agents(context)
        selected_agent = self._resolve_selected_agent(subagent_type=subagent_type, active_agents=active_agents)

        metadata = context.metadata if context is not None else {}
        available_tools_raw = metadata.get("available_tools", [])
        available_tools = [str(name) for name in available_tools_raw] if isinstance(available_tools_raw, list) else []
        resolved_tools = (
            resolve_agent_tools(selected_agent, available_tools)
            if selected_agent is not None and available_tools
            else available_tools
        )

        base_prompt = str(args["prompt"])
        effective_prompt = base_prompt
        if selected_agent is not None and selected_agent.initial_prompt:
            effective_prompt = f"{selected_agent.initial_prompt}\n{base_prompt}"

        if "run_in_background" in args:
            run_in_background = bool(args.get("run_in_background"))
        else:
            run_in_background = bool(selected_agent.background) if selected_agent is not None else False

        effective_name = (
            str(args["name"])
            if args.get("name")
            else (selected_agent.name if selected_agent is not None else None)
        )
        effective_model = (
            str(args["model"])
            if args.get("model")
            else (selected_agent.model if selected_agent is not None else None)
        )
        effective_isolation = (
            str(args["isolation"])
            if args.get("isolation")
            else (selected_agent.isolation if selected_agent is not None else None)
        )
        effective_permission_mode = selected_agent.permission_mode if selected_agent is not None else None
        task_metadata = dict(context.metadata) if context is not None else {}
        verification_commands = self._resolve_verification_commands(args=args, metadata=task_metadata)
        task_metadata["subagent_run_in_background"] = run_in_background
        task_metadata["subagent_resolved_tools"] = resolved_tools
        if verification_commands:
            task_metadata["verification_commands"] = verification_commands
        if args.get("max_rounds") is not None:
            task_metadata["subagent_max_rounds"] = int(args["max_rounds"])
        if selected_agent is not None:
            task_metadata["subagent_name"] = selected_agent.name
        if effective_model:
            task_metadata["subagent_model"] = effective_model
        requires_verification = must_verify(prompt=effective_prompt, metadata=task_metadata)
        if not run_in_background and requires_verification and not verification_commands:
            blocked = {
                "status": "blocked",
                "reason": "verification required for code-change task",
                "name": effective_name or subagent_type or "general-purpose",
                "effective_model": effective_model,
                "effective_isolation": effective_isolation,
                "effective_permission_mode": effective_permission_mode,
                "effective_prompt": effective_prompt,
                "resolved_tools": resolved_tools,
                "selected_agent": (
                    {"name": selected_agent.name, "source": selected_agent.source}
                    if selected_agent is not None
                    else None
                ),
            }
            on_progress(
                {
                    "event": "tool_progress",
                    "tool": self.metadata.name,
                    "stage": "blocked",
                    "reason": blocked["reason"],
                }
            )
            return blocked

        entered_worktree: dict[str, Any] | None = None
        worktree_session_id: str | None = None
        worktree_context: ToolContext | None = None
        if (
            effective_isolation == "worktree"
            and self.worktree_manager is not None
            and not run_in_background
        ):
            metadata_copy = dict(context.metadata) if context is not None else {}
            parent_session_id = context.session_id if context is not None else "session"
            worktree_session_id = f"{parent_session_id}:fg-{uuid.uuid4().hex[:8]}"
            worktree_context = ToolContext(session_id=worktree_session_id, metadata=metadata_copy)
            entered_worktree = self.worktree_manager.enter(
                name=effective_name or subagent_type or "foreground-task",
                context=worktree_context,
            )
            task_metadata["current_cwd"] = entered_worktree["worktree_path"]

        task_context = ToolContext(
            session_id=context.session_id if context is not None else None,
            task_id=context.task_id if context is not None else None,
            metadata=task_metadata,
        )
        recovered_worktrees = []
        if bool(args.get("recover_worktrees")) and self.worktree_manager is not None:
            recovered_worktrees = self.worktree_manager.recover(context=context)
        result: dict[str, Any]
        try:
            result = await self.task_manager.launch(
                prompt=effective_prompt,
                run_in_background=run_in_background,
                context=task_context,
                name=effective_name,
                model=effective_model,
                subagent_type=subagent_type,
                isolation=effective_isolation,
            )

            if effective_isolation == "worktree" and self.worktree_manager is not None:
                if entered_worktree is not None:
                    result["worktree_path"] = entered_worktree["worktree_path"]
                    result["worktree_branch"] = entered_worktree["worktree_branch"]
                    result["worktree_git_backed"] = entered_worktree.get("git_backed")
                    result["worktree_git_repo_root"] = entered_worktree.get("git_repo_root")
                    if result.get("task_id") and worktree_session_id is not None:
                        await self.task_manager.attach_worktree(
                            task_id=str(result["task_id"]),
                            worktree_path=entered_worktree["worktree_path"],
                            worktree_branch=entered_worktree["worktree_branch"],
                            worktree_session_id=worktree_session_id,
                            context=context,
                        )
                elif run_in_background:
                    metadata_copy = dict(context.metadata) if context is not None else {}
                    parent_session_id = context.session_id if context is not None else "session"
                    worktree_session_id = f"{parent_session_id}:{result['task_id']}"
                    worktree_context = ToolContext(session_id=worktree_session_id, metadata=metadata_copy)
                    entered = self.worktree_manager.enter(
                        name=effective_name or subagent_type or result["task_id"],
                        context=worktree_context,
                    )
                    result["worktree_path"] = entered["worktree_path"]
                    result["worktree_branch"] = entered["worktree_branch"]
                    result["worktree_git_backed"] = entered.get("git_backed")
                    result["worktree_git_repo_root"] = entered.get("git_repo_root")
                    await self.task_manager.attach_worktree(
                        task_id=result["task_id"],
                        worktree_path=entered["worktree_path"],
                        worktree_branch=entered["worktree_branch"],
                        worktree_session_id=worktree_session_id,
                        context=context,
                    )
        finally:
            if (
                entered_worktree is not None
                and not run_in_background
                and self.worktree_manager is not None
                and worktree_context is not None
            ):
                cleanup_result = self.worktree_manager.exit(action="auto", context=worktree_context)
                if "result" in locals():
                    result["worktree_cleanup"] = cleanup_result
        result["selected_agent"] = (
            {"name": selected_agent.name, "source": selected_agent.source}
            if selected_agent is not None
            else None
        )
        result["effective_model"] = effective_model
        result["effective_isolation"] = effective_isolation
        result["effective_permission_mode"] = effective_permission_mode
        result["effective_prompt"] = effective_prompt
        result["resolved_tools"] = resolved_tools
        if recovered_worktrees:
            result["recovered_worktrees"] = recovered_worktrees
        on_progress(
            {
                "event": "tool_progress",
                "tool": self.metadata.name,
                "stage": result.get("status", "completed"),
                "task_id": result.get("task_id"),
                "agent_id": result.get("agent_id"),
            }
        )
        return result
