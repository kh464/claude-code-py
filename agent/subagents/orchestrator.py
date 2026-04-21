from __future__ import annotations

import json
import re
import uuid
from typing import Any

from agent.contracts import ToolContext
from agent.subagents.executor import SubagentExecutor
from agent.subagents.roles import AUTOFIX_ROLE, DEFAULT_PHASES, IMPLEMENTER_ROLE, PLANNER_ROLE, REVIEWER_ROLE, VERIFIER_ROLE
from agent.verification.runner import VerificationRunner


class SubagentOrchestrator:
    def __init__(
        self,
        *,
        executor: SubagentExecutor,
        verification_runner: VerificationRunner,
        max_autofix_rounds: int = 1,
        min_review_score: float = 80.0,
    ) -> None:
        self.executor = executor
        self.verification_runner = verification_runner
        self.max_autofix_rounds = max(0, int(max_autofix_rounds))
        self.min_review_score = max(0.0, min(100.0, float(min_review_score)))

    async def _run_phase(self, *, phase: str, prompt: str, context: ToolContext) -> dict[str, Any]:
        task_id = f"{phase}-{uuid.uuid4().hex[:8]}"
        return await self.executor.run_phase(phase=phase, task_id=task_id, prompt=prompt, context=context)

    @staticmethod
    def _summarize_phase_output(output: dict[str, Any] | None) -> str:
        if not isinstance(output, dict):
            return ""
        for key in ("final_output", "content", "summary"):
            value = output.get(key)
            if value is not None:
                text = str(value).strip()
                if text:
                    return text
        transcript = output.get("transcript")
        if isinstance(transcript, list):
            for message in reversed(transcript):
                if not isinstance(message, dict):
                    continue
                if str(message.get("role")) != "assistant":
                    continue
                content = str(message.get("content", "")).strip()
                if content:
                    return content
        return ""

    @staticmethod
    def _review_requests_changes(review_output: dict[str, Any] | None) -> bool:
        summary = SubagentOrchestrator._summarize_phase_output(review_output).lower()
        if not summary:
            return False
        negative_markers = (
            "needs change",
            "needs changes",
            "must fix",
            "blocking issue",
            "[blocking]",
            "critical",
            "review_failed",
            "verification failed",
            "not pass",
            "does not pass",
        )
        return any(marker in summary for marker in negative_markers)

    @staticmethod
    def _format_verification_failures(verification: dict[str, Any] | None) -> str:
        if not isinstance(verification, dict):
            return ""
        results = verification.get("results", [])
        if not isinstance(results, list):
            return ""
        chunks: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            if bool(item.get("passed")):
                continue
            command = str(item.get("command", "")).strip() or "<unknown>"
            returncode = int(item.get("returncode", 1))
            stdout = str(item.get("stdout", "")).strip()
            stderr = str(item.get("stderr", "")).strip()
            section = [f"- command: {command}", f"  returncode: {returncode}"]
            if stdout:
                section.append(f"  stdout: {stdout[:280]}")
            if stderr:
                section.append(f"  stderr: {stderr[:280]}")
            chunks.append("\n".join(section))
        return "\n".join(chunks)

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        stripped = str(text).strip()
        if not stripped:
            return None
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            return loaded

        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.DOTALL)
        if fenced:
            try:
                loaded = json.loads(fenced.group(1))
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                return loaded

        object_match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if object_match:
            try:
                loaded = json.loads(object_match.group(0))
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                return loaded
        return None

    @staticmethod
    def _normalize_str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        output: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                output.append(text)
        return output

    @staticmethod
    def _is_cross_file_task(prompt: str) -> bool:
        text = str(prompt).strip().lower()
        markers = (
            "multi-file",
            "cross-file",
            "across files",
            "across modules",
            "multiple files",
            "multi module",
            "multi-module",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_file_level_step(step: str) -> bool:
        text = str(step).strip().lower()
        if not text:
            return False
        if re.search(r"[a-z0-9_\-./\\]+\.(py|ts|tsx|js|jsx|json|yaml|yml|md)\b", text):
            return True
        if any(token in text for token in ("/", "\\")):
            return True
        return False

    @staticmethod
    def _focus_matches_verification_command(focus_item: str, command: str) -> bool:
        focus = str(focus_item).strip().lower()
        cmd = str(command).strip().lower()
        if not focus or not cmd:
            return False
        if focus in cmd:
            return True

        alias_groups = {
            "test": ("pytest", "test", "unittest", "tox", "nox"),
            "tests": ("pytest", "test", "unittest", "tox", "nox"),
            "regression": ("pytest", "test", "integration"),
            "lint": ("ruff", "flake8", "eslint", "lint", "pylint"),
            "type": ("mypy", "pyright", "tsc", "type"),
            "types": ("mypy", "pyright", "tsc", "type"),
            "build": ("build", "compile", "tsc"),
            "smoke": ("pytest", "test", "smoke"),
        }
        for keyword, aliases in alias_groups.items():
            if keyword in focus and any(alias in cmd for alias in aliases):
                return True

        focus_tokens = [token for token in re.split(r"[^a-z0-9]+", focus) if len(token) >= 4]
        if focus_tokens and any(token in cmd for token in focus_tokens):
            return True
        return False

    def _planner_contract_issues(
        self,
        *,
        planner_payload: dict[str, Any],
        user_prompt: str,
        verification_commands: list[str],
    ) -> list[str]:
        issues: list[str] = []
        steps = self._normalize_str_list(planner_payload.get("steps", []))
        risks = self._normalize_str_list(planner_payload.get("risks", []))
        verification_focus = self._normalize_str_list(planner_payload.get("verification_focus", []))
        if not steps:
            issues.append("planner_missing_steps")
        if verification_commands and not verification_focus:
            issues.append("planner_missing_verification_focus")

        if not self._is_cross_file_task(user_prompt):
            return issues

        if not any(self._is_file_level_step(step) for step in steps):
            issues.append("planner_missing_file_level_steps")
        if not any("regression" in risk.lower() for risk in risks):
            issues.append("planner_missing_regression_risk")
        if verification_commands and verification_focus:
            mapped = all(
                any(
                    self._focus_matches_verification_command(focus_item=focus, command=command)
                    for command in verification_commands
                )
                for focus in verification_focus
            )
            if not mapped:
                issues.append("planner_verification_focus_unmapped")
        return issues

    def _parse_structured_output(self, *, phase: str, output: dict[str, Any] | None) -> dict[str, Any] | None:
        text = self._summarize_phase_output(output)
        payload = self._extract_json_object(text)
        if not isinstance(payload, dict):
            return None

        if phase == PLANNER_ROLE:
            steps = self._normalize_str_list(payload.get("steps", payload.get("plan_steps", [])))
            risks = self._normalize_str_list(payload.get("risks", []))
            verification_focus = self._normalize_str_list(
                payload.get("verification_focus", payload.get("verificationFocus", []))
            )
            if not (steps or risks or verification_focus):
                return None
            return {
                "steps": steps,
                "risks": risks,
                "verification_focus": verification_focus,
            }
        if phase == REVIEWER_ROLE:
            verdict = str(payload.get("verdict", payload.get("status", "pass"))).strip().lower() or "pass"
            raw_score = payload.get("score", payload.get("quality_score", 100))
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                score = 100.0
            if 0.0 <= score <= 1.0:
                score *= 100.0
            score = max(0.0, min(100.0, score))
            blocking_issues = self._normalize_str_list(payload.get("blocking_issues", payload.get("issues", [])))
            fix_plan = self._normalize_str_list(payload.get("fix_plan", payload.get("next_actions", [])))
            return {
                "verdict": verdict,
                "score": int(round(score)),
                "blocking_issues": blocking_issues,
                "fix_plan": fix_plan,
            }
        return payload

    def _evaluate_review_gate(
        self,
        *,
        review_output: dict[str, Any] | None,
        structured_review: dict[str, Any] | None,
    ) -> dict[str, Any]:
        _ = review_output
        if not isinstance(structured_review, dict):
            return {
                "passed": False,
                "verdict": "protocol_invalid",
                "score": 0.0,
                "min_review_score": round(self.min_review_score, 2),
                "blocking_issues": ["review protocol invalid"],
                "reasons": ["review_protocol_invalid"],
            }
        verdict = str(structured_review.get("verdict", "pass")).strip().lower() or "pass"
        raw_score = structured_review.get("score", 100)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(100.0, score))
        blocking_issues = self._normalize_str_list(structured_review.get("blocking_issues", []))
        verdict_blocking = verdict in {"fail", "failed", "needs_changes", "needs-change", "blocking"}
        score_blocking = score < self.min_review_score
        passed = not (verdict_blocking or bool(blocking_issues) or score_blocking)
        reasons: list[str] = []
        if verdict_blocking:
            reasons.append(f"verdict={verdict}")
        if blocking_issues:
            reasons.append("blocking_issues_present")
        if score_blocking:
            reasons.append(f"score_below_threshold({score:.1f}<{self.min_review_score:.1f})")

        return {
            "passed": passed,
            "verdict": verdict,
            "score": round(score, 2),
            "min_review_score": round(self.min_review_score, 2),
            "blocking_issues": blocking_issues,
            "reasons": reasons,
        }

    @staticmethod
    def _failed_result(
        *,
        phases: list[str],
        verification: dict[str, Any],
        phase_outputs: dict[str, Any],
        phase_history: list[dict[str, Any]],
        decision_trace: list[dict[str, Any]],
        structured_outputs: dict[str, dict[str, Any]],
        review_gate: dict[str, Any],
        protocol_violations: list[dict[str, str]],
        autofix_round: int,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "phases": phases,
            "verification": verification,
            "outputs": phase_outputs,
            "structured_outputs": structured_outputs,
            "review_gate": review_gate,
            "protocol_violations": protocol_violations,
            "phase_history": phase_history,
            "decision_trace": decision_trace,
            "autofix_rounds_used": autofix_round,
        }

    def _build_phase_prompt(
        self,
        *,
        phase: str,
        user_prompt: str,
        planner_output: dict[str, Any] | None,
        implement_output: dict[str, Any] | None,
        review_output: dict[str, Any] | None,
        verification: dict[str, Any] | None,
        verification_commands: list[str],
        autofix_round: int,
    ) -> str:
        planner_summary = self._summarize_phase_output(planner_output) or "No planner output yet."
        implement_summary = self._summarize_phase_output(implement_output) or "No implementation output yet."
        review_summary = self._summarize_phase_output(review_output) or "No review output yet."
        verify_failures = self._format_verification_failures(verification) or "No verification failure details."
        commands_section = ", ".join(verification_commands) if verification_commands else "<none>"

        if phase == PLANNER_ROLE:
            return (
                "You are the planning phase.\n"
                f"Task: {user_prompt}\n"
                "Return strict JSON only.\n"
                'Schema: {"steps":[string], "risks":[string], "verification_focus":[string]}\n'
                "Deliverables:\n"
                "- concise implementation steps\n"
                "- risk list\n"
                "- verification focus\n"
                "- For multi-file/cross-file tasks, include file-level steps (e.g. service.py, handler.py),\n"
                "  at least one regression risk, and verification_focus items that map to verification commands.\n"
            )
        if phase == IMPLEMENTER_ROLE:
            return (
                "You are the implementation phase.\n"
                f"Task: {user_prompt}\n"
                f"Planner output:\n{planner_summary}\n"
                "Implement the requested changes and summarize what changed."
            )
        if phase == REVIEWER_ROLE:
            return (
                "You are the reviewer phase.\n"
                f"Task: {user_prompt}\n"
                f"Planner output:\n{planner_summary}\n"
                f"Implementation output:\n{implement_summary}\n"
                "Review for correctness, regressions, and missing tests.\n"
                "Return strict JSON only.\n"
                'Schema: {"verdict":"pass|needs_changes|fail", "score":0-100, '
                '"blocking_issues":[string], "fix_plan":[string]}'
            )
        if phase == AUTOFIX_ROLE:
            return (
                "You are the autofix phase.\n"
                f"Task: {user_prompt}\n"
                f"Autofix round: {autofix_round + 1}\n"
                f"Planner output:\n{planner_summary}\n"
                f"Reviewer output:\n{review_summary}\n"
                f"Verification commands: {commands_section}\n"
                f"Verification failures:\n{verify_failures}\n"
                "Apply minimal, targeted fixes to resolve blocking review items and verification failures."
            )
        return user_prompt

    @staticmethod
    def _is_verification_failed(verification: dict[str, Any] | None) -> bool:
        if not isinstance(verification, dict):
            return True
        status = str(verification.get("status", "")).strip().lower()
        return status not in {"passed", "skipped"}

    async def run(
        self,
        *,
        prompt: str,
        context: ToolContext,
        verification_commands: list[str] | None = None,
    ) -> dict[str, Any]:
        phases: list[str] = []
        phase_outputs: dict[str, Any] = {}
        decision_trace: list[dict[str, Any]] = []
        phase_history: list[dict[str, Any]] = []
        protocol_violations: list[dict[str, str]] = []
        structured_outputs: dict[str, dict[str, Any]] = {}
        commands = [str(command) for command in (verification_commands or []) if str(command).strip()]
        workdir = str(context.metadata.get("current_cwd", ".")) if context.metadata else "."
        planner_output: dict[str, Any] | None = None
        implement_output: dict[str, Any] | None = None
        review_output: dict[str, Any] | None = None
        verification: dict[str, Any] | None = None
        review_gate = {
            "passed": True,
            "verdict": "pass",
            "score": 100.0,
            "min_review_score": round(self.min_review_score, 2),
            "blocking_issues": [],
            "reasons": [],
        }

        for phase in DEFAULT_PHASES:
            phases.append(phase)
            if phase == VERIFIER_ROLE:
                verification = await self.verification_runner.run(workdir=workdir, commands=commands)
                phase_outputs[phase] = verification
                phase_history.append({"phase": phase, "output": verification})
                decision_trace.append(
                    {
                        "phase": phase,
                        "action": "verify",
                        "status": verification.get("status"),
                    }
                )
                continue

            phase_prompt = self._build_phase_prompt(
                phase=phase,
                user_prompt=prompt,
                planner_output=planner_output,
                implement_output=implement_output,
                review_output=review_output,
                verification=verification,
                verification_commands=commands,
                autofix_round=0,
            )
            output = await self._run_phase(phase=phase, prompt=phase_prompt, context=context)
            phase_outputs[phase] = output
            phase_history.append({"phase": phase, "output": output, "prompt": phase_prompt})
            structured = self._parse_structured_output(phase=phase, output=output)
            if phase == PLANNER_ROLE:
                if not isinstance(structured, dict):
                    protocol_violations.append({"phase": PLANNER_ROLE, "reason": "planner_protocol_invalid"})
                    decision_trace.append(
                        {
                            "phase": PLANNER_ROLE,
                            "action": "protocol_invalid",
                            "reason": "planner_protocol_invalid",
                        }
                    )
                    verification = {
                        "status": "skipped",
                        "workdir": workdir,
                        "results": [],
                        "reason": "planner protocol invalid",
                    }
                    return self._failed_result(
                        phases=phases,
                        verification=verification,
                        phase_outputs=phase_outputs,
                        phase_history=phase_history,
                        decision_trace=decision_trace,
                        structured_outputs=structured_outputs,
                        review_gate=review_gate,
                        protocol_violations=protocol_violations,
                        autofix_round=0,
                    )
                planner_issues = self._planner_contract_issues(
                    planner_payload=structured,
                    user_prompt=prompt,
                    verification_commands=commands,
                )
                if planner_issues:
                    for issue in planner_issues:
                        protocol_violations.append({"phase": PLANNER_ROLE, "reason": issue})
                    decision_trace.append(
                        {
                            "phase": PLANNER_ROLE,
                            "action": "protocol_invalid",
                            "reason": planner_issues[0],
                            "issues": list(planner_issues),
                        }
                    )
                    verification = {
                        "status": "skipped",
                        "workdir": workdir,
                        "results": [],
                        "reason": f"planner protocol invalid: {planner_issues[0]}",
                    }
                    return self._failed_result(
                        phases=phases,
                        verification=verification,
                        phase_outputs=phase_outputs,
                        phase_history=phase_history,
                        decision_trace=decision_trace,
                        structured_outputs=structured_outputs,
                        review_gate=review_gate,
                        protocol_violations=protocol_violations,
                        autofix_round=0,
                    )
                structured_outputs[phase] = structured
                planner_output = output
            elif phase == IMPLEMENTER_ROLE:
                implement_output = output
            elif phase == REVIEWER_ROLE:
                review_output = output
                if not isinstance(structured, dict):
                    protocol_violations.append({"phase": REVIEWER_ROLE, "reason": "review_protocol_invalid"})
                else:
                    structured_outputs[phase] = structured
                review_gate = self._evaluate_review_gate(
                    review_output=review_output,
                    structured_review=structured_outputs.get(REVIEWER_ROLE),
                )
                decision_trace.append(
                    {
                        "phase": REVIEWER_ROLE,
                        "action": "review_gate",
                        "passed": review_gate["passed"],
                        "score": review_gate["score"],
                        "reasons": list(review_gate["reasons"]),
                    }
                )

        verification = verification or {}
        autofix_round = 0
        while (
            (self._is_verification_failed(verification) or not bool(review_gate.get("passed", False)))
            and autofix_round < self.max_autofix_rounds
        ):
            phases.append(AUTOFIX_ROLE)
            decision_trace.append(
                {
                    "phase": AUTOFIX_ROLE,
                    "action": "autofix",
                    "trigger": "review_or_verification_failed",
                    "round": autofix_round + 1,
                    "review_passed": review_gate.get("passed"),
                    "review_score": review_gate.get("score"),
                    "verification_status": verification.get("status"),
                }
            )
            autofix_prompt = self._build_phase_prompt(
                phase=AUTOFIX_ROLE,
                user_prompt=prompt,
                planner_output=planner_output,
                implement_output=implement_output,
                review_output=review_output,
                verification=verification,
                verification_commands=commands,
                autofix_round=autofix_round,
            )
            autofix_output = await self._run_phase(
                phase=AUTOFIX_ROLE,
                prompt=autofix_prompt,
                context=context,
            )
            phase_outputs[AUTOFIX_ROLE] = autofix_output
            phase_history.append({"phase": AUTOFIX_ROLE, "output": autofix_output, "prompt": autofix_prompt})

            phases.append(REVIEWER_ROLE)
            review_prompt = self._build_phase_prompt(
                phase=REVIEWER_ROLE,
                user_prompt=prompt,
                planner_output=planner_output,
                implement_output=autofix_output,
                review_output=review_output,
                verification=verification,
                verification_commands=commands,
                autofix_round=autofix_round,
            )
            review_output = await self._run_phase(
                phase=REVIEWER_ROLE,
                prompt=review_prompt,
                context=context,
            )
            phase_outputs[REVIEWER_ROLE] = review_output
            phase_history.append({"phase": REVIEWER_ROLE, "output": review_output, "prompt": review_prompt})
            structured_review = self._parse_structured_output(phase=REVIEWER_ROLE, output=review_output)
            if not isinstance(structured_review, dict):
                protocol_violations.append({"phase": REVIEWER_ROLE, "reason": "review_protocol_invalid"})
            else:
                structured_outputs[REVIEWER_ROLE] = structured_review
            review_gate = self._evaluate_review_gate(
                review_output=review_output,
                structured_review=structured_outputs.get(REVIEWER_ROLE),
            )
            decision_trace.append(
                {
                    "phase": REVIEWER_ROLE,
                    "action": "review_gate",
                    "passed": review_gate["passed"],
                    "score": review_gate["score"],
                    "reasons": list(review_gate["reasons"]),
                    "after_autofix_round": autofix_round + 1,
                }
            )

            phases.append(VERIFIER_ROLE)
            verification = await self.verification_runner.run(workdir=workdir, commands=commands)
            phase_outputs[VERIFIER_ROLE] = verification
            phase_history.append({"phase": VERIFIER_ROLE, "output": verification})
            decision_trace.append(
                {
                    "phase": VERIFIER_ROLE,
                    "action": "verify",
                    "status": verification.get("status"),
                    "after_autofix_round": autofix_round + 1,
                }
            )
            autofix_round += 1

        if not bool(review_gate.get("passed", False)) and not self._is_verification_failed(verification):
            decision_trace.append(
                {
                    "phase": REVIEWER_ROLE,
                    "action": "review_gate_blocked",
                    "status": "failed",
                    "score": review_gate.get("score"),
                    "reasons": list(review_gate.get("reasons", [])),
                }
            )

        return {
            "status": "completed"
            if not self._is_verification_failed(verification) and bool(review_gate.get("passed", False))
            else "failed",
            "phases": phases,
            "verification": verification,
            "outputs": phase_outputs,
            "structured_outputs": structured_outputs,
            "review_gate": review_gate,
            "protocol_violations": protocol_violations,
            "phase_history": phase_history,
            "decision_trace": decision_trace,
            "autofix_rounds_used": autofix_round,
        }
