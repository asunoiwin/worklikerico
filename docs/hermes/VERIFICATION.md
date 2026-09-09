# H01/H03 本地验收记录

原生记忆补充（2026-09-09）：15 项隔离存储与审批检查通过后，使用两个独立 profile、相同问题进行了两次 MiMo 实际调用。有既存虚构偏好的会话正确回答“青绿色方格纸”，无该记录的会话回答“不知道”；每次 1 次主 API、0 次工具调用，分别用时 9.01 秒和 14.18 秒。标题生成和后台复盘关闭，测试未改真实记忆、默认模型或日常任务。这证明新会话能读取内置记忆及本例无记录不猜测，不代表长期工作满意度或强权限隔离已验收。

最新状态（2026-09-09）：Telegram 与企业微信本人私聊均已完成真实请求、工具执行和准确回复，当前 GPT 默认型号为 `gpt-5.6-sol`。企微已由真实本人私聊设置 home channel，并完成一次原生定时任务主动投递。MiMo 补充通过一次原生 CLI 文件任务：实际读取、写入及回读，产物和源文件哈希均独立核对。下方早期测试表是对应日期的历史快照，不能作为当前渠道或型号状态。

时间：2026-09-08，macOS 26.5.2 arm64。所有测试使用 `HERMES_HOME=${HOME}/.config/worklikerico/hermes`。GPT provider 已完成原生 OAuth，MiMo Token Plan 已通过原生短文本调用；消息平台仍未启用；当前已安装并运行原生用户级 gateway service；初期测试没有发送外部消息；后续已按用户明确授权向指定企微联系人发送一条接入协助请求。

| 检查 | 结果 | 证据与边界 |
|---|---|---|
| 上游固定 | PASS | annotated tag `v2026.9.7` 指向 commit `2237be355906fbe6065ce1815711eee52b2d646e`；tag 无 Git 签名 |
| locked 安装 | PASS | Python 3.11.15 独立 venv；`uv sync --extra all --extra messaging --locked` 解析 255 包；Telegram SDK 22.8 可导入 |
| CLI | PASS | `Hermes Agent v0.21.1 (2026.9.7)`，OpenAI SDK 2.24.0 |
| `config check` | PASS | schema v41；渠道均 disabled；provider auth 由独立命令验收 |
| `doctor` | 有限 PASS | runtime/SQLite/核心包和 Telegram SDK 通过；H01 快照当时 provider 未登录、浏览器未装；独立 venv 因不在 checkout 内触发已知路径警告。doctor 退出 0 不能替代阅读结果 |
| 私有数据隔离 | PASS | H01 初始为 0 memory、0 session、state DB 0 sessions，无 Codex managed block；后续 OAuth 由授权任务独立写入，没有复制 Codex auth；初始仅有上游 bundled skills/default SOUL 和明确接入的 `work-like-rico`；随后用本仓短工作角色替换 SOUL，原文件已私有备份 |
| Telegram 空 allowlist | PASS（拒绝） | 固定版本 adapter 本地调用：未知 DM=false，未知群发件人=false，无网络 |
| WeCom 空 allowlist | PASS（拒绝） | `dm_policy/group_policy=allowlist` 时未知 DM=false、未知群=false，无网络 |
| 项目 preflight | PASS | 安全模板通过；把 Telegram 改为 enabled + `allow_from: ['*']` 后退出 1 |
| cron 创建负例 | PASS（拒绝） | `--no-agent` 无 script 退出 1；`../../outside.sh` 路径逃逸退出 1；均未创建 job |
| paused cron | PASS（拒绝） | paused job 不能被 `cron run` 隐式执行，0 execution |
| no-agent 到期 tick | PASS | 前台 gateway 中按时执行一次；execution `f3ddfd75a67742d9ab8daea864026f4b` completed；空 stdout 无投递；随后 job paused、gateway stopped |
| cron 失败台账 | PASS | script exit 7，execution `2a7d3ece00694bb8a008a3a9497326a5` failed 且保留 stdout；外层 `cron run` 却退出 0，故必须查 ledger |
| cron 持久化 | PASS | 新 CLI 进程从 `jobs.json` 读到同一 paused job；`executions.db` 读到 completed run；该验证后测试 job 已清理 |
| Kanban 持久化/去重 | PASS | `kanban.db` 创建；同一 idempotency key 两次创建均返回 `t_04ac3c74`；不存在 task 的 complete 退出 1 |
| Kanban blocked canary | PASS，发现语义边界 | `--initial-status blocked` 若没有 typed block reason，会被 promotion pass 自动推到 ready；随后显式 `block --kind needs_input` 才稳定为 blocked。不能只看 create 返回对象 |
| GPT 订阅模型调用 | PASS | `openai-codex` 为 logged in；`gpt-5.4-mini` 纯文本请求约 4.02 秒返回指定内容；无 API Key、fallback 或 gateway |
| GPT 合成本地文件任务 | PASS | 私有临时目录内预加载 `work-like-rico`，约 15.63 秒正确写出 2 条未完成虚构待办；结果文件存在、内容顺序正确，输入 SHA-256 前后相同 |
| MiMo 订阅模型调用 | PASS | 原生 `xiaomi` / `mimo-v2.5-pro` 无工具短文本约 3.82 秒成功；默认仍为 GPT，无 fallback；后台重启后由 launchd 监督运行 |
| 原生后台本地资料任务 | PASS（纠正后） | 同一任务自动领取、执行并生成真实计划摘要；输入哈希一致，首次与第二次内容不合格，第三次内容复验通过，详见下文 |
| Telegram Bot API 身份与群设置 | PASS | BotFather创建后，官方getMe确认身份；配置本人首期禁群后getMe确认can_join_groups=false；无webhook，实际收件仍待首条消息 |
| Telegram/企业微信实网收发 | NOT RUN | 两个客户端已登录；TG尚未取得本人启动消息，企微Rico已确认API模式与长连接接入权限，单bot连接详情未取得；adapter配置仍disabled |

