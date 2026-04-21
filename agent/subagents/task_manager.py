from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext
from agent.session_store.store import SessionStore
from agent.subagents.executor import SubagentExecutor
from agent.subagents.orchestrator import SubagentOrchestrator
from agent.subagents.roles import AUTOFIX_ROLE, IMPLEMENTER_ROLE, PLANNER_ROLE, REVIEWER_ROLE
from agent.verification.runner import VerificationRunner


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(slots=True)
class ManagedTask:
    task_id: str
    agent_id: str
    name: str
    prompt: str
    status: str
    output_file: Path
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    model: str | None = None
    subagent_type: str | None = None
    isolation: str | None = None
    stop_requested: bool = False
    steps_completed: int = 0
    total_steps: int = 8
    background_task: asyncio.Task[None] | None = None
    inbox: list[str] = field(default_factory=list)
    final_output: str | None = None
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    store_root: str | None = None
    worktree_path: str | None = None
    worktree_branch: str | None = None
    worktree_session_id: str | None = None
    orchestration_status: str | None = None
    verification: dict[str, Any] | None = None
    orchestration: dict[str, Any] | None = None


class TaskManager:
    def __init__(
        self,
        default_root: str | Path | None = None,
        *,
        executor: SubagentExecutor | None = None,
        verification_runner: VerificationRunner | None = None,
    ) -> None:
        self.default_root = (
            Path(default_root).resolve()
            if default_root is not None
            else (Path.cwd() / ".claude" / "python-agent" / "tasks").resolve()
        )
        self.default_root.mkdir(parents=True, exist_ok=True)
        self.executor = executor or SubagentExecutor()
        self.verification_runner = verification_runner or VerificationRunner()
        self._tasks: dict[str, ManagedTask] = {}
        self._agent_to_task: dict[str, str] = {}
        self._store_cache: dict[str, SessionStore] = {}
        self._lock = asyncio.Lock()

    def _resolve_root(self, context: ToolContext | None) -> Path:
        metadata = context.metadata if context is not None else {}
        candidate = metadata.get("task_root")
        if candidate is None:
            root = self.default_root
        else:
            root = Path(str(candidate)).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _resolve_store_root(self, context: ToolContext | None) -> str | None:
        metadata = context.metadata if context is not None else {}
        candidate = metadata.get("session_store_root")
        if candidate is None:
            return None
        return str(Path(str(candidate)).expanduser().resolve())

    def _get_store(self, store_root: str) -> SessionStore:
        cached = self._store_cache.get(store_root)
        if cached is not None:
            return cached
        store = SessionStore(store_root)
        self._store_cache[store_root] = store
        return store

    def _task_to_payload(self, task: ManagedTask) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "agent_id": task.agent_id,
            "name": task.name,
            "prompt": task.prompt,
            "status": task.status,
            "output_file": str(task.output_file),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "model": task.model,
            "subagent_type": task.subagent_type,
            "isolation": task.isolation,
            "stop_requested": task.stop_requested,
            "steps_completed": task.steps_completed,
            "total_steps": task.total_steps,
            "final_output": task.final_output,
            "tool_events": task.tool_events,
            "store_root": task.store_root,
            "worktree_path": task.worktree_path,
            "worktree_branch": task.worktree_branch,
            "worktree_session_id": task.worktree_session_id,
            "orchestration_status": task.orchestration_status,
            "verification": task.verification,
            "orchestration": task.orchestration,
        }

    def _persist_task_state(self, task: ManagedTask) -> None:
        if not task.store_root:
            return
        store = self._get_store(task.store_root)
        store.save_task_state(task.task_id, self._task_to_payload(task))

    async def _restore_tasks_from_store(self, context: ToolContext | None) -> None:
        store_root = self._resolve_store_root(context)
        if store_root is None:
            return
        store = self._get_store(store_root)
        for payload in store.load_all_task_states():
            task_id = str(payload.get("task_id", "")).strip()
            if not task_id or task_id in self._tasks:
                continue
            agent_id = str(payload.get("agent_id", "")).strip()
            if not agent_id:
                continue
            output_file_value = str(payload.get("output_file", "")).strip()
            if output_file_value:
                output_file = Path(output_file_value).expanduser().resolve()
            else:
                output_file = self._resolve_root(context) / f"{task_id}.log"

            restored = ManagedTask(
                task_id=task_id,
                agent_id=agent_id,
                name=str(payload.get("name", "general-purpose")),
                prompt=str(payload.get("prompt", "")),
                status=str(payload.get("status", "completed")),
                output_file=output_file,
                created_at=str(payload.get("created_at", _now_iso())),
                updated_at=str(payload.get("updated_at", _now_iso())),
                model=str(payload.get("model")) if payload.get("model") is not None else None,
                subagent_type=str(payload.get("subagent_type"))
                if payload.get("subagent_type") is not None
                else None,
                isolation=str(payload.get("isolation")) if payload.get("isolation") is not None else None,
                stop_requested=bool(payload.get("stop_requested", False)),
                steps_completed=int(payload.get("steps_completed", 0)),
                total_steps=int(payload.get("total_steps", 8)),
                final_output=str(payload.get("final_output"))
                if payload.get("final_output") is not None
                else None,
                tool_events=list(payload.get("tool_events", []))
                if isinstance(payload.get("tool_events", []), list)
                else [],
                store_root=store_root,
                worktree_path=str(payload.get("worktree_path")) if payload.get("worktree_path") else None,
                worktree_branch=str(payload.get("worktree_branch")) if payload.get("worktree_branch") else None,
                worktree_session_id=str(payload.get("worktree_session_id"))
                if payload.get("worktree_session_id")
                else None,
                orchestration_status=str(payload.get("orchestration_status"))
                if payload.get("orchestration_status")
                else None,
                verification=dict(payload.get("verification"))
                if isinstance(payload.get("verification"), dict)
                else None,
                orchestration=dict(payload.get("orchestration"))
                if isinstance(payload.get("orchestration"), dict)
                else None,
            )
            self._tasks[task_id] = restored
            self._agent_to_task[agent_id] = task_id

    async def _append_output(self, task: ManagedTask, line: str) -> None:
        text = line if line.endswith("\n") else f"{line}\n"
        task.output_file.parent.mkdir(parents=True, exist_ok=True)
        with task.output_file.open("a", encoding="utf-8") as fh:
            fh.write(text)
        task.updated_at = _now_iso()
        self._persist_task_state(task)

    def _copy_context_for_task(self, context: ToolContext | None, *, task_id: str) -> ToolContext:
        if context is None:
            return ToolContext(task_id=task_id)
        return ToolContext(
            session_id=context.session_id,
            task_id=task_id,
            metadata=dict(context.metadata),
        )

    @staticmethod
    def _resolve_verification_commands(metadata: dict[str, Any]) -> list[str]:
        raw_candidates = metadata.get("verification_commands")
        if not (isinstance(raw_candidates, list) and raw_candidates):
            raw_candidates = metadata.get("default_verification_commands")
        if not (isinstance(raw_candidates, list) and raw_candidates):
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

    @staticmethod
    def _extract_orchestration_output(orchestration: dict[str, Any]) -> str:
        outputs = orchestration.get("outputs", {})
        if isinstance(outputs, dict):
            for phase in (AUTOFIX_ROLE, IMPLEMENTER_ROLE, REVIEWER_ROLE, PLANNER_ROLE):
                payload = outputs.get(phase)
                if not isinstance(payload, dict):
                    continue
                for key in ("final_output", "summary", "content"):
                    value = payload.get(key)
                    if value is None:
                        continue
                    text = str(value).strip()
                    if text:
                        return text
        return f"Orchestration status: {orchestration.get('status', 'unknown')}"

    @staticmethod
    def _should_use_orchestrator(metadata: dict[str, Any], commands: list[str]) -> bool:
        _ = metadata, commands
        # Orchestration is mandatory for all task paths.
        return True

    async def _run_executor(self, *, task: ManagedTask, context: ToolContext) -> dict[str, Any]:
        metadata = dict(context.metadata or {})
        commands = self._resolve_verification_commands(metadata)
        if self._should_use_orchestrator(metadata, commands):
            max_autofix_rounds = max(0, int(metadata.get("subagent_max_autofix_rounds", 1)))
            min_review_score = float(metadata.get("subagent_min_review_score", 80.0))
            orchestrator = SubagentOrchestrator(
                executor=self.executor,
                verification_runner=self.verification_runner,
                max_autofix_rounds=max_autofix_rounds,
                min_review_score=min_review_score,
            )
            orchestration = await orchestrator.run(
                prompt=task.prompt,
                context=context,
                verification_commands=commands,
            )
            phase_count = len(orchestration.get("phases", []))
            return {
                "status": str(orchestration.get("status", "failed")),
                "final_output": self._extract_orchestration_output(orchestration),
                "steps_completed": phase_count,
                "total_steps": phase_count,
                "tool_events": [],
                "orchestration": orchestration,
                "verification": orchestration.get("verification", {}),
            }
        return await self.executor.run(
            task_id=task.task_id,
            prompt=task.prompt,
            context=context,
        )

    async def _finalize_task_result(self, *, task_id: str, result: dict[str, Any]) -> ManagedTask:
        async with self._lock:
            task = self._tasks[task_id]
            status = str(result.get("status", "completed")).strip().lower()
            task.status = "failed" if status == "failed" else "completed"
            task.final_output = str(result.get("final_output") or f"Completed task: {task.prompt}")
            task.steps_completed = int(result.get("steps_completed", 1))
            task.total_steps = int(result.get("total_steps", task.steps_completed or 1))
            raw_tool_events = result.get("tool_events", [])
            task.tool_events = list(raw_tool_events) if isinstance(raw_tool_events, list) else []
            orchestration = result.get("orchestration")
            if isinstance(orchestration, dict):
                task.orchestration_status = str(orchestration.get("status", "")).strip() or None
                task.orchestration = dict(orchestration)
            verification = result.get("verification")
            task.verification = dict(verification) if isinstance(verification, dict) else None
            suffix = ""
            if task.orchestration_status:
                suffix = f" [orchestration_status={task.orchestration_status}]"
            await self._append_output(task, f"[{task.status}] {task.final_output}{suffix}")
            return task

    async def _run_background_task(self, task_id: str, context: ToolContext) -> None:
        async with self._lock:
            task = self._tasks[task_id]
            task.status = "running"
            await self._append_output(task, f"[start] {task.prompt}")

        try:
            async with self._lock:
                task = self._tasks[task_id]
                if task.stop_requested:
                    task.status = "stopped"
                    await self._append_output(task, "[stopped] stop requested")
                    return
            result = await self._run_executor(task=self._tasks[task_id], context=context)
            await self._finalize_task_result(task_id=task_id, result=result)
        except asyncio.CancelledError:
            async with self._lock:
                task = self._tasks[task_id]
                task.status = "stopped"
                await self._append_output(task, "[stopped] cancelled")
            raise
        except Exception as exc:  # pragma: no cover - defensive background path
            async with self._lock:
                task = self._tasks[task_id]
                task.status = "failed"
                await self._append_output(task, f"[failed] {exc}")

    async def launch(
        self,
        *,
        prompt: str,
        run_in_background: bool,
        context: ToolContext | None,
        name: str | None = None,
        model: str | None = None,
        subagent_type: str | None = None,
        isolation: str | None = None,
    ) -> dict[str, Any]:
        root = self._resolve_root(context)
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        agent_id = f"agent-{uuid.uuid4().hex[:12]}"
        output_file = root / f"{task_id}.log"
        task_name = name or subagent_type or "general-purpose"
        managed = ManagedTask(
            task_id=task_id,
            agent_id=agent_id,
            name=task_name,
            prompt=prompt,
            status="running" if run_in_background else "pending",
            output_file=output_file,
            model=model,
            subagent_type=subagent_type,
            isolation=isolation,
            store_root=self._resolve_store_root(context),
        )

        async with self._lock:
            self._tasks[task_id] = managed
            self._agent_to_task[agent_id] = task_id
            managed.output_file.parent.mkdir(parents=True, exist_ok=True)
            managed.output_file.touch(exist_ok=True)
            self._persist_task_state(managed)

        task_context = self._copy_context_for_task(context, task_id=task_id)
        if run_in_background:
            background_task = asyncio.create_task(self._run_background_task(task_id, task_context))
            async with self._lock:
                managed.background_task = background_task
            return {
                "status": "async_launched",
                "task_id": task_id,
                "agent_id": agent_id,
                "name": task_name,
                "output_file": str(output_file),
            }

        await self._run_background_task(task_id, task_context)
        async with self._lock:
            managed = self._tasks[task_id]
        return {
            "status": managed.status,
            "task_id": task_id,
            "agent_id": agent_id,
            "name": task_name,
            "output_file": str(output_file),
            "output": managed.final_output,
            "steps_completed": managed.steps_completed,
            "total_steps": managed.total_steps,
            "tool_events": managed.tool_events,
            "orchestration_status": managed.orchestration_status,
            "verification": managed.verification,
            "orchestration": managed.orchestration,
        }

    async def _resolve_task(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        context: ToolContext | None = None,
    ) -> ManagedTask:
        resolved_task_id = task_id
        if resolved_task_id is None and agent_id is not None:
            resolved_task_id = self._agent_to_task.get(agent_id)
        if resolved_task_id is None or resolved_task_id not in self._tasks:
            await self._restore_tasks_from_store(context)
            if resolved_task_id is None and agent_id is not None:
                resolved_task_id = self._agent_to_task.get(agent_id)
        if resolved_task_id is None or resolved_task_id not in self._tasks:
            raise ValueError("Task not found")
        return self._tasks[resolved_task_id]

    async def attach_worktree(
        self,
        *,
        task_id: str,
        worktree_path: str,
        worktree_branch: str,
        worktree_session_id: str,
        context: ToolContext | None = None,
    ) -> None:
        _ = context
        async with self._lock:
            task = await self._resolve_task(task_id=task_id, context=None)
            task.worktree_path = str(worktree_path)
            task.worktree_branch = str(worktree_branch)
            task.worktree_session_id = str(worktree_session_id)
            self._persist_task_state(task)

    async def resume(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        context: ToolContext | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            task = await self._resolve_task(task_id=task_id, agent_id=agent_id, context=context)
            return {
                "status": "resumed",
                "task_id": task.task_id,
                "agent_id": task.agent_id,
                "task_status": task.status,
                "name": task.name,
                "output_file": str(task.output_file),
                "worktree_path": task.worktree_path,
                "worktree_branch": task.worktree_branch,
                "tool_events": task.tool_events,
                "orchestration_status": task.orchestration_status,
                "verification": task.verification,
                "orchestration": task.orchestration,
            }

    async def send_message(
        self,
        *,
        message: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        context: ToolContext | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            task = await self._resolve_task(task_id=task_id, agent_id=agent_id, context=context)
            if task.status not in {"running"}:
                return {
                    "delivered": False,
                    "task_id": task.task_id,
                    "agent_id": task.agent_id,
                    "status": task.status,
                }
            task.inbox.append(message)
            task.updated_at = _now_iso()
            await self._append_output(task, f"[message] {message}")
            return {
                "delivered": True,
                "task_id": task.task_id,
                "agent_id": task.agent_id,
                "status": task.status,
            }

    async def stop(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        context: ToolContext | None = None,
    ) -> dict[str, Any]:
        background_task: asyncio.Task[None] | None = None
        async with self._lock:
            task = await self._resolve_task(task_id=task_id, agent_id=agent_id, context=context)
            if task.status in {"completed", "failed", "stopped"}:
                return {
                    "stopped": False,
                    "task_id": task.task_id,
                    "agent_id": task.agent_id,
                    "status": task.status,
                }
            task.stop_requested = True
            task.status = "stopping"
            task.updated_at = _now_iso()
            background_task = task.background_task
            self._persist_task_state(task)

        if background_task is not None and not background_task.done():
            background_task.cancel()
            try:
                await background_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            task = await self._resolve_task(task_id=task_id, agent_id=agent_id, context=context)
            if task.status == "stopping":
                task.status = "stopped"
                await self._append_output(task, "[stopped] stop requested")
            return {
                "stopped": True,
                "task_id": task.task_id,
                "agent_id": task.agent_id,
                "status": task.status,
            }

    async def output(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        tail_lines: int | None = None,
        context: ToolContext | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            task = await self._resolve_task(task_id=task_id, agent_id=agent_id, context=context)
            output_file = task.output_file
            status = task.status
            created_at = task.created_at
            updated_at = task.updated_at
            steps_completed = task.steps_completed
            total_steps = task.total_steps

        if output_file.exists():
            text = output_file.read_text(encoding="utf-8")
        else:
            text = ""
        if tail_lines is not None and tail_lines > 0:
            lines = text.splitlines()
            text = "\n".join(lines[-tail_lines:])
            if text:
                text += "\n"
        return {
            "task_id": task.task_id,
            "agent_id": task.agent_id,
            "status": status,
            "output_file": str(output_file),
            "output": text,
            "created_at": created_at,
            "updated_at": updated_at,
            "steps_completed": steps_completed,
            "total_steps": total_steps,
            "worktree_path": task.worktree_path,
            "worktree_branch": task.worktree_branch,
            "tool_events": task.tool_events,
            "orchestration_status": task.orchestration_status,
            "verification": task.verification,
            "orchestration": task.orchestration,
        }
