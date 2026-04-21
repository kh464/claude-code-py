# Python Agent Parity Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining capability gap so the Python agent can consistently match local Claude Code in "understand codebase and modify feature code" workflows.

**Architecture:** Execute in three priority lanes: P0 correctness and capability parity (real subagent runtime, semantic/LSP understanding, transactional edits, true parity harness, mandatory verification), P1 reliability for long-running sessions (token-accurate context, memory retrieval quality, resilient MCP transport, worktree recovery), and P2 intelligence orchestration (planner/reviewer/autofix loops and performance guardrails). Each task ships with hard regression tests and measurable acceptance criteria.

**Tech Stack:** Python 3.11+, asyncio, subprocess/git, pytest, JSONL/sqlite, LSP protocol client, tree-sitter (optional fallback), tokenizer adapter (`tiktoken` compatible)

---

## P0 Gap Tasks (Must-Have)

### Task 1 (P0): Real Subagent Runtime v2 (Multi-Turn, Tool-Using, Interruptible)

**Files:**
- Create: `agent/subagents/model_client.py`
- Modify: `agent/subagents/executor.py`
- Modify: `agent/subagents/task_manager.py`
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_subagent_runtime_v2.py`

- [ ] **Step 1: Write failing test for multi-turn subagent execution**

```python
@pytest.mark.asyncio
async def test_subagent_runtime_v2_runs_multi_turn_and_tools():
    result = await run_subagent_task(
        prompt="Read file, edit file, then summarize",
        run_in_background=False,
    )
    assert result["steps_completed"] >= 2
    assert result["tool_events"]
    assert result["final_output"]
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_subagent_runtime_v2.py -v`  
Expected: FAIL because current executor is single-turn echo behavior.

- [ ] **Step 3: Implement runtime v2 in executor**

```python
class SubagentModelClient:
    async def generate(self, messages: list[dict], tools: list[str]) -> dict: ...

class SubagentExecutor:
    async def run(self, *, task_id: str, prompt: str, context: ToolContext) -> dict:
        # run QueryLoop with real model adapter, collect tool events, support interrupt signals
        ...
```

- [ ] **Step 4: Run task tests + regression**

Run: `python -m pytest tests/python_agent/test_subagent_runtime_v2.py tests/python_agent/test_subagent_executor.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/subagents/model_client.py agent/subagents/executor.py agent/subagents/task_manager.py agent/tools/agent_tool.py tests/python_agent/test_subagent_runtime_v2.py
git commit -m "feat: upgrade subagent runtime to multi-turn tool-using execution"
```

### Task 2 (P0): Semantic Engine v2 with LSP-backed Definitions/References

**Files:**
- Create: `agent/semantic/lsp_client.py`
- Create: `agent/semantic/graph.py`
- Modify: `agent/semantic/index.py`
- Modify: `agent/tools/lsp_tool.py`
- Test: `tests/python_agent/test_semantic_lsp_navigation.py`

- [ ] **Step 1: Write failing tests for cross-file symbol and reference accuracy**

```python
def test_lsp_index_resolves_cross_file_references():
    result = semantic_find_symbol("UserService")
    assert len(result["definitions"]) == 1
    refs = semantic_find_references("UserService")
    assert len(refs) >= 3
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_semantic_lsp_navigation.py -v`  
Expected: FAIL with missing LSP-backed resolution behavior.

- [ ] **Step 3: Implement LSP client and semantic graph integration**

```python
class LSPClient:
    async def find_definitions(self, symbol: str, root: Path) -> list[dict]: ...
    async def find_references(self, symbol: str, root: Path) -> list[dict]: ...
```

- [ ] **Step 4: Run semantic tests + tool registry regression**

Run: `python -m pytest tests/python_agent/test_semantic_lsp_navigation.py tests/python_agent/test_semantic_navigation.py tests/python_agent/test_tool_registry.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/semantic/lsp_client.py agent/semantic/graph.py agent/semantic/index.py agent/tools/lsp_tool.py tests/python_agent/test_semantic_lsp_navigation.py
git commit -m "feat: add lsp-backed semantic navigation engine"
```

### Task 3 (P0): AST Transactional Structured Editing

**Files:**
- Create: `agent/editing/ast_engine.py`
- Create: `agent/editing/transactions.py`
- Modify: `agent/editing/engine.py`
- Modify: `agent/tools/file_edit_tool.py`
- Test: `tests/python_agent/test_ast_structured_edit_transactions.py`

- [ ] **Step 1: Write failing tests for atomic multi-edit and rollback**

```python
def test_ast_edit_transaction_rolls_back_on_conflict(tmp_path):
    file_path = tmp_path / "sample.py"
    file_path.write_text("def a():\n    return 1\n")
    with pytest.raises(ValueError):
        apply_transaction(file_path, edits=[...conflicting_edits...])
    assert "return 1" in file_path.read_text()
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_ast_structured_edit_transactions.py -v`  
Expected: FAIL with missing transactional AST edit behavior.

- [ ] **Step 3: Implement AST engine and transaction coordinator**

```python
class EditTransaction:
    def apply(self, edits: list[dict]) -> dict: ...
    def rollback(self) -> None: ...