当前保留状态：cron 无 job；gateway 由 launchd 运行；失败 probe 的 job/script 已移除；Kanban canary 已在保留快照后归档，未归档任务仅有已完成的真实本地资料任务，无待执行任务。

GPT 已覆盖订阅推理、本地文件读写与一次原生后台资料整理。MiMo 仅验证无工具短文本回复。社交收件、自动回复、模型定时任务和持续日常运行仍未验收。本机依赖 HTTP 代理时，Hermes 私有 `.env` 需要显式提供 `HTTP_PROXY=http://localhost:PORT`、`HTTPS_PROXY=http://localhost:PORT` 和本机 `NO_PROXY`；不要把私人代理地址或凭据写入仓库。

## 独立审计修复记录

2026-09-08 的独立复验发现：模板曾公开 `WECOM_GROUP_ALLOWED_CHATS`，但 preflight 没有检查它，写成 `*` 仍退出 0。根因是模板与校验器各自维护范围字段，字段集合发生偏差；而固定上游 v0.21.1 实际并不消费这个变量。

修复已完成，配置范围的独立定向复验 **PASS**；真实渠道仍未验收：

- 从模板移除无效的 `WECOM_GROUP_ALLOWED_CHATS`，并让 preflight 明确拒绝它及同类的 `WECOM_GROUP_ALLOWED_USERS`，避免配置看似生效、实际没有边界。
- 把固定上游实际消费的全局、Telegram、企业微信身份和群范围纳入同一测试矩阵，包括 `GATEWAY_ALLOWED_USERS`、Telegram 三个范围变量、企业微信 YAML 群范围及 `groups.<id>.allow_from`。
- 本地回归覆盖每个范围字段的通配符拒绝、allow-all 拒绝、已启用平台空 DM 范围拒绝，以及明确非通配范围通过。独立复验直接运行原失败输入与合法范围、通配符、allow-all、缺范围及遗留变量矩阵，结果均符合预期。

本次没有重跑 cron。此前 cron 的真实 tick、失败台账与退出码语义证据未受配置校验器修改影响。

修复后本地验证：

- `${HOME}/.local/share/worklikerico/hermes-venv/bin/python -m unittest discover -s integrations/hermes/tests -v`：10 项通过，覆盖所有已登记范围字段的通配符、空启用、显式合法范围和模板字段同步。
- 用审计原配置启用 WeCom 并写入 `WECOM_GROUP_ALLOWED_CHATS=*`：preflight 退出 1，明确指出该变量未被固定版消费。
- 对当前隔离 `${HOME}/.config/worklikerico/hermes` 运行 preflight：通过；消息平台仍 disabled。

## macOS 原生服务验收

时间：2026-09-08 18:04（Asia/Shanghai）。启动前没有同名 launchd job 或 gateway 进程；Telegram/企业微信均为 `false`，cron 无 job，唯一 Kanban canary 为 typed `needs_input` block。

