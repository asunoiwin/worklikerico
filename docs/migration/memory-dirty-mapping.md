# Memory 源码差异映射

首阶段选择公开的双平台 `memory-pro` 工作树作为来源，因为它同时包含 Claude/Codex 外壳、Codex 运行路径抽象和当前测试。旧私有 Codex 仓库的未提交修改没有以 patch 形式发布；逐项语义核对结果如下。

| 旧私有工作树文件 | 修改语义 | 统一源码状态 |
|---|---|---|
| `auto-capture.ts` | 四处日志命名从 Claude 改为 Codex | 已包含；统一 Codex 文件使用 Codex 日志命名，并多一处后续改动 |
| `dream-manager.ts` | 四处日志命名从 Claude 改为 Codex | 已包含；统一 Codex 文件使用 Codex 日志命名，并含更新的运行路径处理 |
| `habit-tracker.ts` | 一处日志命名从 Claude 改为 Codex | 已包含；统一 Codex 文件使用 Codex 日志命名，并有后续行为调整 |
| `mcp-server.ts` | 二十三处启动、维护、错误日志命名从 Claude 改为 Codex | 已包含；统一 Codex 文件的对应日志均为 Codex 命名，并含后续 MCP 逻辑 |
| `store.ts` | 四处存储错误日志命名从 Claude 改为 Codex | 已包含且与旧私有工作树文件完全一致 |

这里的“已包含”只指这五处未提交修改的语义。两个平台的 Memory 内核目前还有运行路径和少量实现差异，因此首阶段保留双平台源码，不执行强制覆盖式同步。同步脚本已改成仓库相对路径，但在差异被正式合并前不应作为发布步骤。
