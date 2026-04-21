# Python Agent Perfect Parity With Local Claude Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Python 复现项目在“理解代码项目并按需求稳定改码”的能力上，达到与本地 Claude Code 可对账的完美比肩水平（功能、质量、稳定性、可恢复性、可观测性全部达标）。

**Architecture:** 以“能力契约冻结 -> 决策质量硬门控 -> 全链路真实执行 -> 真实性能评测 -> 生产化收敛”五层推进。先统一编排和协议约束，再强化语义改码与验证闭环，最后用真实任务评分体系持续压测收敛。

**Tech Stack:** Python 3.11+, asyncio, subprocess, Git worktree, LSP (stdio), MCP stdio transport, pytest, JSON schema validation, structured scoring/reporting

---

## 0. 完美比肩判定标准（DoD）

- 功能对齐：核心改码链路能力矩阵 100% 覆盖（工具、编排、恢复、验证、子 Agent、语义导航/重构、MCP）。
- 质量对齐：真实任务 parity `success_rate >= 0.90`，`weighted_quality_score >= 0.90`，连续 3 次全量运行稳定达标。
- 稳定性对齐：`python -m pytest tests/python_agent -q -rA` 连续 3 次全绿，无随机漂移失败。
- 生产约束对齐：代码改动任务默认强制真实模型链路、强制编排、强制验证（不可隐式降级）。
- 可恢复性对齐：中断、重试、resume、后台任务恢复、worktree 回收路径全部有 e2e 用例覆盖并通过。

---

## 1. 基线盘点（当前状态）

- 已完成：前 5 阶段底座能力、P0-1/P0-2/P0-3/P1-1/P1-2 的主要代码与测试框架。
- 已完成：`tests/python_agent` 全量通过。
- 当前状态：主要缺口已收敛；最新 parity 连续 3 轮均为 `total=80, passed=80, failed=0, success_rate=1.0, weighted_quality_score=0.9775`。

### 1.1 任务回填状态（2026-04-20）

- Task 1：已完成。证据：
  - `docs/superpowers/specs/2026-04-18-python-agent-perfect-parity-contract.md`
  - `agent/parity/report.py`
  - `tests/python_agent/test_parity_report_contract.py`
- Task 2：已完成。证据：
  - `tests/python_agent/test_subagent_runtime_v2.py`
  - `tests/python_agent/test_agent_task_flow.py`
- Task 3：已完成。证据：
  - `tests/python_agent/test_subagent_model_client_real_backend.py`
  - `tests/python_agent/test_verification_gate_required.py`
- Task 4：已完成。证据：
  - `tests/python_agent/test_semantic_lsp_navigation.py`
  - `tests/python_agent/test_semantic_lsp_stdio_integration.py`
- Task 5：已完成。证据：
  - `tests/python_agent/test_mcp_phase6.py`
  - `tests/python_agent/test_mcp_transport_resilience.py`
- Task 6：已完成。证据：
  - `tests/python_agent/test_parity_realism_pack.py`
  - `tests/python_agent/test_parity_real_repo_tasks.py`
  - `tests/python_agent/test_parity_e2e.py`
- Task 7：已完成。证据：
  - `tests/python_agent/test_orchestration_cross_file_quality.py`
  - `tests/python_agent/test_orchestration_quality_gate.py`
- Task 8：已完成。证据：
  - `docs/superpowers/reports/2026-04-18-python-agent-perfect-parity-final-report.md`
  - `python -m pytest tests/python_agent -q` 连续 3 轮通过
  - parity 连续 3 轮满足阈值（见最终报告）
- CI 门禁：已接入。证据：
  - `.github/workflows/ci.yml` 新增 `python-parity-gates` job
  - 包含 `test_parity_report_contract + parity_realism_pack + parity_real_repo_tasks + parity_e2e + tests/python_agent` 门禁

---

### Task 1: 冻结“完美比肩”能力契约与评分口径

**Files:**
- Modify: `docs/superpowers/plans/2026-04-15-python-agent-parity-code-modification.md`
- Create: `docs/superpowers/specs/2026-04-18-python-agent-perfect-parity-contract.md`
- Modify: `agent/parity/report.py`
- Test: `tests/python_agent/test_parity_report_contract.py`

