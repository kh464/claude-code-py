from __future__ import annotations

import pytest

from agent.contracts import ToolContext
from agent.subagents.orchestrator import SubagentOrchestrator
from agent.subagents.executor import SubagentExecutor
from agent.verification.runner import VerificationRunner


class FakeExecutor(SubagentExecutor):
    async def run(self, *, task_id: str, prompt: str, context: ToolContext) -> dict:
        _ = task_id, context
        if "You are the planning phase." in prompt:
            content = '{"steps":["edit"],"risks":["regression"],"verification_focus":["tests"]}'
        elif "You are the reviewer phase." in prompt:
            content = '{"verdict":"pass","score":90,"blocking_issues":[],"fix_plan":[]}'
        else:
            content = f"executed: {prompt}"
        return {
            "final_output": content,
            "steps_completed": 1,
            "total_steps": 1,
            "tool_events": [],
            "transcript": [{"role": "assistant", "content": content}],
        }


class FakeVerificationRunner(VerificationRunner):
    async def run(self, *, workdir: str, commands: list[str]) -> dict:
        _ = workdir, commands
        return {
            "status": "passed",
            "workdir": ".",
            "results": [{"command": "pytest", "returncode": 0, "passed": True, "stdout": "", "stderr": ""}],
        }


@pytest.mark.asyncio
async def test_orchestrator_runs_plan_review_fix_verify_cycle() -> None:
    orchestrator = SubagentOrchestrator(
        executor=FakeExecutor(),
        verification_runner=FakeVerificationRunner(),
    )
    result = await orchestrator.run(
        prompt="implement feature with tests",
        context=ToolContext(session_id="session-orchestrator"),
        verification_commands=["pytest -q"],
    )

    assert result["phases"] == ["plan", "implement", "review", "verify"]
    assert result["verification"]["status"] == "passed"


class RecordingExecutor(SubagentExecutor):
    def __init__(self) -> None:
        self.phase_prompts: list[dict[str, str]] = []

    async def run_phase(
        self,
        *,
        phase: str,
        task_id: str,
        prompt: str,
        context: ToolContext,
    ) -> dict:
        _ = task_id, context
        self.phase_prompts.append({"phase": phase, "prompt": prompt})
        if phase == "plan":
            content = '{"steps":["edit"],"risks":["regression"],"verification_focus":["tests"]}'
        elif phase == "review":
            content = '{"verdict":"pass","score":90,"blocking_issues":[],"fix_plan":[]}'
        else:
            content = f"{phase}: {prompt}"
        return {
            "phase": phase,
            "final_output": content,
            "steps_completed": 1,
            "total_steps": 1,
            "tool_events": [],
            "transcript": [{"role": "assistant", "content": content}],
        }


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


class ReviewBlockingExecutor(SubagentExecutor):
    def __init__(self) -> None:
        self.review_calls = 0
        self.phase_calls: list[str] = []

    async def run_phase(
        self,
        *,
        phase: str,
        task_id: str,
        prompt: str,
        context: ToolContext,
    ) -> dict:
        _ = task_id, prompt, context
        self.phase_calls.append(phase)
        if phase == "plan":
            content = '{"steps":["edit"],"risks":["regression"],"verification_focus":["tests"]}'
            return {
                "phase": phase,
                "final_output": content,
                "steps_completed": 1,
                "total_steps": 1,
                "tool_events": [],
                "transcript": [{"role": "assistant", "content": content}],
            }
        if phase == "review":
            self.review_calls += 1
            if self.review_calls == 1:
                content = (
                    '{"verdict":"needs_changes","score":70,'
                    '"blocking_issues":["missing error handling"],'
                    '"fix_plan":["add guard rails"]}'
                )
            else:
                content = '{"verdict":"pass","score":90,"blocking_issues":[],"fix_plan":[]}'
            return {
                "phase": phase,
                "final_output": content,
                "steps_completed": 1,
                "total_steps": 1,
                "tool_events": [],
                "transcript": [{"role": "assistant", "content": content}],
            }
        return {
            "phase": phase,
            "final_output": f"{phase} done",
            "steps_completed": 1,
            "total_steps": 1,
            "tool_events": [],
            "transcript": [{"role": "assistant", "content": f"{phase} done"}],
        }


