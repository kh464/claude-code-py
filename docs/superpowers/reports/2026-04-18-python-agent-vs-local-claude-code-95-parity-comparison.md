# Python 复现工程 vs 本地 Claude Code（95%对齐评估）

## 结论（先回答你的问题）

- **严格口径：当前不建议直接宣称“达到 95%”**。  
- **客观估算区间：约 92% - 94%**（偏工程能力与可执行闭环已很强；复杂跨文件语义决策上限与跨环境稳定性证据仍不足）。  
- **在当前内部 Parity 基准上，指标已超过 95%门槛**（见下文），但这不等同于“与本地 Claude Code 在所有真实复杂任务上 95%对齐”。

---

## 1. 评估口径

本报告采用两层口径：

1. **内部可测能力口径**（代码与测试可直接验证）。
2. **真实复杂任务口径**（跨项目、跨语言、跨环境、长周期稳定）。

如果只看第 1 层，当前分数非常高；加入第 2 层后，整体仍有缺口。

---

## 2. 量化评分（本次）

评分维度与权重：

1. 工具链完整度与真实性（30%）
2. 运行时安全/权限/恢复闭环（20%）
3. 子 Agent 编排与改码闭环（20%）
4. 语义改码深度（LSP/重构）（15%）
5. 模型与 MCP 生产鲁棒性（10%）
6. 评测真实性与长期稳定性证据（5%）

本次估算：

1. 工具链完整度与真实性：**97**
2. 运行时安全/权限/恢复闭环：**95**
3. 子 Agent 编排与改码闭环：**93**
4. 语义改码深度：**86**
5. 模型与 MCP 生产鲁棒性：**89**
6. 评测真实性与长期稳定性证据：**84**

加权总分：**92.5 / 100**

---

## 3. 已对齐能力（具体功能）

### 3.1 工具与运行时

1. **56/56 内置工具均为真实工具（无 StaticTool 桩）**  
证据：[builtin.py:124](/d:/ai-agent/claude-code/agent/tools/builtin.py:124), [builtin.py:166](/d:/ai-agent/claude-code/agent/tools/builtin.py:166), [test_high_frequency_tools_realization.py:36](/d:/ai-agent/claude-code/tests/python_agent/test_high_frequency_tools_realization.py:36)

2. **统一执行链路完整：schema -> validate -> pre-hook -> permission -> call -> post-hook -> failure-hook**  
证据：[runtime.py:37](/d:/ai-agent/claude-code/agent/tools/runtime.py:37), [runtime.py:93](/d:/ai-agent/claude-code/agent/tools/runtime.py:93), [runtime.py:95](/d:/ai-agent/claude-code/agent/tools/runtime.py:95), [runtime.py:102](/d:/ai-agent/claude-code/agent/tools/runtime.py:102), [runtime.py:139](/d:/ai-agent/claude-code/agent/tools/runtime.py:139)

3. **权限引擎具备 always_allow / always_deny / always_ask 优先级**  
证据：[engine.py:13](/d:/ai-agent/claude-code/agent/permissions/engine.py:13), [engine.py:50](/d:/ai-agent/claude-code/agent/permissions/engine.py:50)

4. **文件改码安全链路可用：read-before-edit / stale-read / 唯一匹配约束**  
证据：[test_file_tools_real.py:55](/d:/ai-agent/claude-code/tests/python_agent/test_file_tools_real.py:55), [test_file_tools_real.py:97](/d:/ai-agent/claude-code/tests/python_agent/test_file_tools_real.py:97)

5. **Shell 执行具备超时、中断、进度流、危险命令拦截**  
证据：[bash_tool.py:80](/d:/ai-agent/claude-code/agent/tools/bash_tool.py:80), [bash_tool.py:101](/d:/ai-agent/claude-code/agent/tools/bash_tool.py:101), [shell_safety.py:6](/d:/ai-agent/claude-code/agent/tools/shell_safety.py:6), [test_shell_tools_phase2.py:47](/d:/ai-agent/claude-code/tests/python_agent/test_shell_tools_phase2.py:47)

### 3.2 子 Agent / 编排 / 验证闭环

1. **TaskManager 强制统一走 orchestrator（无直跑分叉）**  
证据：[task_manager.py:242](/d:/ai-agent/claude-code/agent/subagents/task_manager.py:242)

