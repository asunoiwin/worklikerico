# Hermes 隔离安装与健康检查

当前固定上游为 NousResearch `hermes-agent` tag `v2026.9.7`、commit `2237be355906fbe6065ce1815711eee52b2d646e`、包版本 `0.21.1`。tag 是 annotated tag，但没有 Git 签名；commit 与 GitHub API 返回的 tag target 一致。

## 目录

```text
${HOME}/.local/share/worklikerico/hermes-agent   # 只放固定上游 checkout
${HOME}/.local/share/worklikerico/hermes-venv    # 独立 Python 3.11 runtime
${HOME}/.config/worklikerico/hermes              # 隔离 HERMES_HOME
${HOME}/.local/bin/hermes                        # 默认使用隔离 Home 的短命令入口
```

不要运行上游的一键安装脚本；下面的命令复用了该脚本的 locked sync，并额外启用固定 lock 中的 `messaging` extra，因为 Telegram 是明确目标。以下基础安装步骤不包含交互 setup、浏览器安装、gateway 安装、auth 导入或 Codex 配置迁移；本机后续实际接入见订阅说明与验收记录。

从统一仓库根目录运行；以下步骤用于新安装，已有配置和入口应先检查再保留：

```bash
worklikerico_root="$PWD"
mkdir -p "${HOME}/.local/share/worklikerico"
git clone --branch v2026.9.7 --depth 1 \
  https://github.com/NousResearch/hermes-agent.git \
  "${HOME}/.local/share/worklikerico/hermes-agent"

test "$(git -C "${HOME}/.local/share/worklikerico/hermes-agent" rev-parse HEAD)" = \
  2237be355906fbe6065ce1815711eee52b2d646e

uv venv "${HOME}/.local/share/worklikerico/hermes-venv" --python 3.11

cd "${HOME}/.local/share/worklikerico/hermes-agent"
empty_uv_config="${HOME}/.local/share/worklikerico/empty-uv-config"
mkdir -p "${empty_uv_config}"
unset UV_NO_CONFIG UV_CONFIG_FILE
XDG_CONFIG_HOME="${empty_uv_config}" \
XDG_CONFIG_DIRS="${empty_uv_config}" \
UV_PROJECT_ENVIRONMENT="${HOME}/.local/share/worklikerico/hermes-venv" \
UV_PYTHON="${HOME}/.local/share/worklikerico/hermes-venv/bin/python" \
  uv sync --extra all --extra messaging --locked
cd "${worklikerico_root}"
mkdir -p "${HOME}/.local/bin" "${HOME}/.config/worklikerico/hermes/skills"
# 仅在没有同名入口时安装，避免覆盖其他 Hermes 安装。
test ! -e "${HOME}/.local/bin/hermes" && \
  install -m 755 integrations/hermes/hermes "${HOME}/.local/bin/hermes"
# -n 保留既有配置；新文件只供本人读取。
cp -n integrations/hermes/config.template.yaml "${HOME}/.config/worklikerico/hermes/config.yaml"
cp -n integrations/hermes/env.template "${HOME}/.config/worklikerico/hermes/.env"
cp -n integrations/hermes/SOUL.md "${HOME}/.config/worklikerico/hermes/SOUL.md"
chmod 700 "${HOME}/.config/worklikerico/hermes"
chmod 600 "${HOME}/.config/worklikerico/hermes/config.yaml" "${HOME}/.config/worklikerico/hermes/.env" "${HOME}/.config/worklikerico/hermes/SOUL.md"
```

确保 `${HOME}/.local/bin` 已在 PATH 中；否则可以先使用 `${HOME}/.local/bin/hermes`。

短命令默认使用隔离 Home：

```bash
hermes --version
hermes doctor
hermes config check
```