```

- [ ] **Step 4: Run structured edit tests + file tool regression**

Run: `python -m pytest tests/python_agent/test_ast_structured_edit_transactions.py tests/python_agent/test_structured_edit_engine.py tests/python_agent/test_file_tools_real.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/editing/ast_engine.py agent/editing/transactions.py agent/editing/engine.py agent/tools/file_edit_tool.py tests/python_agent/test_ast_structured_edit_transactions.py
git commit -m "feat: add ast transactional editing with rollback safety"
```

### Task 4 (P0): True Parity Harness (Real Task Execution, Not Static Tagging)

**Files:**
- Create: `agent/parity/runner.py`
- Create: `agent/parity/report.py`
- Modify: `agent/parity/harness.py`
- Modify: `agent/parity/scenarios.py`
- Test: `tests/python_agent/test_parity_real_runner.py`

- [ ] **Step 1: Write failing test for real execution report artifacts**

```python
def test_parity_runner_executes_scenarios_and_emits_report(tmp_path):
    report = run_parity_suite(["single_file_fix"], report_path=tmp_path / "report.json")
    assert report["total"] == 1
    assert report["details"][0]["status"] in {"passed", "failed"}
    assert "duration_ms" in report["details"][0]
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_parity_real_runner.py -v`  
Expected: FAIL because harness currently evaluates static support tags.

- [ ] **Step 3: Implement runner-based harness flow**

```python
class ParityRunner:
    def execute(self, scenario: str) -> dict: ...
```

- [ ] **Step 4: Run parity tests**

Run: `python -m pytest tests/python_agent/test_parity_real_runner.py tests/python_agent/test_parity_harness.py tests/python_agent/test_parity_e2e.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/parity/runner.py agent/parity/report.py agent/parity/harness.py agent/parity/scenarios.py tests/python_agent/test_parity_real_runner.py
git commit -m "feat: convert parity harness to real scenario execution runner"
```

### Task 5 (P0): Mandatory Verification Gate for Code-Change Tasks

**Files:**
- Create: `agent/verification/policy.py`
- Modify: `agent/verification/runner.py`
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_verification_gate_required.py`

- [ ] **Step 1: Write failing test for required verification before completion**

```python
@pytest.mark.asyncio
async def test_code_change_task_without_verification_is_rejected():
    result = await run_agent_task(prompt="modify code", run_in_background=False)
    assert result["status"] == "blocked"
    assert "verification required" in result["reason"]
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_verification_gate_required.py -v`  
Expected: FAIL because verification is currently optional.

- [ ] **Step 3: Implement verification policy gate**

```python
def must_verify(prompt: str, metadata: dict) -> bool:
    return bool(metadata.get("is_code_change", True))
```

- [ ] **Step 4: Run verification and task flow regression**

Run: `python -m pytest tests/python_agent/test_verification_gate_required.py tests/python_agent/test_code_change_verification_loop.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/verification/policy.py agent/verification/runner.py agent/tools/agent_tool.py tests/python_agent/test_verification_gate_required.py
git commit -m "feat: enforce mandatory verification gate for code-change tasks"
```

---

## P1 Gap Tasks (Reliability)

### Task 6 (P1): Token-Accurate Context + Memory Retrieval + MCP Reliability Pack

**Files:**
- Modify: `agent/context/budget.py`
- Modify: `agent/context/compaction.py`
- Modify: `agent/memory/retrieval.py`
- Modify: `agent/query_loop.py`
- Modify: `agent/mcp_integration/transport.py`
- Modify: `agent/mcp_integration/manager.py`
- Test: `tests/python_agent/test_context_token_accuracy.py`
- Test: `tests/python_agent/test_memory_semantic_retrieval.py`
- Test: `tests/python_agent/test_mcp_reliability_pack.py`

- [ ] **Step 1: Write failing reliability tests (token accuracy + semantic memory + mcp retries)**

```python
def test_budget_uses_model_tokenizer_not_whitespace_estimator(): ...
def test_memory_retrieval_prefers_semantic_similarity_over_keyword_overlap(): ...
def test_mcp_retry_stops_on_non_retryable_classification(): ...
```

- [ ] **Step 2: Run tests to verify fail**

Run: `python -m pytest tests/python_agent/test_context_token_accuracy.py tests/python_agent/test_memory_semantic_retrieval.py tests/python_agent/test_mcp_reliability_pack.py -v`  
Expected: FAIL due to current heuristic implementations.

- [ ] **Step 3: Implement reliability pack**

```python
class TokenBudgetEstimator:
    def estimate(self, messages: list[dict]) -> int: ...

class MemoryRanker:
    def rank(self, query: str, entries: list[dict]) -> list[dict]: ...
```

- [ ] **Step 4: Run reliability tests + existing regressions**

