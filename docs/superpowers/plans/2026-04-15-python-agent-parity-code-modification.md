# Python Agent Parity (Code Modification) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Python agent reach near-production parity with local Claude Code for "understand project and modify feature code" workflows.

**Architecture:** Upgrade the current MVP in three layers: (1) execution fidelity (real subagent runtime + git worktree + robust MCP), (2) semantic coding intelligence (symbol graph/LSP + structured edits + safer patch orchestration), and (3) reliability loop (token-aware context management + automated verification + parity benchmark harness). Ship each layer with hard tests and measurable parity score improvements.

**Tech Stack:** Python 3.11+, asyncio, subprocess/git, sqlite/jsonl, pytest, tree-sitter or LSP protocol client, tokenization lib (`tiktoken`-compatible)

---

## Upgrade Note (2026-04-18)

For a stricter and achievable parity convergence path (with preflight, failure buckets, staged hard gates, and anti-false-positive scoring), use:

`docs/superpowers/plans/2026-04-18-python-agent-parity-achievable-convergence-plan.md`

---

## Execution Update (2026-04-18)

- [x] P0 scoring fidelity: failure bucket + missing-dimension no-default-credit 已落地并有测试
- [x] P0 preflight gate: `environment_blocked` 机制已落地并有测试
- [x] P3 realism pack: parity 场景扩展到 80，总体真实改码场景 >= 40，模板兜底占比 <= 10%
- [x] 全量回归：`python -m pytest tests/python_agent -q -rA` 通过
- [x] parity 连续 3 轮：`capability_success_rate=1.0`，`weighted_quality_score=0.9775`，`environment_failure_rate=0.0`
- [x] 最终报告：`docs/superpowers/reports/2026-04-18-python-agent-parity-achievable-final-report.md`

---

### Task 1: Build Parity Benchmark Harness

**Files:**
- Create: `agent/parity/__init__.py`
- Create: `agent/parity/harness.py`
- Create: `agent/parity/scenarios.py`
- Create: `tests/python_agent/test_parity_harness.py`

- [ ] **Step 1: Write failing test for scenario execution and score output**

```python
def test_parity_harness_reports_scores():
    result = run_parity_suite(["simple-edit"])
    assert "success_rate" in result
    assert result["total"] >= 1
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_parity_harness.py -v`  
Expected: FAIL with import/function missing.

- [ ] **Step 3: Implement minimal harness and fixed scenario schema**

```python
def run_parity_suite(scenarios: list[str]) -> dict:
    return {"total": len(scenarios), "success_rate": 0.0, "details": []}
```

- [ ] **Step 4: Run test to verify pass**

Run: `python -m pytest tests/python_agent/test_parity_harness.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/parity tests/python_agent/test_parity_harness.py
git commit -m "feat: add parity benchmark harness baseline"
```

### Task 2: Replace Simulated Subagent with Real Subagent Executor

**Files:**
- Create: `agent/subagents/executor.py`
- Modify: `agent/subagents/task_manager.py`
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_subagent_executor.py`

- [ ] **Step 1: Write failing test for real subagent execution lifecycle**

```python
async def test_subagent_executor_spawn_resume_stop():
    launched = await agent_tool_call({"prompt": "edit file", "run_in_background": True})
    resumed = await agent_tool_call({"resume_task_id": launched["task_id"]})
    assert resumed["status"] == "resumed"
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_subagent_executor.py -v`  
Expected: FAIL due to missing executor integration.

- [ ] **Step 3: Implement executor abstraction and wire task manager to run real query loops**

```python
class SubagentExecutor:
    async def run(self, *, task_id: str, prompt: str, context: ToolContext) -> dict: ...
```

- [ ] **Step 4: Run tests for executor and existing agent flow**

Run: `python -m pytest tests/python_agent/test_subagent_executor.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/subagents/executor.py agent/subagents/task_manager.py agent/tools/agent_tool.py tests/python_agent/test_subagent_executor.py
git commit -m "feat: run real subagent executor lifecycle"
```

### Task 3: Upgrade Worktree to Real Git Worktree Lifecycle

**Files:**
- Create: `agent/workspace_isolation/git_worktree.py`
- Modify: `agent/workspace_isolation/worktree.py`
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_git_worktree_lifecycle.py`

- [ ] **Step 1: Write failing tests for create/reuse/cleanup with git-backed worktree**

