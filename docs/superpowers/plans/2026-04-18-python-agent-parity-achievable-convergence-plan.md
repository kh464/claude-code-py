# Python Agent 可比肩收敛版实施计划（Claude Code Parity）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 把当前“功能可用但效果未收敛”的 Python 复现项目，收敛到可与本地 Claude Code 比肩的稳定改码能力。  
**原则:** 先修“评测是否可信”，再修“能力是否强”，最后修“稳定性是否可持续”。

---

## 0. 北极星验收标准（必须全部满足）

1. `python -m pytest tests/python_agent -q -rA` 连续 3 轮全绿。  
2. Parity 全量真实场景 `capability_success_rate >= 0.90` 连续 3 轮达标。  
3. `weighted_quality_score >= 0.90` 连续 3 轮达标。  
4. `environment_failure_rate <= 0.05`，且不掩盖能力失败。  
5. 代码改动任务强制真实模型通路、强制 orchestrator、强制验证闭环（默认不可绕过）。

---

## 1. 为什么此前计划“看起来完整但你觉得缺斤少两”

1. 目标写了，但“中间硬门槛”不够。  
2. 评测里环境失败和能力失败混在一起，导致结论不可信。  
3. 评分存在失真风险，可能出现“通过率低但质量分不低”。  
4. 缺少明确的“每周收敛节奏 + 失败分桶整改清单”。

本计划专门补这 4 个问题。

---

## 2. Phase 0：评测可信化（先修尺子，再修能力）

### Task P0-0: 失败分桶与评测口径修正

**Files:**
- Modify: `agent/parity/report.py`
- Modify: `agent/parity/scenarios.py`
- Create: `tests/python_agent/test_parity_scoring_fidelity.py`

- [ ] **Step 1: 写失败测试，禁止缺失维度默认加分**

Run: `python -m pytest tests/python_agent/test_parity_scoring_fidelity.py -v`  
Expected: FAIL（当前默认值导致失真）。

- [ ] **Step 2: 实现评分修正**

要求:
- 缺失 `decision`/`verification` 维度时默认 0 分，不是 1 分。  
- 报告新增 `environment_failure_rate`、`capability_failure_rate`。  
- 报告保留失败分桶统计（environment/runtime/capability）。

- [ ] **Step 3: 回归验证**

Run: `python -m pytest tests/python_agent/test_parity_scoring_fidelity.py tests/python_agent/test_parity_e2e.py -v`  
Expected: PASS。

- [ ] **Step 4: 提交**

```bash
git add agent/parity/report.py agent/parity/scenarios.py tests/python_agent/test_parity_scoring_fidelity.py
git commit -m "fix: make parity scoring and failure buckets fidelity-safe"
```

### Task P0-1: 环境前置自检门

**Files:**
- Create: `agent/parity/preflight.py`
- Modify: `agent/parity/harness.py`
- Create: `tests/python_agent/test_parity_preflight.py`

- [ ] **Step 1: 写失败测试，缺少权限/依赖时必须标记为 environment_blocked**

Run: `python -m pytest tests/python_agent/test_parity_preflight.py -v`  
Expected: FAIL。

- [ ] **Step 2: 实现 preflight**

要求:
- 校验临时目录可写、shell 可执行、worktree 可创建、必要命令可用。  
- preflight 失败时停止能力评分，仅输出环境阻塞报告。

- [ ] **Step 3: 回归验证**

Run: `python -m pytest tests/python_agent/test_parity_preflight.py tests/python_agent/test_parity_real_repo_tasks.py -v`  
Expected: PASS。

---

## 3. Phase 1：能力基线闭环（把“可用”变成“可靠”）

### Task P1-0: 编排强制统一（前台/后台）