| 检查 | 结果 | 证据与边界 |
|---|---|---|
| 原生安装 | PASS | `hermes gateway install --no-start-now --start-on-login` 创建并加载 `${HOME}/Library/LaunchAgents/ai.hermes.gateway.plist` |
| 一次实际启动 | PASS | launchd `state=running`，监督 PID 3803，gateway PID 3809；工作目录与 `HERMES_HOME` 均为隔离目录 |
| service 定义 | PASS | `hermes gateway status` 报告 plist 与当前固定安装一致，支持登录自启与崩溃重启 |
| 渠道静默 | PASS | 配置仍为 Telegram=false、WeCom=false；日志显示 `No messaging platforms enabled` 和 `Channel directory built: 0 target(s)` |
| 调度静默 | PASS | cron 仍无 job；canary 仍 blocked/unassigned，带 `needs_input` 原因；没有新 execution 或 worker dispatch |
| 模型静默 | PASS | 本次服务启动日志只有 runtime/tool warmup 和 dispatcher idle，没有 agent dispatch、provider/API 请求或 session turn；未运行模型命令 |

`--no-start-now` 与 `--start-on-login` 在本机组合使用时，launchd 加载含 `RunAtLoad` 的 plist 后仍立即启动。该安装已经构成一次启动，因此没有再调用 `hermes gateway start`。当前服务保持运行。

回滚：先运行 `hermes gateway stop`，再运行 `hermes gateway uninstall`；这只移除后台入口，保留隔离 Home 与台账。

## 默认工作角色与原生后台任务

本仓 `integrations/hermes/SOUL.md` 已应用到隔离 Hermes Home，原上游角色有私有备份。规则来自明确要求及历史任务：简单优先、授权内直接执行、保留源文件、检查当前结果、有事再提醒。未添加固定提醒频率或性格推断。隔离服务目录下的 `prompt-size --json` 确认额外 AGENTS/cwd 上下文为 0。

任务 `t_64ad4552` 由原生 gateway 自动领取，读取当时的实施状态、计划和实际 git 状态，生成一份简短本地摘要。没有手动 dispatch，没有新调度器，也没有发送外部消息。三次运行的输入哈希均保持一致：

- run 2：执行链路通过，但内容重复询问已有授权并凭空增加一页计划，内容验收不通过。
- run 3：消除重复确认后仍增加无必要的整理工作，内容验收仍不通过。
- run 4：补充“建议动作必须有当前可执行的未完成事实，否则写暂无”后，同一任务复验通过。原产物与失败历史均保留。

该任务的输入冻结在 MiMo 接入前，因此原产物仍将 MiMo 写为待接入；这是输入快照的边界，不是当前状态。订阅现状以本次独立调用结果和订阅说明为准。此任务证明一次本地资料任务可后台自动执行，不能推导为社交收件或长期无人值守已验收。

## 2026-09-08 晚间真实渠道准备

- Telegram：通过官方 BotFather 创建显示名 rico 的机器人；用户提供的凭据已通过官方 `getMe` 身份校验并写入私有配置，原变量逐值保留且有修改前备份。
- 本人首期设置：BotFather `/setjoingroups` 实际返回 `DISABLED`，随后 `getMe` 确认 `can_join_groups=false`；隐私模式保持开启，无 webhook。
- 本人 ID：有限 `getUpdates` 检查尚无启动消息，因此没有猜测用户 ID、没有启用渠道。真实收件、模型处理、回复仍未验收。
- 企业微信：当前已登录，现有 Rico 为企业管理员创建的 API 模式 BOT；全局管理页允许成员使用长连接，并显示单成员可见范围。尚未将该成员等同当前登录本人；单 bot 的连接方式、Bot ID/Secret 与占用状态还需详情页核对。
- 按用户授权向指定企微联系人发送了一条 Telegram 首次启动协助请求，发送后在会话中可见。后来请求打开 Rico 详情页的补充消息未发送，不能把草拟请求算作已送达。
- 桌面限制：BotFather 普通聊天输入可用并完成设置；新 bot 开始按钮和企微内嵌详情链接不在可操作 AX 树中，坐标方式不受当前接口支持。有限恢复已停止，没有修改企微设置、重置 Secret 或创建重复机器人。

## 2026-09-09 Telegram 真实任务验收