2. **代码改动任务强制验证门禁（缺 verification 可直接 blocked）**  
证据：[agent_tool.py:180](/d:/ai-agent/claude-code/agent/tools/agent_tool.py:180), [agent_tool.py:183](/d:/ai-agent/claude-code/agent/tools/agent_tool.py:183), [test_verification_gate_required.py:12](/d:/ai-agent/claude-code/tests/python_agent/test_verification_gate_required.py:12)

3. **Planner/Reviewer 结构化协议 + review score gate + autofix 闭环**  
证据：[orchestrator.py:252](/d:/ai-agent/claude-code/agent/subagents/orchestrator.py:252), [orchestrator.py:285](/d:/ai-agent/claude-code/agent/subagents/orchestrator.py:285), [orchestrator.py:550](/d:/ai-agent/claude-code/agent/subagents/orchestrator.py:550), [test_orchestration_quality_gate.py:90](/d:/ai-agent/claude-code/tests/python_agent/test_orchestration_quality_gate.py:90)

4. **后台任务生命周期可用（spawn/resume/stop/output/worktree）**  
证据：[agent_tool.py:98](/d:/ai-agent/claude-code/agent/tools/agent_tool.py:98), [test_agent_task_flow.py:11](/d:/ai-agent/claude-code/tests/python_agent/test_agent_task_flow.py:11), [test_task_state_resume.py:17](/d:/ai-agent/claude-code/tests/python_agent/test_task_state_resume.py:17)

### 3.3 语义能力（LSP）

1. **definitions / references / diagnostics / rename / list_refactors / apply_refactor 全链路可用**  
证据：[lsp_tool.py:39](/d:/ai-agent/claude-code/agent/tools/lsp_tool.py:39), [lsp_tool.py:175](/d:/ai-agent/claude-code/agent/tools/lsp_tool.py:175), [index.py:368](/d:/ai-agent/claude-code/agent/semantic/index.py:368), [test_semantic_lsp_navigation.py:218](/d:/ai-agent/claude-code/tests/python_agent/test_semantic_lsp_navigation.py:218)

2. **strict LSP 模式可强制失败，不再静默降级**  
证据：[lsp_tool.py:124](/d:/ai-agent/claude-code/agent/tools/lsp_tool.py:124), [test_semantic_lsp_navigation.py:162](/d:/ai-agent/claude-code/tests/python_agent/test_semantic_lsp_navigation.py:162)

### 3.4 MCP / 上下文 / 恢复

1. **MCP 支持 stdio transport + retry/backoff + 资源读写 + 动态工具同步**  
证据：[manager.py:58](/d:/ai-agent/claude-code/agent/mcp_integration/manager.py:58), [manager.py:250](/d:/ai-agent/claude-code/agent/mcp_integration/manager.py:250), [transport.py:36](/d:/ai-agent/claude-code/agent/mcp_integration/transport.py:36), [test_mcp_phase6.py:103](/d:/ai-agent/claude-code/tests/python_agent/test_mcp_phase6.py:103)

2. **QueryLoop 支持 token budget compaction + memory 注入**  
证据：[query_loop.py:93](/d:/ai-agent/claude-code/agent/query_loop.py:93), [compaction.py:40](/d:/ai-agent/claude-code/agent/context/compaction.py:40), [query_loop.py:63](/d:/ai-agent/claude-code/agent/query_loop.py:63)

3. **tool_use/tool_result 规范化与 orphan 修复已落地**  
证据：[messages.py:19](/d:/ai-agent/claude-code/agent/messages.py:19), [messages.py:69](/d:/ai-agent/claude-code/agent/messages.py:69), [test_message_normalization.py:24](/d:/ai-agent/claude-code/tests/python_agent/test_message_normalization.py:24)

---

## 4. 与“95%比肩”仍有差距的功能点（具体）

### 4.1 复杂语义重构能力上限仍受 LSP server 约束（核心缺口）

现状：

1. `list_refactors/apply_refactor` 走的是 LSP code action 机制。
2. 是否存在 `extract/move/inline` 深层能力，取决于具体语言服务器是否返回对应 action。

证据：[index.py:330](/d:/ai-agent/claude-code/agent/semantic/index.py:330), [index.py:396](/d:/ai-agent/claude-code/agent/semantic/index.py:396), [lsp_tool.py:158](/d:/ai-agent/claude-code/agent/tools/lsp_tool.py:158)

影响：

1. 在复杂跨文件/跨模块重构任务上，稳定性与上限仍弱于本地 Claude Code 的“强模型 + 工具协同”。

