# H01/H03 本地验收记录

时间：2026-09-08，macOS 26.5.2 arm64。所有测试使用 `HERMES_HOME=${HOME}/.config/worklikerico/hermes`。GPT provider 已完成原生 OAuth；没有启用消息平台、没有安装用户服务、没有发送外部消息。

| 检查 | 结果 | 证据与边界 |
|---|---|---|
| 上游固定 | PASS | annotated tag `v2026.9.7` 指向 commit `2237be355906fbe6065ce1815711eee52b2d646e`；tag 无 Git 签名 |
| locked 安装 | PASS | Python 3.11.15 独立 venv；`uv sync --extra all --extra messaging --locked` 解析 255 包；Telegram SDK 22.8 可导入 |
| CLI | PASS | `Hermes Agent v0.21.1 (2026.9.7)`，OpenAI SDK 2.24.0 |
| `config check` | PASS | schema v41；渠道均 disabled、无 auth |
| `doctor` | 有限 PASS | runtime/SQLite/核心包和 Telegram SDK 通过；明确报告 provider 未登录、浏览器未装；独立 venv 因不在 checkout 内触发已知路径警告。doctor 退出 0 不能替代阅读结果 |
| 私有数据隔离 | PASS | `auth.json` 不存在，0 memory 文件、0 session 文件、state DB 0 sessions，无 Codex managed block；只有上游 bundled skills/default SOUL |
| Telegram 空 allowlist | PASS（拒绝） | 固定版本 adapter 本地调用：未知 DM=false，未知群发件人=false，无网络 |
| WeCom 空 allowlist | PASS（拒绝） | `dm_policy/group_policy=allowlist` 时未知 DM=false、未知群=false，无网络 |
| 项目 preflight | PASS | 安全模板通过；把 Telegram 改为 enabled + `allow_from: ['*']` 后退出 1 |
| cron 创建负例 | PASS（拒绝） | `--no-agent` 无 script 退出 1；`../../outside.sh` 路径逃逸退出 1；均未创建 job |
| paused cron | PASS（拒绝） | paused job 不能被 `cron run` 隐式执行，0 execution |
| no-agent 到期 tick | PASS | 前台 gateway 中按时执行一次；execution `f3ddfd75a67742d9ab8daea864026f4b` completed；空 stdout 无投递；随后 job paused、gateway stopped |
| cron 失败台账 | PASS | script exit 7，execution `2a7d3ece00694bb8a008a3a9497326a5` failed 且保留 stdout；外层 `cron run` 却退出 0，故必须查 ledger |
| cron 持久化 | PASS | 新 CLI 进程从 `jobs.json` 读到同一 paused job；`executions.db` 读到 completed run；gateway 当前停止 |
| Kanban 持久化/去重 | PASS | `kanban.db` 创建；同一 idempotency key 两次创建均返回 `t_04ac3c74`；不存在 task 的 complete 退出 1 |
| Kanban blocked canary | PASS，发现语义边界 | `--initial-status blocked` 若没有 typed block reason，会被 promotion pass 自动推到 ready；随后显式 `block --kind needs_input` 才稳定为 blocked。不能只看 create 返回对象 |
| GPT 订阅模型调用 | PASS | `openai-codex` 为 logged in；`gpt-5.4-mini` 纯文本请求约 4.02 秒返回指定内容；无 API Key、fallback 或 gateway |
| GPT 合成本地文件任务 | PASS | 私有临时目录内预加载 `work-like-rico`，约 15.63 秒正确写出 2 条未完成虚构待办；结果文件存在、内容顺序正确，输入 SHA-256 前后相同 |
| Telegram/企业微信实网 | NOT RUN | 缺 token/租户权限；adapter 配置仍 disabled |

当前保留状态：`hermes-install-watchdog` 每分钟定义为 paused；gateway 未运行；失败 probe 的 job/script 已移除；Kanban canary 为 blocked，不会被 dispatcher 执行。

GPT 验证只覆盖订阅推理和隔离的合成本地文件读写。真实资料处理、社交收件、自动回复、定时任务和无人值守闭环仍未验证。本机依赖 HTTP 代理时，Hermes 私有 `.env` 需要显式提供 `HTTP_PROXY=http://localhost:PORT`、`HTTPS_PROXY=http://localhost:PORT` 和本机 `NO_PROXY`；不要把私人代理地址或凭据写入仓库。

## 独立审计修复记录

2026-09-08 的独立复验发现：模板曾公开 `WECOM_GROUP_ALLOWED_CHATS`，但 preflight 没有检查它，写成 `*` 仍退出 0。根因是模板与校验器各自维护范围字段，字段集合发生偏差；而固定上游 v0.21.1 实际并不消费这个变量。

修复已完成，状态为**待独立复验**：

- 从模板移除无效的 `WECOM_GROUP_ALLOWED_CHATS`，并让 preflight 明确拒绝它及同类的 `WECOM_GROUP_ALLOWED_USERS`，避免配置看似生效、实际没有边界。
- 把固定上游实际消费的全局、Telegram、企业微信身份和群范围纳入同一测试矩阵，包括 `GATEWAY_ALLOWED_USERS`、Telegram 三个范围变量、企业微信 YAML 群范围及 `groups.<id>.allow_from`。
- 本地回归覆盖每个范围字段的通配符拒绝、allow-all 拒绝、已启用平台空 DM 范围拒绝，以及明确非通配范围通过。自测通过不替代独立复验，原独立审计 FAIL 仍以复验结果为准。

本次没有重跑 cron。此前 cron 的真实 tick、失败台账与退出码语义证据未受配置校验器修改影响。

修复后本地验证：

- `${HOME}/.local/share/worklikerico/hermes-venv/bin/python -m unittest discover -s integrations/hermes/tests -v`：10 项通过，覆盖所有已登记范围字段的通配符、空启用、显式合法范围和模板字段同步。
- 用审计原配置启用 WeCom 并写入 `WECOM_GROUP_ALLOWED_CHATS=*`：preflight 退出 1，明确指出该变量未被固定版消费。
- 对当前隔离 `${HOME}/.config/worklikerico/hermes` 运行 preflight：通过；消息平台仍 disabled。