本机 2026-09-08 实测：Python 3.11.15，Hermes `v0.21.1 (2026.9.7)`，OpenAI SDK 2.24.0，SQLite 3.53.0；locked sync 解析 255 包，`python-telegram-bot 22.8` 可导入。`doctor` 能真实启动 CLI，Telegram optional dependency 已通过，但会把“venv 不在上游 checkout 的 `venv/`/`.venv/`”报告为 entry-point 警告。这是 `doctor_platform.py` 的路径假设，与独立 venv 设计冲突；实际 `hermes` 已运行成功。

`${HOME}/.local/bin/hermes` 默认设置 `HERMES_HOME=${HOME}/.config/worklikerico/hermes`，再把参数原样交给独立 venv；调用者显式设置 `HERMES_HOME` 时会尊重该值。`${HOME}/.hermes` 在收尾前已经是一个真实目录，且包含 Hermes 生成的本地状态，因此按不覆盖既有入口的约束予以保留。未修改 shell profile。

统一诊断入口会显式指向实际 `HERMES_HOME`、独立 venv、访问策略 preflight、cron 和 Kanban 状态：

```bash
integrations/hermes/diagnose.sh
```

不要只取该脚本最终 exit code；逐项读取 doctor、cron execution 和 Kanban 状态。Hermes 的部分诊断命令会在内部任务失败时仍返回 0。

## macOS 后台服务

2026-09-08 已用 Hermes 原生命令安装当前用户的 LaunchAgent：

```bash
hermes gateway install --no-start-now --start-on-login
hermes gateway status
launchctl print "gui/$(id -u)/ai.hermes.gateway"
```

实际生成 `${HOME}/Library/LaunchAgents/ai.hermes.gateway.plist`，运行目录、日志目录和 `HERMES_HOME` 均指向 `${HOME}/.config/worklikerico/hermes`。macOS 加载带 `RunAtLoad` 的 LaunchAgent 后立即启动了 gateway，因此即使传入 `--no-start-now`，这组参数仍产生了一次实际启动；没有再运行 `hermes gateway start`。

首次服务验收时，launchd 和 gateway 子进程均存活，`hermes gateway status` 报告由 launchd 监督并支持登录自启/崩溃重启。启动日志明确记录 0 个 channel target、Telegram/企业微信均 disabled、cron 为空；当时唯一 Kanban canary 为带 `needs_input` 原因的 blocked 状态。日志没有 agent dispatch、provider/API 请求或消息收发，因此这次只验证后台调度外壳，没有发起新的模型调用。

后续已完成原生后台本地资料任务、归档 canary，并在 MiMo 接入后重启服务；最新边界见[实测记录](VERIFICATION.md)。

停止并卸载后台入口使用原生命令：

```bash
hermes gateway stop
hermes gateway uninstall
```

卸载服务不会删除隔离配置、认证、skills、cron/Kanban 台账或上游 checkout。

## Work Like Rico skill

核心工作规则作为本地 skill 链入隔离 Home。该链接不导入 Codex 的 AGENTS、MCP、memory 或 auth：

```bash
ln -s "${worklikerico_root}/skill/work-like-rico" \
  "${HOME}/.config/worklikerico/hermes/skills/work-like-rico"
hermes skills list --source local
hermes prompt-size --json
```

固定版本没有 `hermes skills view` 子命令。实测 `skills list` 将 `work-like-rico` 显示为 local、enabled；离线 `prompt-size --json` 通过 Hermes 自己的 skill loader 读取到同名 `SKILL.md`、实际路径和 5225 字节内容。链接直接跟随仓库当前版本，无需复制或同步器；源 `SKILL.md` 当时的 SHA-256 为 `6dc052ff680ed9945556f66e1e5e9c33721d5bbd884fc8473f944ea2ec477c63`。

只卸载这个接入时执行：

```bash
unlink "${HOME}/.config/worklikerico/hermes/skills/work-like-rico"
```

该操作保留仓库里的 skill 源文件和 Hermes 默认 SOUL、bundled skills、memory 与其他状态。