### 4.2 模型链路并非全局“唯一真实模型通路”

现状：

1. 生产档已禁止 mock backend。
2. 但测试/非生产元数据下仍允许 deterministic 路径（保障可用性与测试可重复）。

证据：[model_client.py:273](/d:/ai-agent/claude-code/agent/subagents/model_client.py:273), [model_client.py:290](/d:/ai-agent/claude-code/agent/subagents/model_client.py:290), [test_subagent_model_client_real_backend.py:124](/d:/ai-agent/claude-code/tests/python_agent/test_subagent_model_client_real_backend.py:124)

影响：

1. 在“真实复杂任务全量”场景里，智能决策质量上限仍不等价于本地 Claude Code。

### 4.3 MCP 仍保留模拟模式分支（prod 已禁，但代码路径仍存在）

现状：

1. `echo/constant` 模式仍保留，prod profile 下才阻断。

证据：[manager.py:205](/d:/ai-agent/claude-code/agent/mcp_integration/manager.py:205), [manager.py:206](/d:/ai-agent/claude-code/agent/mcp_integration/manager.py:206), [test_mcp_phase6.py:124](/d:/ai-agent/claude-code/tests/python_agent/test_mcp_phase6.py:124)

影响：

1. 生产级“唯一真实外部系统通路”还不是绝对强制。

### 4.4 记忆检索仍是轻量 token overlap，不是强语义检索

现状：

1. 当前 memory retrieval 主要依赖 token overlap 评分。

证据：[retrieval.py:36](/d:/ai-agent/claude-code/agent/memory/retrieval.py:36), [retrieval.py:63](/d:/ai-agent/claude-code/agent/memory/retrieval.py:63)

影响：

1. 长链路上下文召回质量在复杂项目中可能低于本地 Claude Code。

### 4.5 Parity 指标很高，但场景仍偏“可控模板化任务”

现状：

1. 当前已扩到 80 场景、指标达标。
2. 但 real-repo 场景多数仍是生成式小任务，不等同真实大型仓库任务分布。

证据：[scenarios.py:334](/d:/ai-agent/claude-code/agent/parity/scenarios.py:334), [test_parity_realism_pack.py:16](/d:/ai-agent/claude-code/tests/python_agent/test_parity_realism_pack.py:16), [2026-04-18-python-agent-parity-achievable-final-report.md](/d:/ai-agent/claude-code/docs/superpowers/reports/2026-04-18-python-agent-parity-achievable-final-report.md)

影响：

1. 不能仅凭内部高分直接推断“对本地 Claude Code 达到 95%”。

### 4.6 缺少“长期 + 跨机器 + 跨依赖版本”稳定性证据链

现状：

1. 当前主要是单环境高质量收敛。
2. 还缺跨 OS / 多 Python 版本 / 多周连续观测的证据。

影响：

1. 在工程严谨口径下，无法给出 95% 的稳定承诺。

---

## 5. 内部指标现状（你现在这版的真实强项）

最近一次收敛报告显示：

1. `tests/python_agent` 全绿（本地回归通过）。
2. Parity 80/80 通过。
3. `capability_success_rate = 1.0`
4. `weighted_quality_score = 0.9775`
5. `environment_failure_rate = 0.0`

证据：[2026-04-18-python-agent-parity-achievable-final-report.md](/d:/ai-agent/claude-code/docs/superpowers/reports/2026-04-18-python-agent-parity-achievable-final-report.md)

解释：

1. 这说明“本地可执行闭环能力”已经非常强。  
2. 但“95%比肩”需要把复杂真实任务泛化能力与跨环境稳定性也纳入。

---

## 6. 最终判断（是否达到 95%）

1. **内部工程能力（可测闭环）**：接近或达到 95%。  
2. **与本地 Claude Code 的全场景真实能力**：当前更稳妥判断为 **92%-94%**。  
3. **因此本报告结论：暂不宣称“已 95% 完全比肩”**，但已进入“高对齐、可生产推进”的阶段。

---

## 7. 如果你要冲刺到“可公开宣称 95%”

最短关键补齐项（按优先级）：

1. 强化复杂跨文件真实任务集（非模板、真实仓库分布）并形成长期基线。
2. 扩展 LSP 深层重构能力（至少在主语言链路上稳定支持 extract/move/inline）。
3. 建立跨机器/跨依赖矩阵回归（周级连续达标）。
4. 将 memory 检索从词重叠升级为强语义检索（向量/混合召回）。

