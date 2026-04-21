# Python Agent Core Gap Closure (Core 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three highest-impact parity gaps: semantic refactor depth, real-model-only routing for code changes, and semantic memory retrieval quality.

**Architecture:** Deliver in three packages with strict TDD: (1) enforce real model path for all code-change tasks, (2) upgrade memory retrieval from token overlap to hybrid semantic ranking, (3) add hybrid refactor engine (LSP + structural fallback) for deeper cross-file refactors.

**Tech Stack:** Python 3.12, asyncio, pytest, existing QueryLoop/Subagent stack, existing LSP integration.

---

### Task 1: Enforce Real-Model-Only Routing for Code-Change Tasks

**Files:**
- Modify: `agent/subagents/model_client.py`
- Test: `tests/python_agent/test_subagent_model_client_real_backend.py`
- Test: `tests/python_agent/test_verification_gate_required.py`

- [x] **Step 1: Write failing tests for code-change strict model routing**

```python
def test_code_change_rejects_explicit_deterministic_backend() -> None:
    with pytest.raises(ValueError):
        SubagentModelClient(
            prompt="modify code",
            metadata={
                "is_code_change": True,
                "subagent_model_backend": "deterministic",
                "subagent_allow_mock_backend": True,
            },
        )
```

- [x] **Step 2: Run tests to verify fail**

Run: `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py -k "code_change or deterministic" -v`  
Expected: FAIL because deterministic backend is still allowed in some code-change paths.

- [x] **Step 3: Implement minimal strict routing**

Rules:
- If `is_code_change=true`, reject `subagent_model_backend in {deterministic, stub, none, disabled}` regardless of runtime profile.
- If `is_code_change=true` and no API key / real backend unavailable, keep hard failure (no silent fallback).
- Preserve deterministic path for non-code-change test harness flows.

- [x] **Step 4: Run regression tests**

Run: `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_verification_gate_required.py -v`  
Expected: PASS.

---

### Task 2: Upgrade Memory Retrieval to Hybrid Semantic Ranking

**Files:**
- Modify: `agent/memory/retrieval.py`
- Create: `tests/python_agent/test_memory_hybrid_retrieval.py`
- Test: `tests/python_agent/test_memory_semantic_retrieval.py`
- Test: `tests/python_agent/test_memory_retrieval_policy.py`

- [x] **Step 1: Write failing tests for semantic alias/paraphrase ranking**

```python
def test_hybrid_retrieval_ranks_semantic_match_above_keyword_noise() -> None:
    ...
```

- [x] **Step 2: Run tests to verify fail**

Run: `python -m pytest tests/python_agent/test_memory_hybrid_retrieval.py -v`  
Expected: FAIL on current token-overlap ranker.

- [x] **Step 3: Implement hybrid ranker**

Implementation scope:
- lexical overlap score
- char-ngram similarity score
- alias normalization score
- recency bonus
- weighted fusion + deterministic sort

- [x] **Step 4: Run regression tests**

Run: `python -m pytest tests/python_agent/test_memory_hybrid_retrieval.py tests/python_agent/test_memory_semantic_retrieval.py tests/python_agent/test_memory_retrieval_policy.py -v`  
Expected: PASS.

---

### Task 3: Hybrid Semantic Refactor Engine (LSP + Structural Fallback)

**Files:**
- Modify: `agent/semantic/index.py`
- Modify: `agent/tools/lsp_tool.py`
- Create: `agent/semantic/refactor_fallback.py`
- Create: `tests/python_agent/test_semantic_refactor_hybrid.py`
- Test: `tests/python_agent/test_semantic_lsp_navigation.py`

- [x] **Step 1: Write failing tests for deep refactor fallback**

```python
def test_extract_refactor_falls_back_when_lsp_action_missing() -> None:
    ...
```

- [x] **Step 2: Run tests to verify fail**

Run: `python -m pytest tests/python_agent/test_semantic_refactor_hybrid.py -v`  
Expected: FAIL because only LSP action path exists.

- [x] **Step 3: Implement minimal hybrid refactor fallback**

Implementation scope:
- when LSP code actions unavailable, attempt structured fallback for `extract/move/inline` (Python-first)
- keep explicit structured failure payload when neither path works
- preserve strict mode behavior

- [x] **Step 4: Run regression tests**

Run: `python -m pytest tests/python_agent/test_semantic_refactor_hybrid.py tests/python_agent/test_semantic_lsp_navigation.py -v`  
Expected: PASS.

---

### Final Acceptance Gate

- [x] **Step 1: Run targeted package suite**

Run: `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_verification_gate_required.py tests/python_agent/test_memory_hybrid_retrieval.py tests/python_agent/test_memory_semantic_retrieval.py tests/python_agent/test_memory_retrieval_policy.py tests/python_agent/test_semantic_refactor_hybrid.py tests/python_agent/test_semantic_lsp_navigation.py -v`

- [x] **Step 2: Run full suite**

Run: `python -m pytest tests/python_agent -q -rA`

- [x] **Step 3: Produce closure report**

Create: `docs/superpowers/reports/2026-04-18-python-agent-core3-gap-closure-report.md`