- 本人身份：用户发送消息后，官方更新中取得同一非机器人用户的两条私聊消息，时间与本轮反馈一致；据此配置精确本人允许列表。BotFather 的加入群限制仍关闭，没有开放团队或群。
- 启动边界：固定版本初次 polling 会丢弃待收更新。启动前已私有保存两条启动命令和问候，不含实际待办；通过新消息验收，没有修改上游 polling 行为。
- 首次实测失败：09:57 的只读 Git 请求实际到达网关，机器人也实际回传错误，但旧默认 `gpt-5.4-mini` 被订阅接口拒绝。未设置 home channel 的提示与模型错误无关，不能用设置汇报会话替代模型修复。
- 修复：读取当前 OAuth 账号可用模型目录，改用 `openai-codex/gpt-5.6-sol`。短调用约 5.8 秒返回指定结果；原生网关重启后 Telegram 显示 connected，项目 preflight 通过。
- 最终实测通过：10:09 在本人客户端向 rico 私聊发送同一只读 Git 请求；状态库记录实际 skill 读取和两次 terminal 工具调用，网关约 20.7 秒完成两次模型请求并发出结果。10:10 客户端收到最终回复：分支 `main`、无未提交改动、最近提交 `55299ff`，标题与冻结仓库一致。客户端发送与最终消息均有独立 UI 证据，仓库在验收时保持干净。
- 本次验收证明本人 Telegram 消息可以触发真实本地只读任务并交付结果。它不证明企业微信已接通、历史聊天可全量读取、团队隔离或长期无人值守已验收；home channel 尚未设置，主动推送和定时跟进尚未启用。

原始消息、界面证据、配置备份和运行日志保留本地私有目录，未进入仓库。

## 2026-09-09 企业微信原生长连接验收

- 按用户明确授权，将 Rico 从旧 OpenClaw URL 回调切换为长连接并保存；使用用户提供的 Bot ID/Secret，未重置凭据。此方式仅需出站 WSS，不需要本机公网 IPv4、回调域名或新增文档等权限。
- 本人识别：原生 adapter 使用一次性内存拒绝策略监听，仅匹配本人客户端发出的唯一测试词并私有保存 sender ID；未运行模型、回复或保存正文。随后持久配置改为精确本人 DM allowlist，群策略为 allowlist 且范围为空。
- 正式启用：项目 preflight 通过，在无活跃 agent 时单次重载原生 gateway；Telegram 与 WeCom 均恢复 connected。原 GPT、MiMo、代理及 Telegram 设置保留。
- 工具任务：本人 Rico 私聊发送只读 Git 请求，实际会话使用 `openai-codex/gpt-5.6-sol`，记录两次模型调用及 `skill_view`、`terminal` 两次工具调用。独立客户端收到 `main`、工作区干净、最近提交 `0c221ad` 及正确标题，与冻结仓库相符。
- 边界负例：最终配置下未知 DM 和所有群在本地 adapter 验证中均被拒绝；没有向未知账号或群发送实网测试。
- 主动汇报准备：本人私聊执行一次 `/sethome`，原生成功回执确认 home channel 已设置；主动投递与日常任务需要单独验证，不能用此回执代替送达。
- OpenClaw 清理：按授权卸载旧程序及专属微信插件、清理本机启动项；核查无相关进程、加载 job、命令和全局安装包。旧配置和用户数据已整体私有隔离保留。本机清理不证明旧 URL 对应远端服务已停止；用户明确不要求备份弃用的企微回调字段。

企业微信界面最终显示多人使用且成员列表仅一人，Hermes 的精确本人允许列表独立生效。团队开放、历史聊天导入与长期无人值守不属于本次私聊验收结论。

## 2026-09-09 企业微信主动投递

建立一个原生一次性 cron job，使用 `gpt-5.6-sol` 订阅输出固定验证句，投递到本人 home channel。任务由现有 gateway 的到期 tick 执行，复用正式 WeCom adapter；没有启动第二个 gateway、独立 `cron tick` 或临时 WSS。

10:55 的 durable run 完成，记录一次模型 API 调用，无工具或错误。独立客户端在同一分钟收到机器人主动消息，期间用户没有发送新内容。网关 PID 保持不变，Telegram 与 WeCom 均维持 connected。

验证定义与运行证据已私有保存，一次性 job 已移除，未遗留活跃验证任务。该结果证明原生主动私聊投递可用，不能代替日常监测的基线、去重和持续运行验收。

## 日常监测暂停边界