- [x] **Step 1: 为最终对账定义统一能力契约（功能项 + 质量项 + 失败分类）**

输出内容必须包含：
- 功能能力矩阵（是否具备）
- 质量维度矩阵（决策质量、编辑正确性、验证通过率、回归风险）
- 失败分类（模型、工具、编排、语义、验证、环境）

- [x] **Step 2: 编写失败测试，要求报告必须输出契约字段**

Run: `python -m pytest tests/python_agent/test_parity_report_contract.py -v`  
Expected: FAIL，提示字段缺失。

- [x] **Step 3: 实现报告契约字段与一致性校验**

Run: `python -m pytest tests/python_agent/test_parity_report_contract.py -v`  
Expected: PASS。

- [x] **Step 4: 提交**

```bash
git add docs/superpowers/specs/2026-04-18-python-agent-perfect-parity-contract.md docs/superpowers/plans/2026-04-15-python-agent-parity-code-modification.md agent/parity/report.py tests/python_agent/test_parity_report_contract.py
git commit -m "feat: define perfect parity contract and report schema gate"
```

---

### Task 2: 强化 Orchestrator 为“全路径强制编排”（前台/后台统一）

**Files:**
- Modify: `agent/subagents/task_manager.py`
- Modify: `agent/tools/agent_tool.py`
- Modify: `agent/subagents/orchestrator.py`
- Test: `tests/python_agent/test_subagent_runtime_v2.py`
- Test: `tests/python_agent/test_agent_task_flow.py`

- [x] **Step 1: 增加失败测试，要求代码改动任务默认必须经过 orchestrator（前台+后台）**

Run: `python -m pytest tests/python_agent/test_subagent_runtime_v2.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: FAIL，存在绕过路径。

- [x] **Step 2: 实现统一入口策略，关闭隐式直跑分叉**

策略要求：
- 代码改动任务：强制 orchestrator。
- 非代码任务：允许轻量路径但必须显式标记。
- `subagent_use_orchestrator=false` 对代码改动任务无效（仅测试白名单可用）。

- [x] **Step 3: 回归验证**

Run: `python -m pytest tests/python_agent/test_subagent_runtime_v2.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS。

- [x] **Step 4: 提交**

```bash
git add agent/subagents/task_manager.py agent/tools/agent_tool.py agent/subagents/orchestrator.py tests/python_agent/test_subagent_runtime_v2.py tests/python_agent/test_agent_task_flow.py
git commit -m "feat: enforce orchestrator as default mandatory path for code-change tasks"
```

---

### Task 3: 强制真实模型链路（代码改动任务不允许 deterministic 回退）

**Files:**
- Modify: `agent/subagents/model_client.py`
- Modify: `agent/tools/agent_tool.py`
- Modify: `agent/config.py`
- Test: `tests/python_agent/test_subagent_model_client_real_backend.py`
- Test: `tests/python_agent/test_verification_gate_required.py`

- [x] **Step 1: 新增失败测试，代码改动任务遇到无 key/后端异常时应阻断，不得 silent fallback**

Run: `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_verification_gate_required.py -v`  
Expected: FAIL，存在 fallback 通路。

- [x] **Step 2: 实现“代码改动任务真实模型唯一通路”**

规则要求：
- `is_code_change=true` 时，禁止 deterministic/stub/none。
- 如后端不可用，返回明确错误并进入可恢复重试流程，而非降级产出。
- 非代码任务可保留测试友好策略，但需显式配置。

- [x] **Step 3: 回归验证**

Run: `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_verification_gate_required.py -v`  
Expected: PASS。

- [x] **Step 4: 提交**

```bash
git add agent/subagents/model_client.py agent/tools/agent_tool.py agent/config.py tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_verification_gate_required.py
git commit -m "feat: enforce real-model-only path for code-change tasks"
```

---

### Task 4: 深化 LSP 语义重构能力矩阵（从 rename 到 extract/move/组织导入）

**Files:**
- Modify: `agent/tools/lsp_tool.py`
- Modify: `agent/semantic/lsp_client.py`
- Modify: `agent/semantic/index.py`
- Test: `tests/python_agent/test_semantic_lsp_navigation.py`
- Test: `tests/python_agent/test_semantic_lsp_stdio_integration.py`

