# 已知问题与本轮修复

## Codex 子 Agent Stop 误判

来源是 `plugins/codex/codex-multi-agent/hooks/03-subagent-stop.sh`。旧脚本把整个 Stop payload 序列化为文本，再用 `failed|error|timeout|blocked|incomplete|无结果|失败|超时` 做不区分字段的搜索，并以退出码 2 阻断。

因此，即使子任务已完成，只要成功 Handoff 的风险、历史内容或说明中出现上述词，也可能被误判为子 agent 异常。它也没有区分“这个子任务已经完成”和“总目标仍有剩余工作”。

统一仓源码现只读取顶层 `agent_status`、`status`、`outcome`，或事件专属 `reason` 的直接状态字段/起始状态。明确的 `completed/succeeded/success` 优先；`cancelled/canceled` 作为用户停止终态正常退出；只有明确的 `failed/error/timeout/blocked` 才触发恢复。无状态或损坏 JSON 放行，可通过 `WORKLIKERICO_HOOK_VERBOSE=1` 输出诊断，不伪造完成。个人 HOME 中已安装的旧 hook 没有被修改。

## 普通等待被当成最终交付

来源是 `hooks/02-result-guard.sh`：旧逻辑对 `wait_agent`、`claude_tail` 和 `claude_result` 一律要求 Handoff，所以普通等待或进度快照会被误拦。

统一仓源码现把 `wait_agent` 与 `claude_tail` 视为非终态，只检查超长输出和 raw events；只有 `claude_result` 这类最终结果要求 Handoff。损坏 PostToolUse JSON 放行并可选诊断。

## 同类位置结论

| 位置 | 结论 | 原因 |
|---|---|---|
| `03-subagent-stop.sh` | 已修 | 只按事件状态判终态；完成或取消正常结束，失败才恢复 |
| `02-result-guard.sh` | 已修 | 等待/进度与最终结果分流 |
| `01-route-intent.sh` | 不需修 | 只在用户明确提出多 agent 时追加说明，不判断完成态 |
| Claude `auto-route.sh` | 不需修 | 只读取 PostToolUse 结果对象的直接 error/status，且不以非零码阻断 |

专属回归位于 `plugins/codex/codex-multi-agent/tests/hooks.test.sh`，覆盖完成态携带失败词、真实失败/超时、两种取消拼写且无恢复输出、无关嵌套错误、缺字段、损坏 JSON、子任务完成但总目标未完成，以及普通 wait/tail 与最终 result 的分流。`02-result-guard.sh` 不解析任务终态，因此没有取消被当作失败的同类分支。

## Memory 依赖审计

隔离安装后的 `npm audit --omit=dev` 报告 8 个间接依赖问题：1 低、3 中、4 高、0 严重；均不是直接依赖，npm 表示有修复版本。首阶段为保持已验证的 Memory 运行逻辑和 lockfile，没有顺手升级依赖。发布前应单独开依赖升级任务，并重跑 21 项 Memory 测试和 MCP stdio 启动检查。

## Codex 本地缓存刷新与卸载

旧安装器看到已安装 identity 后会跳过 `plugin add`，所以仓库更新后旧 cache 不会刷新；卸载又忽略 CLI 错误，可能假报成功。现在每次安装都会受控地 remove/add 已安装包（包含 enabled 和 disabled），再构建 Memory；卸载只处理实际存在的 identity/marketplace，真实 CLI 失败会向上返回。Memory 数据位于 `~/.codex/memory-pro`，DTL state 位于 `~/.codex/state/design-test-loop`，Multi-Agent 无持久 state，因此刷新 cache 不删除运行数据。
