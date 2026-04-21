# Python Full-Tooling Agent Design

> 目标：用 Python 完整复现当前项目的 Agent + Tool 体系，覆盖源码 `getAllBaseTools()` 可见工具、动态 MCP 工具、以及内部合成输出能力，达到功能等价与行为等价。

## 1. 设计目标与边界

### 1.1 目标
- 完整复现 Agentic Loop：`LLM -> tool_use -> 工具执行 -> tool_result -> 下一轮`。
- 完整复现工具能力清单，不裁剪、不按优先级分批缩减。
- 完整复现权限、校验、Hook、上下文、子 Agent、worktree、后台任务、会话恢复、可观测性。
- 保持工具契约一致：输入/输出 schema、并发安全标记、只读/破坏性标记、权限决策路径、结果映射。

### 1.2 非目标
- 不追求逐行源码一致。
- 不追求 UI 外观像素级一致。
- 不绑定单一模型厂商，保留 OpenAI/Anthropic 兼容接口。

## 2. 总体架构

### 2.1 分层
- `cli/repl`：命令行交互、流式打印、输入中断、审批交互。
- `agent/query_loop`：主循环、上下文拼接、自动压缩、token 预算。
- `tools/runtime`：工具注册、schema 校验、validateInput、checkPermissions、调用与结果映射。
- `permissions`：allow/deny/ask 规则、自动模式策略、危险操作限制、审批记录。
- `subagents`：AgentTool、内置子 Agent、自定义子 Agent、同步/异步执行、消息路由。
- `workspace_isolation`：worktree 创建、切换、清理、变更检测。
- `mcp_integration`：MCP server 连接、动态工具/资源注入。
- `session_store`：JSONL 转录、任务状态、恢复元数据。
- `observability`：trace/span、tool timing、usage、错误分类。

### 2.2 核心流程
1. 构建系统提示词、用户上下文（含 git 快照、记忆文件）。
2. 调用模型获取 assistant 消息与 `tool_use` 块。
3. 对每个 `tool_use` 执行：
   - `inputSchema` 校验
   - `validateInput`
   - `PreToolUse Hooks`
   - `checkPermissions` / 审批
   - `tool.call`
   - `PostToolUse Hooks`
   - `mapToolResultToToolResultBlockParam`
4. 将 `tool_result` 回注消息流，进入下一轮，直至无工具调用或达到停止条件。

## 3. 工具统一契约（所有工具必须实现）

每个工具在 Python 中统一实现 `ToolDef`：
- 元数据：
  - `name`, `aliases`, `search_hint`, `strict`, `max_result_size_chars`
- schema：
  - `input_schema`（Pydantic/JSON Schema）
  - `output_schema`
- 执行：
  - `call(args, context, can_use_tool, parent_message, on_progress)`
- 规则与安全：
  - `validate_input`
  - `check_permissions`
  - `is_concurrency_safe`
  - `is_read_only`
  - `is_destructive`
- 呈现与映射：
  - `user_facing_name`
  - `get_tool_use_summary`
  - `get_activity_description`
  - `map_tool_result_to_tool_result_block_param`
  - `render_tool_use_message` / `render_tool_result_message`

## 4. 全量工具能力清单（必须全部实现）

以下清单按源码 `getAllBaseTools()`、条件开关、动态注入能力整理。

### 4.1 核心代码操作

1. `BashTool`
- 能力：执行 shell 命令（含流式进度、中断、错误映射）。
- 约束：命令语义分析、危险命令检测、路径与权限限制。

2. `FileReadTool`
- 能力：读取文件文本/图片/PDF/Notebook；支持 offset/limit/pages。
- 约束：绝对路径、设备文件拦截、读取上限、读取状态缓存。

3. `FileEditTool`
- 能力：基于 `old_string/new_string` 精准替换，支持 `replace_all`。
- 约束：必须先 Read；唯一匹配校验；读后变更检测；大文件保护。

4. `FileWriteTool`
- 能力：写入/创建文件内容。
- 约束：路径权限校验、破坏性操作审批、结果差异展示。

5. `GlobTool`
- 能力：文件模式搜索。
- 约束：忽略规则、路径权限、结果数量限制。

6. `GrepTool`
- 能力：正则内容搜索，支持 content/files/count 与上下文参数。
- 约束：路径存在性、权限校验、结果截断与分页（offset/head_limit）。