```python
def test_git_worktree_create_and_cleanup():
    session = manager.enter(...)
    result = manager.exit(action="auto", ...)
    assert "worktree/" in session["worktree_branch"]
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_git_worktree_lifecycle.py -v`  
Expected: FAIL, git integration missing.

- [ ] **Step 3: Implement git worktree adapter with safety checks**

```python
def create_git_worktree(repo_root: Path, slug: str) -> dict: ...
def remove_git_worktree(repo_root: Path, path: Path, branch: str) -> None: ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/python_agent/test_git_worktree_lifecycle.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/workspace_isolation tests/python_agent/test_git_worktree_lifecycle.py agent/tools/agent_tool.py
git commit -m "feat: add git-backed worktree lifecycle"
```

### Task 4: Add Semantic Navigation Layer (Symbols/References)

**Files:**
- Create: `agent/semantic/__init__.py`
- Create: `agent/semantic/index.py`
- Create: `agent/tools/lsp_tool.py`
- Modify: `agent/tools/builtin.py`
- Test: `tests/python_agent/test_semantic_navigation.py`

- [ ] **Step 1: Write failing tests for symbol lookup and reference resolution**

```python
def test_semantic_index_finds_symbol_definitions():
    result = semantic_find_symbol("UserService")
    assert result["definitions"]
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_semantic_navigation.py -v`  
Expected: FAIL with missing semantic layer.

- [ ] **Step 3: Implement semantic index and hook into LSPTool**

```python
class SemanticIndex:
    def find_symbol(self, name: str) -> list[dict]: ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/python_agent/test_semantic_navigation.py tests/python_agent/test_tool_registry.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/semantic agent/tools/lsp_tool.py agent/tools/builtin.py tests/python_agent/test_semantic_navigation.py
git commit -m "feat: add semantic navigation and lsp integration"
```

### Task 5: Add Structured Edit Engine (AST/Range-safe Patches)

**Files:**
- Create: `agent/editing/__init__.py`
- Create: `agent/editing/engine.py`
- Modify: `agent/tools/file_edit_tool.py`
- Test: `tests/python_agent/test_structured_edit_engine.py`

- [ ] **Step 1: Write failing tests for range-safe edits and rollback on mismatch**

```python
def test_structured_edit_rejects_drifted_range():
    with pytest.raises(ValueError):
        apply_structured_edit(...)
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_structured_edit_engine.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement structured edit engine and route FileEditTool through it**

```python
class StructuredEditEngine:
    def apply(self, file_path: Path, edit: dict) -> dict: ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/python_agent/test_structured_edit_engine.py tests/python_agent/test_file_tools_real.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/editing agent/tools/file_edit_tool.py tests/python_agent/test_structured_edit_engine.py
git commit -m "feat: add structured edit engine"
```

### Task 6: De-Stub High-Impact Tools for Code Modification Workflow

**Files:**
- Modify: `agent/tools/builtin.py`
- Create: `agent/tools/web_fetch_tool.py`
- Create: `agent/tools/web_search_tool.py`
- Create: `agent/tools/notebook_edit_tool.py`
- Test: `tests/python_agent/test_high_impact_tools_real.py`

- [ ] **Step 1: Write failing tests for real behavior of high-impact tools**

```python
def test_web_fetch_returns_content_and_status():
    result = web_fetch("https://example.com")
    assert "status_code" in result
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_high_impact_tools_real.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement real tool classes and replace static placeholders in builtin mapping**

```python
concrete_tools["WebFetchTool"] = WebFetchTool()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/python_agent/test_high_impact_tools_real.py tests/python_agent/test_tool_registry.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools tests/python_agent/test_high_impact_tools_real.py
git commit -m "feat: realize high-impact tooling beyond static stubs"
```

### Task 7: Productionize MCP Transport and Retry Policy

**Files:**
- Modify: `agent/mcp_integration/manager.py`
- Create: `agent/mcp_integration/transport.py`
- Modify: `agent/tools/mcp_tools.py`
- Test: `tests/python_agent/test_mcp_transport_resilience.py`

- [ ] **Step 1: Write failing tests for reconnect backoff and error classification**