用户随后明确要求先完成基础环境、工作习惯分析与插件落实，再做日常任务。已停止日常配置与验收：没有创建日常 job，没有执行基线或变化 tick，没有追加真实看板任务或评论。最后检查没有活跃定时任务；一次性投递验证 job 已删除，旧 H01 安装巡检 job 保留 paused，不会自动运行。两个正式消息渠道继续在线。

准备阶段的监测脚本虽通过单元测试，独立静态复核仍发现自由文本输出、全局自增 ID 和纯租约事件导致的内容与稳定性问题；代码、测试及提示词已私有暂存并从公开工作区和运行脚本目录移出，未作为已验收功能发布。显式时区设置保留，但没有启用任何日常计划。


## 2026-09-09：首个专项技能 XMind

通过统一安装器仅选择 `xmind`，在本项目 Hermes Home 下建立指向唯一仓库源码的链接。原生 `skills list --source local` 显示 local/enabled，原生 prompt loader 读取到实际 SKILL.md。默认 Codex/Claude 安装行为保持不变；重复安装、同名目录保留、不兼容选择在写入前失败等四项安装器测试通过，并经过独立复核。

一次真实 `openai-codex` / `gpt-5.6-sol` CLI 任务，通过原生 `-s xmind` 显式预加载技能，在 120 秒运行预算内约 75 秒完成，记录 7 次 API 调用、6 个工具轮次。模型依据隔离合成输入生成 Zen 格式 XMind，再读取输出；执行侧另行核对六个节点的层级、指定关系与源输入哈希，结果一致。没有向聊天渠道发消息或创建定时任务。

该验证证明单项技能能被原生列表发现、显式预加载并用于本地文件工作；未覆盖不指定技能的自然语言自动选择，也不等于真实机器人附件收发、全部 XMind 功能或可视化排版已经验收。原始输入、输出、执行日志与校验报告留在本机受限目录。


同日追加一次未指定 `-s/--skills` 的普通工作请求，且未提示技能、脚本或输入 schema：模型首轮自主选择 `skill_view(xmind)`，真实创建了正确文件；但回读命令被拦截后，它只读取了检查请求 JSON，未实际回读产物，却声称检查完成。该次结论为“自动选技与创建通过，模型自主回读失败，终态后的独立产物校验通过”。不能用独立校验补写模型闭环通过。旁路已将示例改为 JSON 文件输入，并让创建器在返回成功前复用现有 reader 重新读取实际文件、核对结构并返回校验信息。三项确定性回归与独立审查通过，现有安全检查保持不变。按用户最新主线安排，没有再次执行模型复验；这不能把先前自然语言行为失败改记为通过。


## 预期规则的原生按需加载与真实项目规划

2026-09-09，以统一管理入口项目在提交 `8d96c41` 时的五份材料副本进行一次只读规划。调用未点名或预加载技能，Hermes 主动使用 `skill_view(work-like-rico)`，再读取 `references/expectation-and-plan.md`。持久记录显示主任务四次 API 调用、另一次标题生成，约 119 秒；读取范围符合约束，唯一写动作是方案文件，没有安装、更新、外发或修改配置。

结果为部分满足：模型能发现插件缺少选择参数、Hermes 核心未纳入清单等实际缺口，但将清单的 19 个技能目录项误写为 18 项；方案只新增查询脚本，仍要求用户区分多个安装入口，未充分减少管理负担。因此仅确认核心规则在原生入口下实际按需加载，不将方案充分性、事实准确性或持续自主监督记为通过。主线程保留原响应，使用程序目录计数与统一管理入口推进实际实现，本轮不重复模型请求。


## 统一管理入口的安装验收

2026-09-09，`scripts/manage.py` 已统一目录查询、平台/模块选择、安装和快进更新，并将核心技能纳入 Hermes 目录。34 项脚本回归通过，独立审查复现了后项冲突、拉取后目录变化、大小写路径别名和真实外来入口等关键边界。

真实 Hermes 首次重复安装因 `Projects`/`projects` 同一目录被错误判为外来链接而失败。统一改为文件系统身份判断后，原命令重试退出 0，核心与 xmind 均为 `unchanged`，两个链接的实际目标正确。SOUL、配置、环境与 cron/jobs 四份文件摘要执行前后不变；没有重启网关或恢复日常任务。

这证明当前 Hermes 两个受管入口的实际幂等接续。Codex/Claude 新筛选路径与 Git 更新使用隔离或受控子进程检查，本轮没有重装真实插件或拉取真实工作区，不将其记为全平台真实更新验收。共享仓库更新会改变现有技能链接所见源码，模块筛选只限制后续安装动作。
