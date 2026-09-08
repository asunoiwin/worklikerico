# Hermes 模型与消息渠道准备

本文件只给出登录和配置顺序。模板默认禁用渠道且 allowlist 为空；不要把真实 token、secret、用户 ID、群 ID 写入仓库。

## 启动前权限门

上游 `hermes config check` 检查配置版本和结构，但不会禁止用户有意填写 `*`。当前固定版本的 adapter 已做本地负例验证：Telegram 的 `allow_from: []`/`group_allow_from: []` 会拒绝未知私聊和群发件人；WeCom 的 `dm_policy/group_policy: allowlist` 配合空列表也会拒绝未知私聊和群。因此仅填 token、仍保留本模板的空 allowlist 不会变成“允许所有人”。

为了避免后来误填通配符或 allow-all 环境变量，启用任何消息平台前再运行项目 preflight。它不会输出 token/secret：

```bash
export HERMES_HOME="${HOME}/.config/worklikerico/hermes"
"${HOME}/.local/share/worklikerico/hermes-venv/bin/python" \
  integrations/hermes/verify-safe-config.py --home "${HERMES_HOME}"
```

preflight 对已启用平台还要求非空 DM user allowlist；群列表可以为空，此时所有群都被拒绝。它拒绝所有当前模板和固定版上游可达范围中的 `*`，也拒绝 `*_ALLOW_ALL_USERS=true`。企业微信群范围只有 YAML `platforms.wecom.extra.group_allow_from`；固定版不消费 `WECOM_GROUP_ALLOWED_CHATS` 或 `WECOM_GROUP_ALLOWED_USERS`，preflight 会拒绝这两个易误认的变量。通过只证明本地访问策略为 fail-closed，不证明 token 有效或平台已能收发。

## OpenAI Codex provider

首期保留 `model.openai_runtime: auto`，即 Hermes 默认 agent runtime。它与 Codex app-server runtime 是两件事。

```bash
export HERMES_HOME="${HOME}/.config/worklikerico/hermes"
hermes_bin="${HOME}/.local/share/worklikerico/hermes-venv/bin/hermes"
"${hermes_bin}" auth add openai-codex
```

命令会显示 device-code URL 和 code，需要 Rico 在浏览器中交互登录。凭据写入隔离 `HERMES_HOME` 的 auth store；不要复制 `~/.codex/auth.json`。登录后先运行一个两轮本地会话，再判断模型链路通过。套餐资格及如何计入 Codex 限额尚未被 Hermes 官方文档明确说明。

不要在首期运行 `/codex-runtime codex_app_server`。该操作会迁移 MCP/plugins 并写 `~/.codex/config.toml` 的 managed block；后续只在单独 coding profile 评估。

## Telegram bot

1. 在 Telegram 官方 `@BotFather` 执行 `/newbot`，本地保存 token。
2. 先由目标用户向 bot 发消息；用 `/whoami` 或 gateway 日志确认数值 user ID。
3. 把 `TELEGRAM_BOT_TOKEN` 和唯一允许的 `TELEGRAM_ALLOWED_USERS` 写入隔离 `HERMES_HOME/.env`；群 allowlist 初始留空。
4. 在 `config.yaml` 把 `platforms.telegram.enabled` 改为 `true`；保持 `guest_mode: false`、`observe_unmentioned_group_messages: false`。
5. 本机已有用户服务时先停止它，再前台运行 `hermes gateway` 测试一条新私聊消息和回复；通过后恢复用户服务，避免同时运行两个 gateway。

Telegram 内建接入不能读取个人账号旧历史。若以后启用群消息，先分别填 sender 和 chat allowlist；不要用 `*`。BotFather 隐私模式默认开启，是否关闭必须按群范围单独决定。

## 企业微信智能机器人

1. 企业管理员在管理台创建 AI Bot；优先用 Hermes `gateway setup` 的扫码创建流程，失败时手工取得 Bot ID/Secret。
2. 把 `WECOM_BOT_ID`、`WECOM_SECRET` 写入隔离 `.env`。
3. 先取得获准的 user ID；把 `dm_policy` 保持为 `allowlist` 并填写 `allow_from`。群初始保持 `group_policy: allowlist` 且 `group_allow_from` 为空；后续群 ID 只写入 YAML，不写不存在的企业微信群环境变量。
4. 在 `config.yaml` 把 `platforms.wecom.enabled` 改为 `true`。
5. 本机已有用户服务时先停止它，再前台运行 `hermes gateway` 实测一条获准私聊消息、回复和重连；通过后恢复用户服务。

WebSocket 模式只需出站网络，不要求公网 callback。它只收机器人可见的新消息，不读取工作会话历史。若租户没有 AI Bot 权限，再单独评估自建应用 callback；该路径要求管理员、Corp ID/Secret/Agent ID、Token/AES key 和公网 HTTPS。

## 模板应用

```bash
export HERMES_HOME="${HOME}/.config/worklikerico/hermes"
cp -n integrations/hermes/env.template "${HERMES_HOME}/.env"
cp -n integrations/hermes/config.template.yaml "${HERMES_HOME}/config.yaml"
chmod 600 "${HERMES_HOME}/.env" "${HERMES_HOME}/config.yaml"
```

这些命令保留既有文件；已有 GPT/MiMo 配置时只补充所需渠道字段。复制后先填本地 secrets，再启用单一渠道。不要把填好的文件复制回仓库。

## 官方依据

- [Providers](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/website/docs/integrations/providers.md)
- [Codex app-server runtime](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/website/docs/user-guide/features/codex-app-server-runtime.md)
- [Telegram](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/website/docs/user-guide/messaging/telegram.md)
- [WeCom WebSocket](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/website/docs/user-guide/messaging/wecom.md)
- [WeCom self-built app callback](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/website/docs/user-guide/messaging/wecom-callback.md)