```python
def test_mcp_retries_transient_errors_with_backoff():
    result = invoke_with_retry(...)
    assert result["attempts"] >= 2
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_mcp_transport_resilience.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement transport + retry strategy**

```python
async def invoke_with_retry(request: MCPRequest) -> MCPResponse: ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/python_agent/test_mcp_transport_resilience.py tests/python_agent/test_mcp_phase6.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/mcp_integration agent/tools/mcp_tools.py tests/python_agent/test_mcp_transport_resilience.py
git commit -m "feat: add resilient mcp transport and retries"
```

### Task 8: Token-Accurate Budgeting and Importance-Aware Compaction

**Files:**
- Modify: `agent/query_loop.py`
- Create: `agent/context/budget.py`
- Create: `agent/context/compaction.py`
- Test: `tests/python_agent/test_query_loop_token_budget.py`

- [ ] **Step 1: Write failing tests for token-based budget enforcement**

```python
def test_query_loop_uses_token_budget_not_char_budget():
    transcript = run_with_budget(max_tokens=200)
    assert transcript_has_compaction_marker(transcript)
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_query_loop_token_budget.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement budget estimator and compaction policy prioritizing**
: memory/system messages, latest tool_use/tool_result pairs, newest user intent.

```python
def compact_messages(messages: list[dict], max_tokens: int) -> list[dict]: ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/python_agent/test_query_loop_token_budget.py tests/python_agent/test_query_loop_context_management.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/context agent/query_loop.py tests/python_agent/test_query_loop_token_budget.py
git commit -m "feat: token-aware context budget and compaction"
```

### Task 9: Add Memory Store and Retrieval Policy for Long-Running Coding Sessions

**Files:**
- Create: `agent/memory/__init__.py`
- Create: `agent/memory/store.py`
- Create: `agent/memory/retrieval.py`
- Modify: `agent/query_loop.py`
- Test: `tests/python_agent/test_memory_retrieval_policy.py`

- [ ] **Step 1: Write failing tests for memory persistence and ranked retrieval**

```python
def test_memory_retrieval_returns_high_relevance_entries():
    results = memory_search("auth bug")
    assert results[0]["score"] >= results[-1]["score"]
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_memory_retrieval_policy.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement memory store + retrieval and inject top-k into context**

```python
class MemoryStore:
    def upsert(self, key: str, value: str) -> None: ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/python_agent/test_memory_retrieval_policy.py tests/python_agent/test_query_loop_context_management.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/memory agent/query_loop.py tests/python_agent/test_memory_retrieval_policy.py
git commit -m "feat: add long-session memory retrieval policy"
```

### Task 10: Automated Verification Loop for Code-Change Tasks

**Files:**
- Create: `agent/verification/__init__.py`
- Create: `agent/verification/runner.py`
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_code_change_verification_loop.py`

- [ ] **Step 1: Write failing test for post-edit verification gating**

```python
async def test_agent_requires_verification_before_complete():
    result = await run_agent_edit_task(...)
    assert result["verification"]["status"] in {"passed", "failed"}
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_code_change_verification_loop.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implement verification runner (lint/test/build command pipeline)**

```python
class VerificationRunner:
    async def run(self, workdir: str, commands: list[str]) -> dict: ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/python_agent/test_code_change_verification_loop.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/verification agent/tools/agent_tool.py tests/python_agent/test_code_change_verification_loop.py
git commit -m "feat: add automated verification loop for code changes"
```

### Task 11: End-to-End Parity Evaluation and Gap Burn-down

**Files:**
- Modify: `agent/parity/scenarios.py`
- Create: `tests/python_agent/test_parity_e2e.py`
- Modify: `README_PYTHON_AGENT.md`

- [ ] **Step 1: Add at least 30 representative code-modification scenarios**

```python
SCENARIOS = ["single_file_fix", "multi_file_refactor", "api_contract_update", ...]
```

- [ ] **Step 2: Run harness and capture baseline/final score**

Run: `python -m pytest tests/python_agent/test_parity_e2e.py -v`  
Expected: PASS with report artifact generated.

- [ ] **Step 3: Document remaining deltas and mitigation**

```markdown
## Parity Report
- success_rate: ...
- unresolved_gaps: ...
```

- [ ] **Step 4: Run full suite**

Run: `python -m pytest tests/python_agent`  
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/parity tests/python_agent/test_parity_e2e.py README_PYTHON_AGENT.md
git commit -m "chore: publish parity e2e report and remaining deltas"
```