class StructuredReviewExecutor(SubagentExecutor):
    def __init__(self) -> None:
        self.review_calls = 0

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
                '{"steps":["edit service.py","edit handler.py"],"risks":["regression"],'
                '"verification_focus":["tests"]}'
            )
        elif phase == "review":
            self.review_calls += 1
            if self.review_calls == 1:
                content = (
                    '{"verdict":"pass","score":62,'
                    '"blocking_issues":[],"fix_plan":["strengthen tests"]}'
                )
            else:
                content = (
                    '{"verdict":"pass","score":90,'
                    '"blocking_issues":[],"fix_plan":[]}'
                )
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
async def test_orchestrator_enriches_phase_prompts_and_rechecks_review_after_autofix() -> None:
    executor = RecordingExecutor()
    verifier = SequenceVerificationRunner(["failed", "passed"])
    orchestrator = SubagentOrchestrator(
        executor=executor,
        verification_runner=verifier,
        max_autofix_rounds=2,
    )

    result = await orchestrator.run(
        prompt="implement feature with tests",
        context=ToolContext(session_id="session-orchestrator-rich"),
        verification_commands=["pytest -q"],
    )

    assert result["status"] == "completed"
    assert result["phases"] == ["plan", "implement", "review", "verify", "autofix", "review", "verify"]

    prompts_by_phase: dict[str, list[str]] = {}
    for item in executor.phase_prompts:
        prompts_by_phase.setdefault(item["phase"], []).append(item["prompt"])

    assert "Task:" in prompts_by_phase["plan"][0]
    assert "Planner output" in prompts_by_phase["implement"][0]
    assert "Implementation output" in prompts_by_phase["review"][0]
    assert "Verification failures" in prompts_by_phase["autofix"][0]
    assert "pytest -q" in prompts_by_phase["autofix"][0]


@pytest.mark.asyncio
async def test_orchestrator_returns_decision_trace_for_autofix_loop() -> None:
    orchestrator = SubagentOrchestrator(
        executor=RecordingExecutor(),
        verification_runner=SequenceVerificationRunner(["failed", "failed"]),
        max_autofix_rounds=1,
    )
    result = await orchestrator.run(
        prompt="fix flaky tests",
        context=ToolContext(session_id="session-orchestrator-trace"),
        verification_commands=["pytest -q"],
    )

    assert result["status"] == "failed"
    assert "decision_trace" in result
    assert any(item.get("phase") == "verify" for item in result["decision_trace"])
    assert any(item.get("action") == "autofix" for item in result["decision_trace"])


@pytest.mark.asyncio
async def test_orchestrator_triggers_autofix_on_review_blocking_even_when_verify_passes() -> None:
    orchestrator = SubagentOrchestrator(
        executor=ReviewBlockingExecutor(),
        verification_runner=SequenceVerificationRunner(["passed", "passed"]),
        max_autofix_rounds=1,
    )
    result = await orchestrator.run(
        prompt="improve edge-case handling",
        context=ToolContext(session_id="session-orchestrator-review-blocking"),
        verification_commands=["pytest -q"],
    )

    assert result["status"] == "completed"
    assert result["phases"] == ["plan", "implement", "review", "verify", "autofix", "review", "verify"]
    assert any(item.get("action") == "autofix" for item in result["decision_trace"])


@pytest.mark.asyncio
async def test_orchestrator_uses_structured_review_score_gate() -> None:
    orchestrator = SubagentOrchestrator(
        executor=StructuredReviewExecutor(),
        verification_runner=SequenceVerificationRunner(["passed", "passed"]),
        max_autofix_rounds=1,
        min_review_score=80,
    )
    result = await orchestrator.run(
        prompt="refactor multi-file flow",
        context=ToolContext(session_id="session-orchestrator-structured-review"),
        verification_commands=["pytest -q"],
    )

    assert result["status"] == "completed"
    assert result["phases"] == ["plan", "implement", "review", "verify", "autofix", "review", "verify"]
    assert result["review_gate"]["score"] == 90.0
    assert result["review_gate"]["passed"] is True
    assert result["structured_outputs"]["plan"]["steps"]
    assert result["structured_outputs"]["review"]["score"] == 90
