# WorkLikeRico

一个仓库维护 Rico 自建的技能、记忆与协作插件；一个本地 Hermes 助手接收信息、执行任务、跟进结果。简单工作直接完成，重要工作用真实结果验收。

Hermes 原生负责模型、消息入口、定时任务和看板。本仓库提供现有能力包与工作规则，不另建调度器、任务数据库、代理服务或控制台。

## 当前交付

- 已归并 6 个平台插件包和 19 项技能目录，包含腾讯云、OCI、PVE、记忆、多 agent 和验收工作流。本机入口已切换，11 个旧能力仓已归档并保留历史。
- 工作协议已加强源文件保留、当前事实核对、授权内推进、取消停止与安静跟进；三类合成任务通过独立真实模型验收。
- 本地 Hermes 0.21.1 已安装，macOS 原生后台服务运行中；无模型定时任务、暂停恢复和持久化已实测。当前没有活跃定时任务，消息渠道等待接入。
- GPT 订阅已登录并通过真实回复与本地文件任务验证；MiMo 有原生订阅入口，待填入凭证。真实消息渠道尚未接通，自动处理日常工作的整条链路仍待验收。

落地顺序见[任务书](docs/plan/implementation-plan.md)，逐项边界见[实施状态](docs/plan/status.md)。

## 安装与使用

```bash
git clone https://github.com/asunoiwin/worklikerico.git ~/.local/share/worklikerico
cd ~/.local/share/worklikerico
```

按使用的平台选择安装，不需要全部安装：

```bash
# 通用技能，链接到当前仓库
python3 scripts/install_skills.py

# Codex 的三个插件
python3 scripts/install_codex_plugins.py

# Claude 的三个插件
python3 scripts/install_claude_plugins.py
```

安装器保留同名冲突，重复执行不会创建副本。加 `--remove` 只移除本仓库受管入口；加 `--home /path/to/temp-home` 可隔离试装。Memory MCP 在安装位置构建，私人数据库和凭据留在用户目录。Claude 安装器已验证本地文件与构建流程，尚未通过真实 Claude CLI 的市场发现验证。详见[迁移说明](docs/migration/README.md)。

更新源码使用 `git pull`；插件复制到缓存后，需要重新执行对应安装器更新。核心协议可显式调用：

```text
$work-like-rico 接手这个任务，先核对当前事实，再在授权范围内完成并检查结果。
```

## 本地助手

按[Hermes 安装说明](docs/hermes/INSTALL.md)配置入口，然后选择一种已有订阅：

| 订阅 | 原生接入 |
|---|---|
| GPT / ChatGPT | `hermes auth add openai-codex`，完成官方设备授权 |
| MiMo Token Plan | `hermes setup` 选择 Xiaomi MiMo，填写订阅密钥和对应地区 Base URL |

详细操作见[订阅接入](docs/hermes/SUBSCRIPTIONS.md)。不要把 Codex 已登录理解成 Hermes 已登录。

Telegram 与企业微信按[渠道说明](docs/hermes/CHANNELS.md)设置。Telegram Bot 只收到机器人可见信息，企业微信机器人或应用也不自动拥有个人聊天历史。个人历史导入和企业会话存档需要对应的账号能力与权限。

第一件工作按下面的链路验收：

```mermaid
flowchart LR
    A[获准的信息或本地资料] --> B[Hermes 明确任务]
    B --> C[调用现有技能执行]
    C --> D[检查实际结果]
    D --> E[交付或记录具体阻塞]
```

先跑通实际任务，再启用相应的定时跟进。[定时任务](docs/hermes/CRON.md)和[实测记录](docs/hermes/VERIFICATION.md)分别说明运行方式与已验证范围。

## 按 Rico 的要求做事

1. **核对事实。** 旧总结、看板状态和别人的完成声明是线索；最终检查当前文件、服务或业务结果。
2. **授权内自主推进。** 普通内部取舍直接处理，遇到问题先诊断、有限重试或恢复；只有真正缺权限、凭据或关键决定时才交回用户。
3. **修根因。** 判断问题属于设计、状态流转、数据结构还是边界条件，检查同类位置和配对操作。
4. **简单优先。** 不预埋假想需求，不顺手重构，不为了流程增加会议或 agent。普通任务由一个执行者完成和检查。
5. **真实验收。** 源文件和手工修改要保留；检查实际产物。高影响且证据不足时增加独立复核，不把脚本退出码、看板 done 或自报 PASS 当作最终结果。
6. **有事再提醒。** 只在实质变化、完成、失败或需要决定时反馈；无变化保持安静，取消后停止推进。

完整协议位于 [SKILL.md](skill/work-like-rico/SKILL.md)，具体督促约定位于[任务跟进规则](skill/work-like-rico/references/task-supervision-contract.md)。它们是行为指导，不能代替运行环境权限控制。

## 目录

| 目录 | 内容 |
|---|---|
| `skill/work-like-rico/` | 核心工作协议，保留原路径兼容既有安装 |
| `skills/` | 独立技能与历史工作流 |
| `plugins/claude/`、`plugins/codex/` | 保留各平台 manifest 名称的插件 |
| `catalog/` | 自建资产清单与第三方依赖 |
| `integrations/hermes/` | 固定版本、配置模板与检查脚本 |
| `scripts/` | 安装、卸载和发布集合检查 |
| `docs/` | 任务书、操作说明、迁移来源与验证记录 |

## 维护与数据

GitHub 只维护源码、脱敏规则与样例。聊天原文、偏好证据、私人任务、运行数据库、授权文件和密钥留在本机；消息内容本身不会扩大执行授权。

发布前运行：

```bash
python3 scripts/verify_publication.py
python3 scripts/verify_plugins.py --skip-codex-cli
git diff --check
```

若需实际验证 Codex 市场发现，运行 `python3 scripts/verify_plugins.py --home /path/to/temp-home`。

已发现的 hook 修复及 Memory 间接依赖问题见[已知问题](docs/migration/known-issues.md)。来源与保留决策见[迁移说明](docs/migration/README.md)。根许可证为 [MIT](LICENSE)，各包的许可证边界见[许可证说明](docs/migration/licenses.md)。