7. `NotebookEditTool`
- 能力：编辑 Jupyter Notebook 单元内容。
- 约束：Notebook 结构合法性、差异输出、权限审批。

8. `LSPTool`（条件）
- 能力：语言服务能力（跳转、符号、诊断等）。
- 约束：仅启用时注入，结果结构化返回。

9. `PowerShellTool`（条件）
- 能力：Windows 专用命令执行。
- 约束：与 BashTool 同级权限与安全策略。

### 4.2 Agent 与协作

10. `AgentTool`
- 能力：拉起子 Agent 执行任务；支持命名、后台化、模型覆盖、isolation（worktree/remote）。
- 约束：工具池隔离、权限模式隔离、可选 fork 共享上下文、转录持久化。

11. `SendMessageTool`
- 能力：向已运行子 Agent / teammate 定向发消息。

12. `TaskStopTool`
- 能力：停止后台任务/子 Agent。

13. `TaskOutputTool`
- 能力：读取后台任务输出文件/进度摘要。

14. `TeamCreateTool`（条件）
- 能力：创建协作团队上下文。

15. `TeamDeleteTool`（条件）
- 能力：删除协作团队上下文。

16. `ListPeersTool`（条件）
- 能力：列出可通信 peer/agent。

### 4.3 计划与任务管理

17. `EnterPlanModeTool`
- 能力：进入 Plan Mode，限制工具并改写行为策略。

18. `ExitPlanModeV2Tool`
- 能力：退出 Plan Mode，恢复权限模式与上下文状态。

19. `TodoWriteTool`
- 能力：维护任务清单（添加/更新/完成）。

20. `TaskCreateTool`（条件）
- 能力：创建结构化任务。

21. `TaskGetTool`（条件）
- 能力：读取单任务详情。

22. `TaskUpdateTool`（条件）
- 能力：更新任务状态与内容。

23. `TaskListTool`（条件）
- 能力：列出任务集合。

24. `VerifyPlanExecutionTool`（条件）
- 能力：校验计划执行一致性。

### 4.4 Web / MCP / 技能

25. `WebSearchTool`
- 能力：网页搜索。

26. `WebFetchTool`
- 能力：抓取指定 URL 内容并结构化返回。

27. `WebBrowserTool`（条件）
- 能力：浏览器级自动化交互（页面导航、抓取）。

28. `SkillTool`
- 能力：调用技能工作流与技能提示。

29. `AskUserQuestionTool`
- 能力：在无法安全假设时向用户发结构化提问。

30. `ToolSearchTool`（动态条件）
- 能力：在 defer-loading 场景检索工具能力，再按需启用工具。

31. `ListMcpResourcesTool`
- 能力：列出 MCP 资源。

32. `ReadMcpResourceTool`
- 能力：读取 MCP 资源内容。

33. `动态 MCP 工具`：`mcp__<server>__<tool>`
- 能力：运行时从 MCP server 注入，遵循同一工具契约与权限体系。

### 4.5 Worktree / 流程 / 系统

34. `EnterWorktreeTool`（条件）
- 能力：创建并进入会话 worktree。

35. `ExitWorktreeTool`（条件）
- 能力：退出并按策略保留/删除 worktree。

36. `WorkflowTool`（条件）
- 能力：执行预定义 workflow 脚本。

37. `SleepTool`（条件）
- 能力：延迟/等待型流程控制。

38. `BriefTool`
- 能力：产生精简摘要/状态简报。

39. `SnipTool`（条件）
- 能力：历史裁剪与上下文管理辅助。

40. `CtxInspectTool`（条件）
- 能力：上下文内容检查与诊断。

41. `TerminalCaptureTool`（条件）
- 能力：终端捕获/回放相关能力。

42. `MonitorTool`（条件）
- 能力：监控任务/会话状态。

43. `RemoteTriggerTool`（条件）
- 能力：触发远程任务链路。

### 4.6 通知与集成

44. `PushNotificationTool`（条件）
- 能力：发送推送通知。

45. `SubscribePRTool`（条件）
- 能力：订阅 PR 事件。

46. `SuggestBackgroundPRTool`（ant-only）
- 能力：后台 PR 建议与流程辅助。

47. `SendUserFileTool`（条件）
- 能力：向用户传递文件内容/工件。

48. `ReviewArtifactTool`（条件）
- 能力：评审生成工件。

### 4.7 定时与运维