Run: `python -m pytest tests/python_agent/test_context_token_accuracy.py tests/python_agent/test_memory_semantic_retrieval.py tests/python_agent/test_mcp_reliability_pack.py tests/python_agent/test_query_loop_token_budget.py tests/python_agent/test_memory_retrieval_policy.py tests/python_agent/test_mcp_transport_resilience.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/context/budget.py agent/context/compaction.py agent/memory/retrieval.py agent/query_loop.py agent/mcp_integration/transport.py agent/mcp_integration/manager.py tests/python_agent/test_context_token_accuracy.py tests/python_agent/test_memory_semantic_retrieval.py tests/python_agent/test_mcp_reliability_pack.py
git commit -m "feat: deliver token-accurate context, semantic memory, and mcp reliability pack"
```

### Task 7 (P1): Worktree Recovery and Garbage Collection Pack

**Files:**
- Create: `agent/workspace_isolation/recovery.py`
- Modify: `agent/workspace_isolation/git_worktree.py`
- Modify: `agent/workspace_isolation/worktree.py`
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_worktree_recovery_gc.py`

- [ ] **Step 1: Write failing tests for crash recovery and stale worktree cleanup**

```python
def test_worktree_recovery_rebinds_running_task_after_restart(): ...
def test_worktree_gc_removes_stale_entries_without_active_sessions(): ...
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_worktree_recovery_gc.py -v`  
Expected: FAIL because recovery/GC policies are not implemented.

- [ ] **Step 3: Implement recovery + GC logic**

```python
def recover_worktree_sessions(store_root: Path) -> list[dict]: ...
def collect_stale_worktrees(root: Path, active_session_ids: set[str]) -> dict: ...
```

- [ ] **Step 4: Run worktree tests + regression**

Run: `python -m pytest tests/python_agent/test_worktree_recovery_gc.py tests/python_agent/test_git_worktree_lifecycle.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/workspace_isolation/recovery.py agent/workspace_isolation/git_worktree.py agent/workspace_isolation/worktree.py agent/tools/agent_tool.py tests/python_agent/test_worktree_recovery_gc.py
git commit -m "feat: add worktree recovery and stale gc policies"
```

---

## P2 Gap Tasks (Intelligence/Experience)

### Task 8 (P2): Planner-Reviewer-Autofix Orchestration Pack

**Files:**
- Create: `agent/subagents/orchestrator.py`
- Create: `agent/subagents/roles.py`
- Modify: `agent/subagents/executor.py`
- Modify: `agent/subagents/task_manager.py`
- Modify: `agent/verification/runner.py`
- Test: `tests/python_agent/test_orchestration_autofix_loop.py`

- [ ] **Step 1: Write failing test for orchestration with auto-fix loop**

```python
@pytest.mark.asyncio
async def test_orchestrator_runs_plan_review_fix_verify_cycle():
    result = await run_orchestrated_task("implement feature with tests")
    assert result["phases"] == ["plan", "implement", "review", "verify"]
    assert result["verification"]["status"] == "passed"
```

- [ ] **Step 2: Run test to verify fail**

Run: `python -m pytest tests/python_agent/test_orchestration_autofix_loop.py -v`  
Expected: FAIL with missing orchestration components.

- [ ] **Step 3: Implement orchestrator and auto-fix retries**

```python
class SubagentOrchestrator:
    async def run(self, prompt: str, context: ToolContext) -> dict: ...
```

- [ ] **Step 4: Run orchestration tests + runtime regression**

Run: `python -m pytest tests/python_agent/test_orchestration_autofix_loop.py tests/python_agent/test_subagent_runtime_v2.py tests/python_agent/test_code_change_verification_loop.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/subagents/orchestrator.py agent/subagents/roles.py agent/subagents/executor.py agent/subagents/task_manager.py agent/verification/runner.py tests/python_agent/test_orchestration_autofix_loop.py
git commit -m "feat: add planner-reviewer-autofix orchestration flow"
```

---

## Final Validation and Publish

- [ ] **Step 1: Run full suite**

Run: `python -m pytest tests/python_agent -v`  
Expected: all tests PASS.

- [ ] **Step 2: Refresh parity report summary in docs**

Update:
- `README_PYTHON_AGENT.md`
- `docs/superpowers/specs/2026-04-15-python-full-tooling-agent-design.md` (progress notes section)

- [ ] **Step 3: Commit final integration batch**

```bash
git add README_PYTHON_AGENT.md docs/superpowers/specs/2026-04-15-python-full-tooling-agent-design.md
git commit -m "chore: publish parity gap-closure progress and final validation status"
```

---

## Plan Self-Review

1. **Spec coverage:** Includes all previously identified gap packages across P0/P1/P2: real subagent intelligence, semantic depth, transactional editing safety, real parity benchmarking, mandatory verification, context/memory/MCP reliability, worktree recovery, orchestration loop.
2. **Placeholder scan:** All tasks include explicit files, tests, commands, expected outcomes, and commit actions.
3. **Type consistency:** Uses existing project interfaces (`ToolContext`, `QueryLoop`, `ToolRuntime`, `MCPManager`, `TaskManager`) and extends them incrementally.

