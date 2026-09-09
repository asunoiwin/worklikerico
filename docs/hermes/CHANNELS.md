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

preflight 对已启用平台还要求非空 DM user allowlist；WeCom 在群策略为 allowlist 且群列表为空时拒绝所有群。Telegram 的全局用户 allowlist 也适用于群：即使群列表为空，已允许用户仍能在 bot 已加入的群内触发，因此不能把空群列表理解为全群禁用。它拒绝所有当前模板和固定版上游可达范围中的 `*`，也拒绝 `*_ALLOW_ALL_USERS=true`。企业微信群范围只有 YAML `platforms.wecom.extra.group_allow_from`；固定版不消费 `WECOM_GROUP_ALLOWED_CHATS` 或 `WECOM_GROUP_ALLOWED_USERS`，preflight 会拒绝这两个易误认的变量。通过只证明本地访问策略为 fail-closed，不证明 token 有效或平台已能收发。

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

1. 在 Telegram 官方 `@BotFather` 先核对已有机器人，无可复用入口时执行 `/newbot`，本地保存 token。首期仅服务本人时，通过 `/setjoingroups` 关闭加入群，私聊仍可用；团队阶段确定群范围后再开启。
2. 先由目标用户向 bot 发消息；用 `/whoami` 或 gateway 日志确认数值 user ID。
3. 把 `TELEGRAM_BOT_TOKEN` 和唯一允许的 `TELEGRAM_ALLOWED_USERS` 写入隔离 `HERMES_HOME/.env`；群 allowlist 初始留空。
4. 在 `config.yaml` 把 `platforms.telegram.enabled` 改为 `true`；保持 `guest_mode: false`、`observe_unmentioned_group_messages: false`。
5. 本机已有用户服务时先停止它，再前台运行 `hermes gateway` 测试一条新私聊消息和回复；通过后恢复用户服务，避免同时运行两个 gateway。

Telegram 内建接入不能读取个人账号旧历史。若以后启用群消息，先明确 sender 与 chat 授权关系：全局用户列表允许该用户在各种聊天类型触发；`group_allowed_chats` 则授权指定群内全部成员。不要将两者误当成必须同时满足的条件，也不要用 `*`。BotFather 隐私模式默认开启，是否关闭必须按群范围单独决定。

## 企业微信智能机器人

**API 长连接模式不需要本机公网 IPv4、域名或回调 URL**；Hermes 主动连接企微官方 WebSocket。已有域名也无需用于这条路径。先核对现有机器人类型：

| 现有入口 | 能否直接接 Hermes |
|---|---|
| 智能机器人 → API 模式 → 使用长连接，提供 Bot ID/Secret | 可使用原生 `wecom` |
| 自建应用，提供 Corp ID/Agent ID 与接收消息 URL | 使用不同的 callback adapter，需要公网 HTTPS；本次优先长连接 |
| 某个群的 Webhook URL | 只能向该群推送，不是双向收件入口 |

先检查创建/管理权限、连接模式、可使用成员和是否已有服务连接。首期成员范围只包含本人；不要为了接入机器人申请不需要的通讯录或其他权限。同一机器人长连接与 URL 回调互斥，且只有一个有效长连接，接管前须确认已有连接用途。

1. 先检查现有 AI Bot 是否可复用；否则由有创建权限的成员或管理员创建，选择 API 模式、使用长连接，并取得 Bot ID/Secret。也可使用 Hermes `gateway setup` 的扫码流程。
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

## 团队阶段的边界

先完成本人私聊验证，再扩大成员或群范围。机器人只能收它可见的新信息，客户端登录不赋予机器人全量历史读取权。Telegram 开启隐私模式时主要收到明确指向它的命令和回复；关闭隐私模式或设为群管理员会改变可见范围。企微的群接入也受机器人类型与平台规则约束，不能仅因已加群就宣称在记录所有讨论。

Hermes 的会话分流不等于权限隔离：长期记忆和工具属于 profile，guest/slash 限制不能限制普通聊天调用的工具。未来开放多人前，应使用独立的受限团队配置并验证工具与数据范围，不能把个人助手的完整记忆和本机权限直接共享。当前首期无需为此另建系统。

2026-09-09 当前配置窄查：两个平台各只允许本人，allow-all 均关闭；没有 profile 路由且未启用 multiplex。Telegram 官方 `getMe` 确认不能加入群、未启用读取群内全部消息。注意，禁止加入新群不等于证明机器人已退出所有既有群；全局用户允许列表在群内的生效规则仍需单独核对。

原生会话键包含 profile、平台、聊天类型与 chat ID；当前普通群默认按发言者分会话，同一 thread 默认共享上下文。同一 profile 下的 memories、sessions、skills 和 workspace 仍共享。当前版本的 profile 路由支持平台及 guild/chat/thread，不按 user ID 路由；独立 profile 目录本身也不是操作系统的文件权限边界。团队开放前必须分别验证会话上下文、记忆/附件和本地工具权限，不把会话键分开当作多用户隔离已完成。

机器人消息权限也不代表邮箱、微盘或个人历史权限。文件消息需要渠道接收与工具处理；本机文件由后台进程按系统权限访问。邮件读取、附件处理、草稿与发送需分别接入并验证对应账户和执行授权，当前未验收邮件能力。本次工作习惯研究通过已登录客户端只读历史，不是机器人自动取得了个人全部聊天。

官方补充：[Telegram 收件范围](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get) · [BotFather 群设置](https://core.telegram.org/bots/features#botfather) · [企微长连接接入](https://cloud.tencent.cn/document/product/1831/137051) · [企微连接模式限制](https://cloud.tencent.cn/document/product/1759/121473)。
