# Hermes 隔离安装与健康检查

当前固定上游为 NousResearch `hermes-agent` tag `v2026.9.7`、commit `2237be355906fbe6065ce1815711eee52b2d646e`、包版本 `0.21.1`。tag 是 annotated tag，但没有 Git 签名；commit 与 GitHub API 返回的 tag target 一致。

## 目录

```text
${HOME}/.local/share/worklikerico/hermes-agent   # 只放固定上游 checkout
${HOME}/.local/share/worklikerico/hermes-venv    # 独立 Python 3.11 runtime
${HOME}/.config/worklikerico/hermes              # 隔离 HERMES_HOME
${HOME}/.local/bin/hermes                        # 默认使用隔离 Home 的短命令入口
```

不要运行上游的一键安装脚本；下面的命令复用了该脚本的 locked sync，并额外启用固定 lock 中的 `messaging` extra，因为 Telegram 是明确目标。没有执行交互 setup、浏览器安装、gateway 安装、auth 导入或 Codex 配置迁移。

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
chmod 700 "${HOME}/.config/worklikerico/hermes"
chmod 600 "${HOME}/.config/worklikerico/hermes/config.yaml" "${HOME}/.config/worklikerico/hermes/.env"
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

## Work Like Rico skill

只把本仓库维护的一个 skill 作为本地 skill 链入隔离 Home，没有导入其他 Codex skills、AGENTS、MCP、memory 或 auth：

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

原生离线状态能力也已实测：Kanban 创建了一个 blocked canary，重复使用同一 idempotency key 返回同一个 task ID，完成不存在的 task 返回非零；cron 拒绝无 script 的 `--no-agent` job 和越出 `${HERMES_HOME}/scripts` 的路径。唯一 no-agent watchdog 在前台 gateway 中按时完成一次，execution ID 为 `f3ddfd75a67742d9ab8daea864026f4b`，空 stdout 没有投递；随后 job 已暂停、gateway 已停止。该次测量发生在模型授权之前，只证明 scheduler/script/ledger；后续模型接入结果见 [VERIFICATION.md](VERIFICATION.md)。

失败 probe 的 script 以 7 退出，execution `2a7d3ece00694bb8a008a3a9497326a5` 正确记为 `failed` 并保存 stdout；但 `hermes cron run` 这个外层 CLI 命令仍返回 0。外部验收脚本不能只看 CLI exit code，必须再查 `hermes cron runs <job-id>` 或 execution ledger 的终态。临时失败 job 和脚本已删除，ledger 证据保留。

健康边界：CLI 版本与 doctor 只证明本地 runtime 和依赖可用。未完成 Hermes provider OAuth 时，不能据此声称模型可调用；未启动 gateway 时，也不能据此声称 Telegram/企业微信可收发。

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
