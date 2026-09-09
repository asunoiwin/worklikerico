# Hermes 订阅接入

已核对固定安装：Hermes `v2026.9.7` / `0.21.1` 原生支持两条最短路径，无需新增 provider。本机网络若依赖 HTTP 代理，需要让 Hermes 进程显式使用该代理。

## GPT（ChatGPT/Codex 订阅）

原生 provider 是 `openai-codex`，走 Hermes 自己的 device OAuth。OpenAI 官方也确认“使用 ChatGPT 登录”属于订阅访问。当前 Hermes 已是 **logged in**；没有复制或导入 `~/.codex/auth.json`，也没有使用 API Key。需要重新认证时运行：

```bash
hermes auth add openai-codex
```

本机当前默认 provider/model 为 `openai-codex` / `gpt-5.6-sol`，保留 `openai_runtime: auto`，没有配置 fallback。2026-09-09 实际 Telegram 请求发现旧默认 `gpt-5.4-mini` 被订阅接口以 HTTP 400 拒绝；读取当前账号的模型目录后改用 `gpt-5.6-sol`，真实短调用约 5.8 秒通过，随后 Telegram 只读 Git 任务也收到准确回复。模型可用性以当前账号目录和实际调用为准。

2026-09-09 工作场景复验发现：固定版本对估算输入较小的 Codex 请求使用 12 秒事件空闲阈值；本地保护主动关闭流后出现 `Broken pipe`。同一订阅、模型和材料，仅把该项进程阈值调整为 60 秒，实际一次请求约 36.9 秒完整返回，没有重试或流空闲终止。真实返回的 token 统计与触发分支使用的输入估算口径不同，不能混用。该结果支持调整此项超时，不代表持续运行已经全部验收。

如遇上述已确认的固定版本问题，在 Hermes 私有 `.env` 中设置以下一项，并通过原生服务管理方式重新加载；保留原 provider、模型与审批策略：

```dotenv
HERMES_CODEX_EVENT_STALE_TIMEOUT_SECONDS=60
```

2026-09-08 的早期快照曾记录 `gpt-5.4-mini` 纯文本约 4.02 秒及隔离文件任务约 15.63 秒通过，不能用该历史结果证明次日网关仍支持该型号。

若本机依赖 HTTP 代理，只在 Hermes 私有 `.env` 中配置，仓库文档使用占位写法：

```dotenv
HTTP_PROXY=http://localhost:PORT
HTTPS_PROXY=http://localhost:PORT
NO_PROXY=localhost,127.0.0.1
```

原生 gateway 已自动领取并完成一次真实本地资料整理，内容经纠正复验，源输入哈希未变。现已验证订阅推理、本地文件工具、单次后台执行，以及 Telegram、企业微信本人私聊请求到工具执行和回复；持续日常运行尚未验收。

## MiMo（Token Plan 订阅）

小米官方产品名是 **Token Plan**。它原生支持 Hermes；不是普通按量 API。订阅凭证为 `tp-` 开头的专属 Key，Base URL 以订阅页显示为准（中国区示例 `https://token-plan-cn.xiaomimimo.com/v1`），推荐模型 `mimo-v2.5-pro`。Hermes 内置 provider 为 `xiaomi`，配置键为 `XIAOMI_API_KEY`、`XIAOMI_BASE_URL`。用户先在 Token Plan 页面取得专属 Key/Base URL，再运行：

```bash
hermes setup
# Quick Setup → Xiaomi MiMo → 填订阅专属 Key/Base URL → mimo-v2.5-pro
```

本机现有 MiMoCode 订阅已接入 Hermes：先由 `mimo debug paths` 确认实际认证存储，再核对 Token Plan 凭证和官方地区入口，仅将所需字段写入 Hermes 私有 `.env`，保留既有变量与私有备份。只检查配置文件中的 schema/plugin 键不足以判断订阅状态。

原生 `xiaomi` / `mimo-v2.5-pro` 单次无工具短文本请求成功，约 3.82 秒；后台服务已重启加载配置。默认仍为 GPT 订阅，当前型号为 `gpt-5.6-sol`，没有配置 fallback。

2026-09-09 补充真实文件工具验收：模型读取合成输入，计算总额并写入 JSON，再回读核对；主线程检查金额、随机标识、仅有指定字段和源文件 SHA-256，全部通过。持久会话记录为 4 次 API 调用、`read_file → write_file → read_file` 三次真实工具调用，实际请求入口仍为 Token Plan。未访问外部平台或创建定时任务。首次仅开放 terminal 的试验因内联脚本审批拦截而未产出文件；改用原生 file 工具集通过，没有更改审批策略。该结果覆盖一次 CLI 文件任务，MiMo 后台任务和持续运行仍未验收。

官方依据：[OpenAI 认证](https://developers.openai.com/codex/auth) · [MiMo × Hermes](https://mimo.mi.com/docs/zh-CN/tokenplan/integration/hermes-agent) · [Token Plan 凭证](https://mimo.mi.com/docs/en-US/tokenplan/Token%20Plan/subscription) · [Hermes 固定版本 provider](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/hermes_cli/auth.py#L180-L241)
