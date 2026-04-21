# Python Agent Core3 Gap Closure Report (2026-04-18)

## Scope
- Plan executed: `docs/superpowers/plans/2026-04-18-python-agent-gap-closure-core3.md`
- Goal: close 3 core gaps
  - real-model-only route for code-change tasks
  - hybrid semantic memory retrieval
  - hybrid semantic refactor (LSP + fallback)

## Completed Work

### 1) Real-Model-Only for Code-Change
- Updated: `agent/subagents/model_client.py`
- Added/updated tests:
  - `tests/python_agent/test_subagent_model_client_real_backend.py`
  - `tests/python_agent/test_verification_gate_required.py`
- Result:
  - code-change task now rejects mock backends (`deterministic/stub/none/disabled`) even in test profile
  - non-code-change deterministic test flows are still preserved

### 2) Hybrid Memory Retrieval
- Updated: `agent/memory/retrieval.py`
- Added tests: `tests/python_agent/test_memory_hybrid_retrieval.py`
- Result:
  - retrieval now uses hybrid ranking (lexical overlap + ngram semantic signal + alias normalization + recency bonus)
  - semantic/paraphrase retrieval quality improved while keeping deterministic behavior

### 3) Hybrid Semantic Refactor (LSP + Fallback)
- Added: `agent/semantic/refactor_fallback.py`
- Updated: `agent/semantic/index.py`
- Updated: `agent/tools/lsp_tool.py`
- Added tests: `tests/python_agent/test_semantic_refactor_hybrid.py`
- Result:
  - when LSP has no usable code action (or no edit), `apply_refactor` now attempts semantic fallback
  - `extract` has Python-first executable fallback
  - `inline` has Python-first executable fallback (single-file, simple return-expression function shape)
  - `move` now has Python-first executable fallback (cross-file top-level function move via `target_path`)
  - move path includes syntax validation + atomic write rollback on failure
  - strict mode behavior for LSP transport errors remains intact

## Verification Evidence

### Task 3 Regression
- Command:
  - `python -m pytest tests/python_agent/test_semantic_refactor_hybrid.py tests/python_agent/test_semantic_lsp_navigation.py -v`
- Result:
  - `11 passed`

### Targeted Acceptance Suite
- Command:
  - `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_verification_gate_required.py tests/python_agent/test_memory_hybrid_retrieval.py tests/python_agent/test_memory_semantic_retrieval.py tests/python_agent/test_memory_retrieval_policy.py tests/python_agent/test_semantic_refactor_hybrid.py tests/python_agent/test_semantic_lsp_navigation.py -v`
- Result:
  - `26 passed`

### Full Python-Agent Suite
- Command:
  - `python -m pytest tests/python_agent -q -rA`
- Result:
  - full suite green (all tests in `tests/python_agent` passed)

## Remaining Delta (Honest Status)
- `move` fallback currently targets top-level Python function moves and requires explicit `target_path`; broader symbol/class/method move semantics remain to be expanded.
- Therefore this closes Core3 plan acceptance, but not the full deep semantic refactor parity ceiling.