- [x] **Step 1: 新增失败测试，要求 capability matrix 能区分 rename/extract/move/inline/organize_imports**

Run: `python -m pytest tests/python_agent/test_semantic_lsp_navigation.py tests/python_agent/test_semantic_lsp_stdio_integration.py -v`  
Expected: FAIL，能力归一化不足。

- [x] **Step 2: 实现重构能力协商与降级透明化**

要求：
- 明确报告 server 支持能力，不支持时返回结构化不可用原因。
- `apply_refactor` 路径记录操作种类与影响文件，供 reviewer/verification 使用。

- [x] **Step 3: 回归验证**

Run: `python -m pytest tests/python_agent/test_semantic_lsp_navigation.py tests/python_agent/test_semantic_lsp_stdio_integration.py -v`  
Expected: PASS。

- [x] **Step 4: 提交**

```bash
git add agent/tools/lsp_tool.py agent/semantic/lsp_client.py agent/semantic/index.py tests/python_agent/test_semantic_lsp_navigation.py tests/python_agent/test_semantic_lsp_stdio_integration.py
git commit -m "feat: expand lsp refactor capability matrix and structured outcomes"
```

---

### Task 5: MCP 生产模式收敛（真实连接优先 + 重连 + 协议错误恢复）

**Files:**
- Modify: `agent/mcp_integration/manager.py`
- Modify: `agent/mcp_integration/transport.py` (or equivalent)
- Modify: `agent/tools/builtin.py`
- Test: `tests/python_agent/test_mcp_phase6.py`
- Test: `tests/python_agent/test_mcp_transport_resilience.py`

- [x] **Step 1: 新增失败测试，生产 profile 禁止模拟模式（除显式 allowlist）**

Run: `python -m pytest tests/python_agent/test_mcp_phase6.py tests/python_agent/test_mcp_transport_resilience.py -v`  
Expected: FAIL。

- [x] **Step 2: 实现连接与恢复闭环**

要求：
- 连接失败分级（可重试/不可重试）。
- 指数退避重试 + 最大重连次数。
- 恢复后工具池自动同步。

- [x] **Step 3: 回归验证**

Run: `python -m pytest tests/python_agent/test_mcp_phase6.py tests/python_agent/test_mcp_transport_resilience.py -v`  
Expected: PASS。

- [x] **Step 4: 提交**

```bash
git add agent/mcp_integration/manager.py agent/mcp_integration/transport.py agent/tools/builtin.py tests/python_agent/test_mcp_phase6.py tests/python_agent/test_mcp_transport_resilience.py
git commit -m "feat: harden mcp production connection and recovery loop"
```

---

### Task 6: Parity 场景真实性升级（模板兜底最小化 + 真实任务扩容）

**Files:**
- Modify: `agent/parity/scenarios.py`
- Modify: `agent/parity/harness.py`
- Modify: `agent/parity/report.py`
- Create: `tests/python_agent/test_parity_realism_pack.py`
- Modify: `tests/python_agent/test_parity_real_repo_tasks.py`

- [x] **Step 1: 新增失败测试，限制默认模板场景占比并要求关键场景真实执行**

Run: `python -m pytest tests/python_agent/test_parity_realism_pack.py tests/python_agent/test_parity_real_repo_tasks.py -v`  
Expected: FAIL。

- [x] **Step 2: 扩容并分层场景集**

目标：
- 总场景 >= 80。
- 高价值真实改码场景 >= 40（跨文件、回归修复、验证失败后 autofix）。
- 默认模板兜底占比 <= 10%。

- [x] **Step 3: 回归验证**

Run: `python -m pytest tests/python_agent/test_parity_realism_pack.py tests/python_agent/test_parity_real_repo_tasks.py tests/python_agent/test_parity_e2e.py -v`  
Expected: PASS。

- [x] **Step 4: 提交**

```bash
git add agent/parity/scenarios.py agent/parity/harness.py agent/parity/report.py tests/python_agent/test_parity_realism_pack.py tests/python_agent/test_parity_real_repo_tasks.py tests/python_agent/test_parity_e2e.py
git commit -m "feat: raise parity realism with larger real-task scenario pack"
```