## 按需接入专项技能

2026-09-09 首先开放 `xmind` 的 Hermes 安装资格。从统一仓库根目录明确选择安装项：

```bash
python3 scripts/install_skills.py --target hermes --skill xmind
hermes skills list --source local
```

入口链接到仓库中的技能源码；重复安装保持原入口，遇到预存同名目录会报告冲突并保留它。当前不批量迁移其他平台的技能、插件或数据。原生列表显示 enabled 只证明发现成功，实际创建与回读另按[实测记录](VERIFICATION.md)验收。

移除该受控入口时运行：

```bash
python3 scripts/install_skills.py --target hermes --skill xmind --remove
```

移除入口不会删除仓库源码或已经创建的 XMind 文件。这里沿用本项目的隔离 Home 布局；不要把安装器的 `--home` 测试根目录参数当成任意 Hermes 配置目录。

原生离线状态能力也已实测：Kanban 创建了一个 blocked canary，重复使用同一 idempotency key 返回同一个 task ID，完成不存在的 task 返回非零；cron 拒绝无 script 的 `--no-agent` job 和越出 `${HERMES_HOME}/scripts` 的路径。唯一 no-agent watchdog 在前台 gateway 中按时完成一次，execution ID 为 `f3ddfd75a67742d9ab8daea864026f4b`，空 stdout 没有投递；随后 job 已暂停、gateway 已停止。该次测量发生在模型授权之前，只证明 scheduler/script/ledger；后续模型接入结果见 [VERIFICATION.md](VERIFICATION.md)。

失败 probe 的 script 以 7 退出，execution `2a7d3ece00694bb8a008a3a9497326a5` 正确记为 `failed` 并保存 stdout；但 `hermes cron run` 这个外层 CLI 命令仍返回 0。外部验收脚本不能只看 CLI exit code，必须再查 `hermes cron runs <job-id>` 或 execution ledger 的终态。临时失败 job 和脚本已删除，ledger 证据保留。

健康边界：CLI 版本、doctor 和 gateway 进程只证明本地 runtime、依赖与后台外壳可用。模型登录及真实文本/文件调用另行验收；消息渠道仍未启用，也不能据此声称 Telegram/企业微信可收发。

隔离边界以 `hermes auth status <provider>` 的实际结果验收，不以 `auth.json` 是否存在推断登录状态；认证文件可能由独立的授权任务并行维护。本次没有复制凭据、修改 auth 或发起模型调用。`hermes auth list` 会发现本机已有 `gh` CLI 的 Copilot 凭据；它不是本次导入。首次 doctor 初始化了 Hermes 上游自带的 bundled skills（332 个文件）和默认 `SOUL.md`；它们来自固定上游，不是从 Codex/Claude 或个人目录导入。实际 `.env` 和 `config.yaml` 权限为 0600，`~/.codex/config.toml` 没有 Hermes managed block。

## 回滚

本次入口回滚只删除 CLI 入口文件，保留上游 checkout、独立 venv、隔离配置和既有 `${HOME}/.hermes`：

```bash
unlink "${HOME}/.local/bin/hermes"
```

不要删除或 `unlink` `${HOME}/.hermes`，因为它不是本次创建的链接。本阶段没有改 `~/.codex`、`~/.claude`、shell profile 或系统 LaunchAgent。

## 官方依据

- [release v2026.9.7](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.9.7)
- [安装文档](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/website/docs/getting-started/installation.md)
- [固定依赖与 Python 范围](https://github.com/NousResearch/hermes-agent/blob/v2026.9.7/pyproject.toml)

## 默认工作要求

`integrations/hermes/SOUL.md` 提供简短的默认工作要求，普通对话也会加载。新安装使用上面的 `cp -n` 保留既有自定义角色；本机初次应用前已私有备份上游默认角色。工程或长期任务再按需读取 `work-like-rico` 技能，不把每件日常小事变成重型流程。