---

## Plan Self-Review

1. **Spec coverage:** Covers execution fidelity, semantic understanding, tool realism, MCP robustness, context budget/compaction, memory injection/retrieval, and verification loop.
2. **Placeholder scan:** No TBD/TODO placeholders in task steps.
3. **Type consistency:** New modules and APIs use existing code style (`ToolContext`, `ToolRegistry`, `QueryLoop`, pytest async tests).

---

## Final Gap Closure Packages (P0/P1)

> Objective: close the remaining gap against local Claude Code on complex cross-file code understanding/modification quality and production-grade runtime fidelity.

### Package P0-1: Hard-Protocol Decision Quality Gate (Planner/Reviewer must be valid)

Status: Completed (2026-04-17)

**Goal:** Make structured planner/reviewer protocol a strict prerequisite for success, and block low-quality decisions before completion.

**Files:**
- Modify: `agent/subagents/orchestrator.py`
- Modify: `agent/subagents/task_manager.py`
- Test: `tests/python_agent/test_orchestration_autofix_loop.py`
- Test: `tests/python_agent/test_agent_task_flow.py`

- [x] **Step 1: Add failing tests for protocol-invalid and low-score blocking**

Run: `python -m pytest tests/python_agent/test_orchestration_autofix_loop.py -k "protocol_invalid or structured_review_score_gate" -v`  
Expected: FAIL for newly added strict gate assertions.

- [x] **Step 2: Implement hard fail path for invalid planner/reviewer schema and score threshold gate**

Key rule:
- Invalid planner schema -> task status must be `failed`.
- Invalid reviewer schema -> review gate must be `passed=False`.
- Reviewer score below `subagent_min_review_score` -> block completion.

- [x] **Step 3: Verify package**

Run: `python -m pytest tests/python_agent/test_orchestration_autofix_loop.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS.

---

### Package P0-2: Real-World Parity Harness (from synthetic patches to repo tasks)

Status: Completed (2026-04-17)
Progress now: real repo-task schema is in place, parity scenarios expanded to 50+ with 20 real repo-like tasks, and e2e parity quality dimensions are verified.

**Goal:** Upgrade parity from synthetic patch checks to real repository coding tasks with verification command outcomes.

**Files:**
- Modify: `agent/parity/scenarios.py`
- Modify: `agent/parity/runner.py`
- Modify: `agent/parity/report.py`
- Create: `tests/python_agent/test_parity_real_repo_tasks.py`
- Modify: `tests/python_agent/test_parity_e2e.py`

- [x] **Step 1: Add failing tests for real-task scenario execution and score dimensions**

Run: `python -m pytest tests/python_agent/test_parity_real_repo_tasks.py -v`  
Expected: FAIL with missing real-task fields (`verification_pass_rate`, `decision_quality_score`, `edit_correctness_score`).

- [x] **Step 2: Implement real-task scenario schema**

Required scenario fields:
- `workspace_template`
- `task_prompt`
- `verification_commands`
- `expected_artifacts` (diff fragments / test outcomes)
- `scoring_weights`

- [x] **Step 3: Raise baseline coverage target**

Target:
- At least 50 total scenarios.
- At least 20 real repo-like multi-file tasks.

- [x] **Step 4: Verify package**

Run: `python -m pytest tests/python_agent/test_parity_real_repo_tasks.py tests/python_agent/test_parity_e2e.py -v`  
Expected: PASS and report includes new quality dimensions.

---

### Package P0-3: Cross-File Orchestration Intelligence Uplift

Status: Completed (2026-04-18)
Progress now: cross-file planner contract is enforced (file-level steps, regression risk, verification_focus mapping), and dedicated quality tests are in place and passing.

**Goal:** Improve planner/reviewer/autofix decision quality on complex multi-file edits via explicit decomposition and risk-aware fix loops.

**Files:**
- Modify: `agent/subagents/orchestrator.py`
- Modify: `agent/subagents/prompts.py` (or equivalent prompt builder module)
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_orchestration_autofix_loop.py`
- Create: `tests/python_agent/test_orchestration_cross_file_quality.py`

- [x] **Step 1: Add failing tests for cross-file decomposition quality**

Run: `python -m pytest tests/python_agent/test_orchestration_cross_file_quality.py -v`  
Expected: FAIL due to missing mandatory decomposition/risk evidence in structured planner output.

