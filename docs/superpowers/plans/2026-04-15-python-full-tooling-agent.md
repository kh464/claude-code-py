# Python Full Tooling Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python implementation of the full tooling agent contract defined in `2026-04-15-python-full-tooling-agent-design.md`, including runtime pipeline, 57 tools, dynamic MCP tooling, and test coverage.

**Architecture:** Implement a contract-first Python package under `agent/` with a shared `ToolDef` base class, a deterministic runtime execution chain, permission engine, session store, and tool registry that exposes all tools. Use focused modules and metadata-driven registration for consistency while keeping tool-specific logic isolated.

**Tech Stack:** Python 3.11+, pydantic, pytest, asyncio, dataclasses

---

### Task 1: Bootstrap Python workspace

**Files:**
- Create: `pyproject.toml`
- Create: `agent/__init__.py`
- Create: `agent/py.typed`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write failing test for package import smoke check**
- [ ] **Step 2: Run test to verify fail**
- [ ] **Step 3: Add package scaffold and project metadata**
- [ ] **Step 4: Run test to verify pass**

### Task 2: Define shared contracts and error taxonomy

**Files:**
- Create: `agent/contracts.py`
- Create: `agent/errors.py`
- Create: `tests/test_contracts.py`

- [ ] **Step 1: Write failing tests for ToolDef required fields and methods**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement `ToolDef`, metadata, schema contracts, and error classes**
- [ ] **Step 4: Run tests to verify pass**

### Task 3: Implement runtime execution chain

**Files:**
- Create: `agent/tools/runtime.py`
- Create: `tests/test_runtime_pipeline.py`

- [ ] **Step 1: Write failing tests for order: schema -> validate -> pre-hook -> permission -> call -> post-hook -> map**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement runtime pipeline with progress events and concurrency-safe batching**
- [ ] **Step 4: Run tests to verify pass**

### Task 4: Implement permission system

**Files:**
- Create: `agent/permissions/models.py`
- Create: `agent/permissions/engine.py`
- Create: `tests/test_permissions.py`

- [ ] **Step 1: Write failing tests for allow/deny/ask rules and source tracking**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement permission decision engine and retryability semantics**
- [ ] **Step 4: Run tests to verify pass**

### Task 5: Implement session store and observability models

**Files:**
- Create: `agent/session_store/store.py`
- Create: `agent/observability/events.py`
- Create: `tests/test_session_store.py`

- [ ] **Step 1: Write failing tests for JSONL transcript append/load and async task restore metadata**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement JSONL session store and event models**
- [ ] **Step 4: Run tests to verify pass**

### Task 6: Implement tool base class + concrete tool registry (57 tools)

**Files:**
- Create: `agent/tools/base.py`
- Create: `agent/tools/builtin.py`
- Create: `agent/tools/registry.py`
- Create: `tests/test_tool_registry.py`

- [ ] **Step 1: Write failing tests asserting all 57 tool names exist with contract fields**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement tool base class and concrete classes for all listed tools (including conditional and internal tools)**
- [ ] **Step 4: Implement registry assembly including dynamic MCP tool injection**
- [ ] **Step 5: Run tests to verify pass**

### Task 7: Implement safety rules for read/edit/write and path constraints

**Files:**
- Create: `agent/tools/file_safety.py`
- Create: `tests/test_file_safety.py`

- [ ] **Step 1: Write failing tests for read-before-edit, stale-read rejection, non-unique replacement rejection**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement safety validator and state cache logic**
- [ ] **Step 4: Run tests to verify pass**

### Task 8: Implement subagent/worktree models and built-in agent catalog

**Files:**
- Create: `agent/subagents/models.py`
- Create: `agent/subagents/catalog.py`
- Create: `agent/workspace_isolation/worktree.py`
- Create: `tests/test_subagents_and_worktree.py`

- [ ] **Step 1: Write failing tests for built-in agents, isolation policy, and worktree retention/cleanup decisions**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement subagent catalog and worktree policy helpers**
- [ ] **Step 4: Run tests to verify pass**

### Task 9: End-to-end agentic loop skeleton

**Files:**
- Create: `agent/query_loop.py`
- Create: `tests/test_query_loop.py`

- [ ] **Step 1: Write failing tests for multi-round tool_use -> tool_result loop and stop condition**
- [ ] **Step 2: Run tests to verify fail**
- [ ] **Step 3: Implement query loop skeleton with pluggable model client and runtime integration**
- [ ] **Step 4: Run tests to verify pass**

### Task 10: Verification and documentation

**Files:**
- Create: `README_PYTHON_AGENT.md`

- [ ] **Step 1: Run full Python test suite and capture evidence**
- [ ] **Step 2: Document module map, tool coverage table, and known integration gaps**
- [ ] **Step 3: Re-run full suite to verify final state**