---

### Task 7: 决策质量门控升级（planner/reviewer/autofix 自动打分与阻断）

**Files:**
- Modify: `agent/subagents/orchestrator.py`
- Modify: `agent/subagents/prompts.py` (or equivalent)
- Modify: `agent/verification/runner.py`
- Test: `tests/python_agent/test_orchestration_cross_file_quality.py`
- Create: `tests/python_agent/test_orchestration_quality_gate.py`

- [x] **Step 1: 新增失败测试，低质量决策必须阻断并触发有界 autofix**

Run: `python -m pytest tests/python_agent/test_orchestration_cross_file_quality.py tests/python_agent/test_orchestration_quality_gate.py -v`  
Expected: FAIL。

- [x] **Step 2: 实现结构化质量分与门控策略**

要求：
- planner 完整性、reviewer 一致性、verification 覆盖率形成联合评分。
- 低于阈值阻断 completed 状态。
- 进入 autofix 时保留上轮失败证据，避免盲修。

- [x] **Step 3: 回归验证**

Run: `python -m pytest tests/python_agent/test_orchestration_cross_file_quality.py tests/python_agent/test_orchestration_quality_gate.py -v`  
Expected: PASS。

- [x] **Step 4: 提交**

```bash
git add agent/subagents/orchestrator.py agent/subagents/prompts.py agent/verification/runner.py tests/python_agent/test_orchestration_cross_file_quality.py tests/python_agent/test_orchestration_quality_gate.py
git commit -m "feat: add structured decision-quality gate with bounded autofix loop"
```

---

### Task 8: 完美比肩最终验收（连续三轮）

**Files:**
- Modify: `docs/superpowers/plans/2026-04-18-python-agent-perfect-parity-plan.md`
- Create: `docs/superpowers/reports/2026-04-18-python-agent-perfect-parity-final-report.md`

- [x] **Step 1: 全量自动化回归**

Run: `python -m pytest tests/python_agent -q -rA`  
Expected: PASS。

- [x] **Step 2: 运行 parity 全量并记录指标**

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
print("quality_metrics", r["quality_metrics"])
PY
```
Expected: `success_rate >= 0.90` 且 `weighted_quality_score >= 0.90`。

- [x] **Step 3: 连续执行 3 轮，确认稳定达标**

Run: 同 Step 1 + Step 2，重复 3 次并保存结果。  
Expected: 三轮全部满足阈值。

- [x] **Step 4: 输出最终能力对账报告并提交**

```bash
git add docs/superpowers/plans/2026-04-18-python-agent-perfect-parity-plan.md docs/superpowers/reports/2026-04-18-python-agent-perfect-parity-final-report.md
git commit -m "docs: finalize perfect parity acceptance report"
```

---

## 2. 执行节奏建议（强约束）

- 第 1 周：Task 1-3（契约、编排、模型强制）
- 第 2 周：Task 4-5（LSP 深语义、MCP 生产收敛）
- 第 3 周：Task 6-7（真实性场景、质量门控）
- 第 4 周：Task 8（连续三轮验收 + 最终报告）

---

## 3. 风险与兜底策略

- 风险 1：真实模型不可用导致任务阻断  
  兜底：仅非代码任务允许显式测试后端；代码改动任务保持强制真实链路。

- 风险 2：LSP server 语言差异导致能力不稳定  
  兜底：能力矩阵显式上报，未支持能力不伪装成功，转可解释降级。

- 风险 3：Parity 指标被模板场景“虚高”  
  兜底：强制真实场景占比、失败分类统计、按任务族分层出分。

- 风险 4：后台长任务恢复导致状态漂移  
  兜底：task state + session manifest 双写校验，恢复后第一轮强一致检查。

---

## 4. 完成标志

当且仅当以下条件同时满足，才可宣告“与本地 Claude Code 完美比肩”：

- `tests/python_agent` 全绿且连续 3 轮稳定。
- parity 全量 `success_rate >= 0.90` 且 `weighted_quality_score >= 0.90` 连续 3 轮稳定。
- 最终报告中“剩余缺口”项为 0，或均为明确不在目标范围的非核心项。