- [x] **Step 2: Implement decomposition contract**

Required planner output fields:
- `steps` (must mention file-level actions)
- `risks` (must include at least one regression risk)
- `verification_focus` (must map to provided verification commands)

Required reviewer output fields:
- `verdict`, `score`, `blocking_issues`, `fix_plan` (already present; enforce consistency checks).

- [x] **Step 3: Verify package**

Run: `python -m pytest tests/python_agent/test_orchestration_autofix_loop.py tests/python_agent/test_orchestration_cross_file_quality.py -v`  
Expected: PASS.

---

### Package P1-1: LSP Deep Refactor Capability Matrix

Status: Completed (2026-04-17)

**Goal:** Move beyond basic rename/find/diagnostics by standardizing refactor capability detection and execution contracts for extract/move/class-level operations where server supports them.

**Files:**
- Modify: `agent/tools/lsp_tool.py`
- Modify: `agent/semantic/lsp_client.py`
- Modify: `agent/semantic/index.py`
- Create: `tests/python_agent/test_semantic_lsp_refactor_capabilities.py`

- [x] **Step 1: Add failing tests for capability introspection and refactor availability**

Run: `python -m pytest tests/python_agent/test_semantic_lsp_navigation.py::test_lsp_tool_reports_capabilities_and_normalized_refactor_kinds -v`  
Expected: FAIL with missing `capabilities` and normalized refactor kinds.

- [x] **Step 2: Implement capability matrix and normalized kinds**

Expose:
- `supported_operations`
- `supported_refactor_kinds`
- `strict_lsp_effective`

Normalize code-action kinds into stable buckets:
- `rename`, `extract`, `move`, `inline`, `organize_imports`, `other`.

- [x] **Step 3: Verify package**

Run: `python -m pytest tests/python_agent/test_semantic_lsp_navigation.py tests/python_agent/test_semantic_lsp_stdio_integration.py -v`  
Expected: PASS.

---

### Package P1-2: Production Profile Hardening (real model + real MCP by default)

Status: Completed (2026-04-17)

**Goal:** Keep tests/dev flexibility while making production profile strongly prefer real backends and explicitly reject mock/simulated modes unless allowlisted.

**Files:**
- Modify: `agent/subagents/model_client.py`
- Modify: `agent/mcp_integration/manager.py`
- Modify: `agent/config.py` (or equivalent runtime config module)
- Create: `tests/python_agent/test_production_profile_strictness.py`

- [x] **Step 1: Add failing tests for production strict profile**

Run: `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py::test_subagent_model_client_prod_profile_rejects_mock_backend_even_if_allowlisted tests/python_agent/test_mcp_phase6.py::test_mcp_prod_profile_rejects_simulated_modes -v`  
Expected: FAIL when profile guard is not enforced.

- [x] **Step 2: Implement profile-based guardrails**

Production profile (`PY_AGENT_PROFILE=prod`):
- reject `subagent_model_backend in {deterministic, stub, none, disabled}`.
- reject MCP tool mode `echo/constant` unless explicitly allowlisted per server.

Test profile (`PY_AGENT_PROFILE=test`):
- keep deterministic/simulated modes available for harness reliability.

- [x] **Step 3: Verify package**

Run: `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_mcp_phase6.py tests/python_agent/test_mcp_transport_resilience.py -v`  
Expected: PASS.

---

### Final Acceptance Gate (All Packages)

- [x] **Run full Python agent suite**

Run: `python -m pytest tests/python_agent -q -rA`  
Expected: all tests PASS.

- [x] **Run parity full suite and confirm quality fields present**

Run:
```bash
python - <<'PY'
from agent.parity.harness import run_parity_suite
from agent.parity.scenarios import SCENARIOS
r = run_parity_suite(SCENARIOS)
print("total", r["total"])
print("passed", r["passed"])
print("failed", r["failed"])
print("success_rate", r["success_rate"])
print("average_score", r["average_score"])
print("has_quality_dims", all("score" in d and "quality_metrics" in d for d in r["details"]))
PY
```
Expected: quality fields present and baseline metrics reported; pass rate used as parity gap indicator.

Latest run (2026-04-18): `total=52, passed=1, failed=51, success_rate=0.0192, average_score=0.0192`, quality fields complete.
