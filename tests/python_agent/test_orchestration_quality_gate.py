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


class ProtocolInvalidReviewExecutor(SubagentExecutor):
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
            content = '{"steps":["edit service.py"],"risks":["regression"],"verification_focus":["pytest"]}'
        elif phase == "review":
            content = "review output without structured json"
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


class LowScoreReviewExecutor(SubagentExecutor):
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
            content = '{"steps":["edit service.py"],"risks":["regression"],"verification_focus":["pytest"]}'
        elif phase == "review":
            content = '{"verdict":"pass","score":60,"blocking_issues":[],"fix_plan":["add tests"]}'
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
async def test_orchestrator_blocks_when_review_protocol_invalid() -> None:
    orchestrator = SubagentOrchestrator(
        executor=ProtocolInvalidReviewExecutor(),
        verification_runner=SequenceVerificationRunner(["passed"]),
        max_autofix_rounds=0,
    )
    result = await orchestrator.run(
        prompt="improve service logic",
        context=ToolContext(session_id="session-quality-protocol-invalid"),
        verification_commands=["pytest -q"],
    )

    assert result["status"] == "failed"
    assert any(
        violation.get("reason") == "review_protocol_invalid"
        for violation in result.get("protocol_violations", [])
    )


@pytest.mark.asyncio
async def test_orchestrator_blocks_when_review_score_below_threshold_without_autofix_budget() -> None:
    orchestrator = SubagentOrchestrator(
        executor=LowScoreReviewExecutor(),
        verification_runner=SequenceVerificationRunner(["passed"]),
        max_autofix_rounds=0,
        min_review_score=80,
    )
    result = await orchestrator.run(
        prompt="improve service logic",
        context=ToolContext(session_id="session-quality-low-score"),
        verification_commands=["pytest -q"],
    )

    assert result["status"] == "failed"
    reasons = result.get("review_gate", {}).get("reasons", [])
    assert any("score_below_threshold" in str(reason) for reason in reasons)
