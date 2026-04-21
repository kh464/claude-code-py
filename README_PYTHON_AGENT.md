# Python Full-Tooling Agent (Implementation Snapshot)

This repository now includes a Python implementation scaffold for the design in:

- `docs/superpowers/specs/2026-04-15-python-full-tooling-agent-design.md`

## Implemented modules

- `agent/contracts.py`: unified `ToolDef` contract and metadata model
- `agent/tools/runtime.py`: execution pipeline (`schema -> validate -> pre-hook -> permission -> call -> post-hook -> result mapping`)
- `agent/permissions/*`: allow/deny/ask permission engine and rule matching
- `agent/tools/registry.py`: registry + dynamic MCP tool injection (`mcp__<server>__<tool>`)
- `agent/tools/builtin.py`: static tool catalog and feature flags
- `agent/tools/file_safety.py`: read-before-edit / stale-read / non-unique replacement safety checks
- `agent/subagents/*`: built-in agent catalog
- `agent/workspace_isolation/worktree.py`: worktree retention and safe-delete validation
- `agent/session_store/store.py`: JSONL transcript + sqlite task-state persistence
- `agent/query_loop.py`: basic agentic loop skeleton for tool-use rounds

## Tool coverage

The Python registry includes the full static tool list from the design document:

- 56 static tool names registered in `ToolRegistry.get_all_base_tools()`
- dynamic MCP tools supported via runtime injection
- internal `SyntheticOutputTool` included in static registry

> Note: dynamic MCP tools are runtime-derived (`mcp__<server>__<tool>`) and therefore not counted as fixed static names.

## Test coverage included

Tests are under `tests/python_agent/` and currently validate:

- tool contract defaults and result mapping
- runtime execution order and permission gate behavior
- permission rule matching and retryability semantics
- session store JSONL/sqlite roundtrip
- full static tool name coverage and dynamic MCP injection
- file edit safety constraints
- built-in subagent/worktree policy helpers
- query loop tool execution cycle

## Known gaps versus production parity

This implementation is contract-first and test-backed, but still a foundation layer. It does **not** yet include:

- production-grade shell/file/network side effects per tool
- full MCP transport client implementation
- real model provider adapters and token budgeting
- full hook ecosystem, UI integration, and complete observability backends

The current code is suitable as an executable baseline to continue incremental parity work.

## Parity Report

- baseline scenarios: 32
- current validated success_rate: 1.0 (32/32, verified on 2026-04-16)
- unresolved_gaps:
  - none in current harness execution snapshot

Mitigation direction:
- raise scenario difficulty from template-level edits toward real multi-step task scoring
- continue improving planner/reviewer/autofix policy quality against harder benchmarks
