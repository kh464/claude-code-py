from __future__ import annotations

import pytest

from agent.contracts import ToolContext
from agent.subagents.executor import SubagentExecutor
from agent.subagents.orchestrator import SubagentOrchestrator
from agent.verification.runner import VerificationRunner


class SequenceVerificationRunner(VerificationRunner):
    def __init__(self, statuses: list[str]) -> None:
        self._statuses = list(statuses)
        self.calls = 0

    async def run(self, *, workdir: str, commands: list[str]) -> dict:
        _ = workdir
        index = min(self.calls, len(self._statuses) - 1)
        self.calls += 1
        status = self._statuses[index]
        is_passed = status == "passed"
        return {
            "status": status,
            "workdir": ".",
            "results": [
                {
                    "command": commands[0] if commands else "pytest -q",
                    "returncode": 0 if is_passed else 1,
                    "passed": is_passed,
                    "stdout": "" if is_passed else "1 failed",
                    "stderr": "" if is_passed else "assert 2 == 3",
                }
            ],
        }


class MissingFileLevelPlannerExecutor(SubagentExecutor):
    async def run_phase(
        self,
        *,
        phase: str,
        task_id: str,
        prompt: str,
        context: ToolContext,
    ) -> dict:
        _ = task_id, prompt, context
        if phase == "plan":
            content = (
                '{"steps":["refactor shared orchestration flow"],'
                '"risks":["regression risk in downstream modules"],'
                '"verification_focus":["pytest"]}'
            )
        elif phase == "review":
            content = '{"verdict":"pass","score":92,"blocking_issues":[],"fix_plan":[]}'
        else:
            content = f"{phase} done"
        return {
            "phase": phase,
            "final_output": content,
            "steps_completed": 1,
            "total_steps": 1,
            "tool_events": [],
            "transcript": [{"role": "assistant", "content": content}],
        }


class UnmappedVerificationFocusExecutor(SubagentExecutor):
    async def run_phase(
        self,
        *,
        phase: str,
        task_id: str,
        prompt: str,
        context: ToolContext,
    ) -> dict:
        _ = task_id, prompt, context
        if phase == "plan":
            content = (
                '{"steps":["update service.py flow","update handler.py callsite"],'
                '"risks":["regression in handler branch"],'
                '"verification_focus":["manual exploratory review"]}'
            )
        elif phase == "review":
            content = '{"verdict":"pass","score":95,"blocking_issues":[],"fix_plan":[]}'
        else:
            content = f"{phase} done"
        return {
            "phase": phase,
            "final_output": content,
            "steps_completed": 1,
            "total_steps": 1,
            "tool_events": [],
            "transcript": [{"role": "assistant", "content": content}],
        }


class ValidCrossFilePlannerExecutor(SubagentExecutor):
    async def run_phase(
        self,
        *,
        phase: str,
        task_id: str,
        prompt: str,
        context: ToolContext,
    ) -> dict:
        _ = task_id, prompt, context
        if phase == "plan":
            content = (
                '{"steps":["edit service.py to migrate contract","edit handler.py to update callsite"],'
                '"risks":["regression in response schema adapters"],'
                '"verification_focus":["pytest regression tests","mypy type checks"]}'
            )
        elif phase == "review":
            content = '{"verdict":"pass","score":93,"blocking_issues":[],"fix_plan":[]}'
        else:
            content = f"{phase} done"
        return {
            "phase": phase,
            "final_output": content,
            "steps_completed": 1,
            "total_steps": 1,
            "tool_events": [],
            "transcript": [{"role": "assistant", "content": content}],
        }


@pytest.mark.asyncio
async def test_orchestrator_blocks_cross_file_plan_without_file_level_steps() -> None:
    orchestrator = SubagentOrchestrator(
        executor=MissingFileLevelPlannerExecutor(),
        verification_runner=SequenceVerificationRunner(["passed"]),
        max_autofix_rounds=0,
    )
    result = await orchestrator.run(
        prompt="refactor multi-file flow for billing pipeline",
        context=ToolContext(session_id="session-cross-file-missing-file-steps"),
        verification_commands=["pytest -q", "python -m mypy src"],
    )

    assert result["status"] == "failed"
    assert any(
        violation.get("reason") == "planner_missing_file_level_steps"
        for violation in result.get("protocol_violations", [])
    )


@pytest.mark.asyncio
async def test_orchestrator_blocks_cross_file_plan_with_unmapped_verification_focus() -> None:
    orchestrator = SubagentOrchestrator(
        executor=UnmappedVerificationFocusExecutor(),
        verification_runner=SequenceVerificationRunner(["passed"]),
        max_autofix_rounds=0,
    )
    result = await orchestrator.run(
        prompt="cross-file rename rollout for API handlers",
        context=ToolContext(session_id="session-cross-file-unmapped-focus"),
        verification_commands=["pytest -q", "python -m mypy src"],
    )

    assert result["status"] == "failed"
    assert any(
        violation.get("reason") == "planner_verification_focus_unmapped"
        for violation in result.get("protocol_violations", [])
    )


@pytest.mark.asyncio
async def test_orchestrator_accepts_valid_cross_file_planner_contract() -> None:
    orchestrator = SubagentOrchestrator(
        executor=ValidCrossFilePlannerExecutor(),
        verification_runner=SequenceVerificationRunner(["passed"]),
        max_autofix_rounds=0,
    )
    result = await orchestrator.run(
        prompt="refactor multi-file flow for checkout orchestration",
        context=ToolContext(session_id="session-cross-file-valid"),
        verification_commands=["pytest -q", "python -m mypy src"],
    )

    assert result["status"] == "completed"
    assert result["review_gate"]["passed"] is True
