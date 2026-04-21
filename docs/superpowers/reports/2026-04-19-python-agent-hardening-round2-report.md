# Python Agent Hardening Round 2 Report (2026-04-19)

## Scope
- Continue parity hardening after Core3.
- Focus:
  - `move` semantic fallback executable path + safety
  - model backend deterministic path tightening
  - MCP simulated mode tightening

## Implemented

### 1) Move Fallback: Structured Failure -> Executable
- Added `target_path` input for refactor apply path:
  - `agent/tools/lsp_tool.py`
  - `agent/semantic/index.py`
- Implemented Python-first move fallback:
  - top-level function/class move from source file to target file
  - preserves decorator lines when moving decorated functions/classes
  - supports class `@staticmethod` move to top-level function:
    - strips `@staticmethod` in moved target block
    - rewrites `ClassName.method(...)` callsites to `method(...)` in source
    - inserts `pass` when class body becomes empty after method extraction
  - supports class `@classmethod` move to top-level function:
    - strips `@classmethod` in moved target block
    - rewrites `ClassName.method(...)` callsites to `method(...)` in source
    - removes leading `cls` parameter only when method body does not use class state
    - returns structured failure when class state is used (`move_classmethod_uses_cls_state`)
  - supports safe instance method move to top-level function:
    - rewrites `ClassName().method(...)` callsites to `method(...)` in source
    - rewrites `ClassName(args...).method(...)` callsites to `method(...)` in source
    - rewrites known instance-variable callsites where alias is constructed as `x = ClassName()`
    - supports local alias propagation such as `alias = svc` before `alias.method(...)`
    - supports simple local factory aliases where function body is a single safe return-path that yields constructor/factory calls (for example direct return, assignment-then-return, and simple `if/else` return branches)
    - supports transitive local factory wrappers (for example `make_service -> build_service -> ClassName(...)`)
    - local factory inference upgraded to safe intra-function dataflow:
      - supports multi-statement alias propagation (`a = factory(...)`; `b = a`; `return b`)
      - supports branch + alias merge patterns where all return paths remain factory-safe
      - supports parameter-passthrough wrappers (`relay(service): return service`) when call-site arguments are factory-safe
      - supports chained passthrough wrappers (`relay_a(x): return relay_b(x)`) via iterative wrapper inference
      - supports assignment-return passthrough wrappers (`tmp = relay(...); return tmp`) with alias resolution
      - supports argument-reordered passthrough chains (`relay_a(x, y) -> relay_b(y, x)`) when routed parameter remains factory-safe
    - removes leading `self` parameter only when method body does not use instance state
    - returns structured failure when instance state is used (`move_instance_method_uses_instance_state`)
    - returns structured failure when unresolved attribute callsites remain (`move_instance_method_unresolved_callsites`)
  - method-level move dispatch is now gated by indented selection (`start_character > 0`) to avoid class-level move regression.
  - cross-file callsite rewrite (workspace-local Python files):
    - rewrites eligible direct class callsites in other files (for example `ClassName(...).method(...)`)
    - rewrites eligible imported-factory alias callsites in other files (for example `from source import make_service`; `svc = make_service(...)`; `svc.method(...)`)
    - rewrites eligible module-imported factory alias callsites in other files (for example `import source as m`; `svc = m.make_service(...)`; `svc.method(...)`)
    - supports candidate-file local wrapper factories over imported factories during alias propagation
    - supports deeper candidate-file wrapper chains with branch + alias propagation over imported factories
      - supports candidate-file parameter-passthrough wrappers over imported/module-imported factories
      - supports chained candidate-file passthrough wrappers over imported/module-imported factories
      - supports assignment-return + argument-reordered candidate-file passthrough chains over imported/module-imported factories
      - supports branch-return passthrough wrappers (for example `if cond: return relay(x); return relay(y)`) over imported/module-imported factories
      - supports keyword-only passthrough wrappers (for example `def relay(*, service): return service`) over imported/module-imported factories
      - supports passthrough wrappers imported from external workspace modules (both `from helpers import relay` and `import helpers as m; m.relay(...)`)
      - supports transitive imported wrapper chains across external modules (for example `helpers.relay_twice -> bridge.relay`)
      - supports transitive module-imported wrapper chains across external modules (for example `helpers.bridge_mod.relay(...)`)
    - injects import to moved target module when rewrite happened
    - keeps invalid-Python files out of rewrite scope to avoid accidental corruption
  - import patching (`from target_module import symbol`) when source still references moved symbol
  - syntax validation for both files before write
  - atomic write + rollback on failure
- Main code:
  - `agent/semantic/refactor_fallback.py`

### 2) Model Chain Tightening
- Runtime profile default now resolves to `prod` when not explicitly test:
  - `agent/subagents/model_client.py`
