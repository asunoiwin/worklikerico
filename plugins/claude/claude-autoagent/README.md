# claude-autoagent

Claude Code 多 Agent 自动编排插件。

## 功能

自动分析用户任务的复杂度，智能决定是否启动多 Agent 协作流程。

### 核心组件

| 组件 | 类型 | 功能 |
|------|------|------|
| `supervisor` | Agent | 任务协调者：复杂度分析 → 角色分配 → 依赖管理 → 结构化交接 |
| `recovery-agent` | Agent | 故障恢复：3 级诊断（L1 部分收集 → L2 重试 → L3 人工干预） |
| `/orchestrate` | 命令 | 手动触发多 Agent 编排（可选） |
| `auto-route` | Hook | `UserPromptSubmit` prompt hook，自动路由复杂任务 |

### 自动路由逻辑

```
用户输入 → UserPromptSubmit hook（LLM 自动评分）
    ├─ 简单任务 → 直接放行，Claude 正常处理
    └─ 复杂任务（3+ 领域协作）→ 注入路由指令 → 自动启动 supervisor
        → supervisor 分析拆分 → 分配专业 agent → 协调执行 → 汇总结果
```

### 触发条件

只有**同时满足**以下条件才会触发多 Agent：
- 文本超过 80 字
- 涉及 3 个及以上工作领域（调研/设计/实现/测试/文档）
- 包含明确的多步骤需求

**不会触发**的情况：
- 短文本、单步操作、问答讨论、git 命令、`/` 开头命令、简短回复

### 结构化交接协议

每个 Agent 完成任务后以统一格式报告：

```markdown
## 交接报告
- **状态**: completed / blocked / failed
- **摘要**: 一句话总结
- **产出物**: 修改/创建的文件列表
- **交接信息**: 下游 agent 需要知道的关键信息
- **下一步**: 建议的后续操作
```

### 故障恢复

当子 Agent 异常退出时，`recovery-agent` 自动介入：
- **L1**: 收集部分产出（文件已写入但未报告）
- **L2**: 补充上下文后重试（最多 2 次）
- **L3**: 降级为人工干预，通知用户

## 安装

```bash
./install.sh
```

然后参考 `hooks/auto-route-prompt.md` 配置自动路由 hook。

重启 Claude Code 会话后生效。

## 设计来源

核心设计理念源自 [OpenClaw 多 Agent 编排系统](https://github.com/asunoiwin/multi-agent-orchestration)，提炼了其中经过验证的三个高价值能力：

1. **任务自动路由** — 用 LLM 判断代替关键词匹配，更准确
2. **故障自愈** — 三层恢复机制，减少人工干预
3. **结构化交接** — 统一的 Agent 间通信协议，防止信息丢失

## 许可

MIT
