# 多 Agent 编排：跨平台共享学说 + 平台隔离映射

> 本文件是 `claude-autoagent`（Claude 平台）与 `codex-multi-agent`（Codex 平台）的**共享真源**，两仓库各存一份、内容一致。
> 目的：把两平台**可共享的编排学说**沉淀成单一真源，同时用**映射表锁死平台隔离层**，防止跨平台污染（如 Claude hook/工具名泄进 Codex 导致 hook 静默失效）。

## 一、共享层（平台中立，改这里 = 两平台都改）

编排的**概念/规则**不含任何平台工具名，两平台一致：

- **复杂度评分**：research / planning / implementation / audit 四维打分，判断是否升级多 agent。
- **升级阈值**：仅当任务同时涉及 3+ 领域、含明确多步串并行、文本足够长时才启多 agent；绝大多数输入直接放行。
- **角色分工**：supervisor（监督协调）/ challenger（唱反调）/ executor（执行）/ recovery-agent（故障恢复）。
- **结构化交接**：问题陈述 → 约束 → 选项 → 风险 → 建议 → 执行交接。
- **故障恢复**：子 agent 失败/超时/结果不完整时，诊断→恢复部分结果→重试或升级。
- **结果聚合 / 编译测试校验 / 长文件大纲 / 不相交写权**：sidecar 委派、报告汇总、disjoint write ownership。
- **主线程纪律**：主线程留在关键路径，控制上下文消耗。

## 二、平台隔离层（各写各的，**永不跨平台同步**）

下表每一行都是一个**污染点**。改 hook / 工具 matcher 前必查此表，确认用的是**目标平台**的词汇。

| 维度 | Claude（claude-autoagent） | Codex（codex-multi-agent） |
|---|---|---|
| Hook 声明位置 | 用户配 `~/.claude/settings.json`（模板见 `hooks/auto-route-prompt.md`） | 插件自带 `hooks.json` |
| Hook 类型 | `prompt`（LLM 分类器，无脚本） | `command`（shell 脚本 `hooks/*.sh`） |
| 路由事件 | `UserPromptSubmit` | `UserPromptSubmit` |
| 结果守卫事件 | （无） | `PostToolUse`、`SubagentStop` |
| **委派工具名** | `Agent`、`Task`/`TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet`、`SendMessage` | `spawn_agent`、`wait_agent`、`multi_agent_v1.wait_agent`、`claude_result`、`claude_tail` |
| MCP 委派工具 | `mcp__claude-delegate__*` | `mcp__claude-delegate__claude_result` / `claude_tail` |
| Hook 脚本路径 | 无 | 硬编码 `~/.codex/plugins/cache/codex-multi-agent/...` |
| stdin JSON 字段 | Claude hook 载荷格式 | `prompt` / `user_prompt` / `tool_name` |
| Agent 定义格式 | `agents/*.md`（frontmatter + 正文） | `agents/*.toml`（`developer_instructions`） |
| 路由策略 | 主动 auto-routing（prompt 分类器） | 需显式授权，仅在检测到明确委派意图时发路由提醒 |
| 任务持久化 | Task 工具族 | Codex planning + 主线程集成 |

## 三、合并/维护规则

1. **改编排概念**（第一节）→ 两仓库的本文件同步更新（内容一致）。
2. **改 hook / 工具 / agent 格式**（第二节）→ 只改**当前平台**，另一平台按映射表写**对应但不同**的实现，**禁止复制粘贴**。
3. **新增委派工具或 hook 事件** → 先在第二节映射表补一行，再实现。表是防污染的唯一真相源。
4. 反例（历史事故）：把 Codex 的 `hooks.json` matcher（`wait_agent|spawn_agent`）搬到 Claude → Claude 无此工具 → matcher 永不命中 → hook 静默失效。