- Mock backend is no longer implicitly enabled:
  - requires explicit `subagent_allow_mock_backend=True`
  - only valid in test profile
  - non-test profile with explicit mock allow now hard-fails
- To keep unit/e2e test harness stable, executor injects test-only mock flags only under pytest and only for non-code-change tasks:
  - `agent/subagents/executor.py`

### 3) MCP Simulated Mode Tightening
- Runtime profile default now resolves to `prod` when not explicitly test:
  - `agent/mcp_integration/manager.py`
- `echo/constant` simulated modes now require:
  - explicit `allow_simulated=True`
  - test profile
  - pytest context
- Without all three, simulated mode is rejected.

## Tests Added/Updated
- Move fallback tests:
  - `tests/python_agent/test_semantic_refactor_hybrid.py`
    - require `target_path`
    - cross-file move success
    - cross-file class move success
    - decorated function move keeps decorator with moved symbol
    - staticmethod method move to top-level with callsite rewrite
    - classmethod method move to top-level with callsite rewrite
    - classmethod using `cls` state fails with structured safety error
    - instance method move to top-level with constructor-call rewrite
    - instance method move rewrites known local instance-variable callsites
    - instance method move rewrites constructor-with-args alias chains
    - instance method move rewrites simple local-factory alias calls (including conditional return branches and assignment-return patterns)
    - instance method move rewrites transitive local-factory wrapper alias calls
    - instance method move rewrites eligible cross-file constructor callsites
    - instance method move rewrites eligible cross-file imported-factory alias callsites
    - instance method move rewrites eligible cross-file module-imported factory alias callsites
    - instance method move rewrites eligible cross-file transitive wrapper-over-imported-factory alias callsites
    - instance method move rewrites eligible cross-file multi-step wrapper + branch alias callsites (when all paths remain factory-safe)
    - instance method move rewrites eligible cross-file parameter-passthrough wrapper alias callsites
    - instance method move rewrites eligible cross-file chained-parameter-passthrough wrapper alias callsites
    - instance method move rewrites eligible cross-file assignment-return/reordered chained-parameter-passthrough wrapper alias callsites
    - instance method move rewrites eligible cross-file branch-return passthrough wrapper alias callsites
    - instance method move rewrites eligible cross-file keyword-only passthrough wrapper alias callsites
    - instance method move rewrites eligible cross-file external-module imported passthrough wrapper alias callsites
    - instance method move rewrites eligible cross-file external transitive imported-wrapper alias callsites
    - instance method move rewrites eligible cross-file external transitive module-wrapper alias callsites
    - instance method using `self` state fails with structured safety error
    - instance method with unresolved callsites fails with structured safety error
    - instance method with external/unknown factory source remains safely blocked
    - no source mutation when target is invalid Python
- Model strictness tests:
  - `tests/python_agent/test_subagent_model_client_real_backend.py`
    - test profile requires explicit mock allow
    - default profile rejects mock backend when not in pytest context
- MCP strictness tests:
  - `tests/python_agent/test_mcp_phase6.py`
    - simulated mode requires explicit allow even in test profile
  - `tests/python_agent/test_mcp_transport_resilience.py`
    - added explicit `allow_simulated=True` for simulated-mode test fixtures
- Verification gate tests updated to use mocked real backend payload instead of implicit deterministic:
  - `tests/python_agent/test_verification_gate_required.py`

## Verification
- Focused suites:
  - `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_mcp_phase6.py tests/python_agent/test_mcp_transport_resilience.py tests/python_agent/test_agent_task_flow.py tests/python_agent/test_subagent_runtime_v2.py -v`
  - `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_verification_gate_required.py tests/python_agent/test_memory_hybrid_retrieval.py tests/python_agent/test_memory_semantic_retrieval.py tests/python_agent/test_memory_retrieval_policy.py tests/python_agent/test_semantic_refactor_hybrid.py tests/python_agent/test_semantic_lsp_navigation.py tests/python_agent/test_mcp_phase6.py tests/python_agent/test_mcp_transport_resilience.py -v`
- Full:
  - `python -m pytest tests/python_agent -q -rA`
- Result:
  - full suite green

## Remaining Delta
- `move` fallback now covers top-level function/class plus `@staticmethod`, safe `@classmethod`, and safe instance-method extraction to top-level with callsite rewrite (constructor, constructor-with-args, local alias chains, simple local factories, eligible cross-file direct constructor callsites, eligible cross-file imported-factory alias callsites, and eligible cross-file module-imported/transitive-wrapper factory alias callsites), but deeper object-flow-aware cross-file rewrites remain to be expanded.
- Deterministic backend and simulated MCP are now test-explicit paths, but still intentionally retained for harness use (not production path).
