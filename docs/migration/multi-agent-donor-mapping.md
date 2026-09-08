# Multi-Agent 来源映射

统一包以公开 `multi-agent` 双平台仓库为主来源，并吸收已安装 `multi-agent-enhance` 的两处未提交选择：

- Claude supervisor 的模型从 Sonnet 调整为 Opus，已写入 `plugins/claude/claude-autoagent/agents/supervisor.md`。
- Delegate 的模型原则“普通编码用 Sonnet、复杂决策和正式审查用 Opus、机械任务才用 Haiku”已随 `skills/delegate/SKILL.md` 纳入 Claude 包。
- donor 的结构化 hook 也纳入 Claude 包；没有复制 Git 元数据、缓存或运行输出。

Codex 包保留自己的 agent 类型与调用语法，不把 Claude 模型字段机械翻译进去。两个平台共享交接格式，但保持平台运行接口独立。
