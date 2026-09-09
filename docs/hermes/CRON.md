# 无模型本地巡检样例

2026-09-09：用户明确要求先完成基础环境、工作习惯分析与插件落实，再做日常任务。日常监测暂不启用，没有确定提醒频率；下列为手动参考样例，不应自动创建或恢复。

Hermes cron 原生支持 `--no-agent --script`。该模式不创建 agent、不调用 provider、不消耗模型 token；stdout 为空时保持静默，非零退出或超时会记为失败。脚本必须位于 `${HERMES_HOME}/scripts/`。

本项目的 `hermes-install-watchdog.sh` 只读检查固定上游 checkout：HEAD 正确且工作区干净时没有输出；安装缺失、版本漂移或上游目录出现修改时输出一行。它不联网、不写文件、不读取私人资料。

```bash
export HERMES_HOME="${HOME}/.config/worklikerico/hermes"
hermes_bin="${HOME}/.local/share/worklikerico/hermes-venv/bin/hermes"

install -m 755 integrations/hermes/scripts/hermes-install-watchdog.sh \
  "${HERMES_HOME}/scripts/hermes-install-watchdog.sh"

"${hermes_bin}" cron create "every 1h" \
  --no-agent \
  --script hermes-install-watchdog.sh \
  --deliver local \
  --failure-deliver local \
  --name hermes-install-watchdog \
  --paused \
  --paused-reason "H01 template; keep paused until an explicit local test"
```

不启动 gateway 的手动验证需短暂 resume；上游拒绝直接运行 paused job。确认 gateway 未运行后执行一次并立即恢复暂停：

```bash
"${hermes_bin}" cron resume hermes-install-watchdog
"${hermes_bin}" cron run hermes-install-watchdog
"${hermes_bin}" cron pause hermes-install-watchdog
"${hermes_bin}" cron runs hermes-install-watchdog --limit 5
"${hermes_bin}" cron list
"${hermes_bin}" cron doctor
```

注意：本机负例中，script 以 7 退出后 ledger 正为 `failed`，但 `hermes cron run` 自身仍返回 shell code 0。验收必须读取 `cron runs`/ledger 的 execution 状态，不能只用外层命令退出码。

本阶段不运行 `hermes gateway install`。前台 gateway 的一次到期 tick、暂停和停止结果记录在安装验收中；后续阶段仍需验证进程重启和有副作用任务的幂等边界。

来源：[Hermes cron 官方文档](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/website/docs/user-guide/features/cron.md)。