49. `CronCreateTool`
- 能力：创建 cron 任务。

50. `CronDeleteTool`
- 能力：删除 cron 任务。

51. `CronListTool`
- 能力：列出 cron 任务。

52. `ConfigTool`（ant-only）
- 能力：运行期配置管理。

53. `TungstenTool`（ant-only）
- 能力：特定内部能力桥接。

54. `REPLTool`（ant-only）
- 能力：REPL 包裹模式运行工具。

55. `OverflowTestTool`（条件）
- 能力：溢出/边界测试。

56. `TestingPermissionTool`（仅测试环境）
- 能力：权限流测试注入。

### 4.8 特殊内部工具

57. `SyntheticOutputTool`（内部）
- 能力：合成输出块；不作为常规工具列表暴露，但必须在运行时支持。

## 5. 子 Agent 内置类型（必须实现）

来自 `getBuiltInAgents()`：
- `general-purpose`
- `statusline-setup`
- `Explore`（条件）
- `Plan`（条件）
- `claude-code-guide`（非 SDK 入口）
- `verification`（条件）

并支持：
- 自定义 Agent 目录加载（项目级与用户级）
- tools allowlist/disallowlist
- `permissionMode`、`model`、`mcpServers`、`hooks` frontmatter

## 6. 关键行为一致性要求

### 6.1 工具执行顺序一致
- `schema -> validateInput -> PreToolUse hooks -> permission -> tool.call -> PostToolUse hooks -> result mapping`。

### 6.2 权限一致
- 同时支持 `alwaysAllow/alwaysDeny/alwaysAsk`。
- 支持按工具名、按模式、按规则来源（session/local/user/policy）追踪。
- 拒绝后可生成可重试/不可重试语义。

### 6.3 并发一致
- 并发安全工具批量并发执行，非并发安全工具串行执行。
- 工具执行更新需携带进度事件。

### 6.4 编辑安全一致
- 未 Read 不允许 Edit。
- 读后文件变更必须拒绝并要求重读。
- `old_string` 非唯一必须拒绝并要求更精确定位或 `replace_all`。

### 6.5 worktree 一致
- 子 Agent 可在独立 worktree 运行。
- 退出策略：有改动默认保留，无改动可自动清理。
- 删除前必须做变更与安全路径校验。

### 6.6 转录与恢复一致
- 主线程与子线程均写 JSONL 转录。
- 异步任务可恢复，支持通过 `agentId/taskId` 路由消息与输出。

## 7. Python实现规范

### 7.1 目录建议
- `agent/tools/*.py`：各工具实现。
- `agent/tools/runtime.py`：统一执行链。
- `agent/subagents/*.py`：子 Agent 生命周期。
- `agent/permissions/*.py`：权限引擎。
- `agent/session_store/*.py`：JSONL + sqlite。

### 7.2 统一事件模型
- `tool_use_started`
- `tool_progress`
- `tool_result`
- `tool_error`
- `permission_decision`
- `agent_spawned/agent_completed/agent_failed`

### 7.3 统一错误分类
- 输入校验错误
- 权限拒绝错误
- 工具执行错误
- 中断错误
- MCP 连接/调用错误

## 8. 验收标准（无优先级分期）

必须同时满足：
- 上述 57 类工具能力全部可调用（条件工具在开关开启时可用）。
- 每个工具都有：
  - schema 测试
  - validateInput 测试
  - 权限测试
  - 成功/失败路径测试
  - `tool_result` 映射测试
- AgentTool 完整覆盖：
  - 同步子 Agent
  - 异步后台子 Agent
  - 命名路由通信
  - worktree isolation
  - 转录恢复
- MCP 动态工具与资源读取完整可用。
- 端到端场景通过：
  - 读代码 -> 改代码 -> 运行测试 -> 生成总结
  - 并发搜索/读取
  - 审批拒绝与重试
  - 子 Agent 后台运行与回收

## 9. 风险与约束

- 外部模型差异会导致轨迹不完全一致，需通过行为验收而非 token 级验收。
- 平台差异（Windows/Linux/macOS）会影响 shell、路径、权限策略实现。
- 远程/推送/PR 订阅类工具依赖外部系统凭证，需提供 mock 与降级策略。

## 10. 审阅说明

本设计文档已按“全工具能力覆盖”重写，不包含优先级分期与裁剪实现路径。  
后续实现应严格以本清单为范围基线，禁止删减工具能力。