**Files:**
- Modify: `agent/subagents/task_manager.py`
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_subagent_runtime_v2.py`

- [ ] **Step 1: 代码改动任务统一强制走 orchestrator**
- [ ] **Step 2: 禁止隐式直跑分叉（仅测试白名单可绕过）**
- [ ] **Step 3: 跑回归**

Run: `python -m pytest tests/python_agent/test_subagent_runtime_v2.py tests/python_agent/test_agent_task_flow.py -v`  
Expected: PASS。

### Task P1-1: 真实模型强制链路

**Files:**
- Modify: `agent/subagents/model_client.py`
- Modify: `agent/tools/agent_tool.py`
- Test: `tests/python_agent/test_subagent_model_client_real_backend.py`

- [ ] **Step 1: `is_code_change=true` 禁止 deterministic/stub/none**
- [ ] **Step 2: 后端失败进入重试/阻断，不得 silent fallback**
- [ ] **Step 3: 跑回归**

Run: `python -m pytest tests/python_agent/test_subagent_model_client_real_backend.py tests/python_agent/test_verification_gate_required.py -v`  
Expected: PASS。

### Task P1-2: 验证闭环硬门控

**Files:**
- Modify: `agent/verification/runner.py`
- Modify: `agent/subagents/orchestrator.py`
- Test: `tests/python_agent/test_code_change_verification_loop.py`

- [ ] **Step 1: 代码改动任务无 verification 命令时必须 blocked**
- [ ] **Step 2: verification 失败必须阻断 completed**
- [ ] **Step 3: 跑回归**

Run: `python -m pytest tests/python_agent/test_code_change_verification_loop.py tests/python_agent/test_verification_gate_required.py -v`  
Expected: PASS。

---

## 4. Phase 2：语义改码深度（复杂跨文件能力）

### Task P2-0: LSP 重构能力矩阵深化

**Files:**
- Modify: `agent/tools/lsp_tool.py`
- Modify: `agent/semantic/lsp_client.py`
- Test: `tests/python_agent/test_semantic_lsp_navigation.py`

- [ ] **Step 1: 支持 rename/extract/move/inline/organize_imports 能力协商**
- [ ] **Step 2: 不支持能力必须结构化返回，不伪装成功**
- [ ] **Step 3: 跑回归**

Run: `python -m pytest tests/python_agent/test_semantic_lsp_navigation.py tests/python_agent/test_semantic_lsp_stdio_integration.py -v`  
Expected: PASS。

### Task P2-1: 决策质量硬门控

**Files:**
- Modify: `agent/subagents/orchestrator.py`
- Create: `tests/python_agent/test_orchestration_quality_gate.py`

- [ ] **Step 1: planner/reviewer 输出不完整或低分必须阻断**
- [ ] **Step 2: autofix 有界重试且保留失败证据**
- [ ] **Step 3: 跑回归**

Run: `python -m pytest tests/python_agent/test_orchestration_cross_file_quality.py tests/python_agent/test_orchestration_quality_gate.py -v`  
Expected: PASS。

---

## 5. Phase 3：Parity 真实性与收敛工程

### Task P3-0: 场景集重构（真实任务为主）

**Files:**
- Modify: `agent/parity/scenarios.py`
- Create: `tests/python_agent/test_parity_realism_pack.py`

- [x] **Step 1: 总场景 >= 80**
- [x] **Step 2: 真实改码场景 >= 40**
- [x] **Step 3: 模板兜底场景占比 <= 10%**
- [x] **Step 4: 跑回归**

Run: `python -m pytest tests/python_agent/test_parity_realism_pack.py tests/python_agent/test_parity_real_repo_tasks.py tests/python_agent/test_parity_e2e.py -v`  
Expected: PASS。

### Task P3-1: 每周收敛门（硬阈值）

**Week 1 Gate:**
- `capability_success_rate >= 0.25`
- `environment_failure_rate <= 0.20`

**Week 2 Gate:**
- `capability_success_rate >= 0.50`
- `environment_failure_rate <= 0.10`

**Week 3 Gate:**
- `capability_success_rate >= 0.75`
- `weighted_quality_score >= 0.80`

**Week 4 Gate:**
- `capability_success_rate >= 0.90`
- `weighted_quality_score >= 0.90`
- 连续 3 轮稳定达标

---

## 6. 最终验收执行清单

- [x] **Step 1: 全量测试**

Run: `python -m pytest tests/python_agent -q -rA`  
Expected: PASS。

- [x] **Step 2: 跑 parity 全量并记录指标**

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
print("quality_metrics", r["quality_metrics"])
print("environment_failure_rate", r.get("environment_failure_rate"))
print("capability_failure_rate", r.get("capability_failure_rate"))
PY
```

- [x] **Step 3: 连续 3 轮，输出最终报告**

**Files:**
- Create: `docs/superpowers/reports/2026-04-18-python-agent-parity-achievable-final-report.md`

---

## 7. 不得宣称“可比肩”的红线

1. 仅 `tests/python_agent` 全绿，但 parity 未达标。  
2. parity 达标但环境失败率过高。  
3. 质量分达标但通过率低。  
4. 依赖 deterministic 回退才能通过关键代码改动任务。
