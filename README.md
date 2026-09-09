# WorkLikeRico

一个仓库维护 Rico 自建的技能、记忆与协作插件；一个本地 Hermes 助手接收信息、执行任务、跟进结果。简单工作直接完成，重要工作用真实结果验收。

Hermes 原生负责模型、消息入口、定时任务和看板。本仓库提供现有能力包与工作规则，不另建调度器、任务数据库、代理服务或控制台。

工作规则共用源码，平台接入分别实现：

| 使用入口 | 加载内容 | 负责的工作 |
|---|---|---|
| Hermes | 原生会话、工具、调度与已接入的工作规则 | 机器人接收任务、执行和跟进 |
| Codex | Codex 版记忆、协作、验收插件及独立技能 | 开发协作、记忆检索与交付检查 |
| Claude Code | Claude 版的对应插件 | 保留已有 Claude 工作环境的兼容入口 |

六个包是三类能力的两套平台适配，不是六个 Hermes 插件。Hermes 当前已链接 `work-like-rico` 核心规则与 `xmind` 专项技能，后者已通过一次原生 CLI 创建及回读验证；其他平台的技能、hook、MCP 配置和记忆库不会因此自动接入或共享。Claude 兼容工作不代表 Hermes 增加了 Claude 模型依赖。

## 当前交付

- 已归并 6 个平台插件包和 19 项技能目录，包含腾讯云、OCI、PVE、记忆、多 agent 和验收工作流。本机入口已切换，11 个旧能力仓已归档并保留历史。
- 2026-09-09 Codex 安装态按能力去重为 20 项 skill：11 项自研独立技能、9 项由三个 Codex 插件提供的改编/移植工作流；自研 MCP 服务为 `codex-memory-pro` 一项。19 项仓库目录包含 Claude 工作流，不能直接当作 Codex 自研数量；旧任务仍可能绑定旧版插件缓存。
- 工作协议已加强源文件保留、当前事实核对、授权内推进、取消停止与安静跟进；三类合成任务通过独立真实模型验收。
- 本地 Hermes 0.21.1 已安装，macOS 原生后台服务运行中；无模型定时任务、暂停恢复和持久化已实测。Telegram 和企业微信本人私聊均已接通；企微使用不依赖公网 IPv4 的原生长连接。
- GPT 订阅当前使用 gpt-5.6-sol，两个渠道的真实请求到本地只读工具和准确回复均已验收；MiMo Token Plan 已通过原生短文本调用。默认工作角色已应用，原生后台资料整理通过内容复验。按用户最新要求，日常监测暂不启用，先完善基础环境、工作习惯分析和插件落实。

落地顺序见[任务书](docs/plan/implementation-plan.md)，逐项边界见[实施状态](docs/plan/status.md)。

## 安装与使用

```bash
git clone https://github.com/asunoiwin/worklikerico.git ~/.local/share/worklikerico
cd ~/.local/share/worklikerico
```

先查看目录，再按使用的平台安装；默认安装该平台在目录中声明兼容的全部能力：

```bash
python3 scripts/manage.py list
python3 scripts/manage.py list --platform hermes

python3 scripts/manage.py install --platform codex
python3 scripts/manage.py install --platform claude
python3 scripts/manage.py install --platform agents
python3 scripts/manage.py install --platform hermes
```

`list` 的数量是本仓库目录在当前平台筛选下的 skill 条目和插件包，不是机器上的全部已安装能力；插件内部包含的 skill 和平台自带能力不重复展开。

只安装明确选择的模块时可重复指定 `--skill` 或 `--plugin`。只要出现任一筛选参数，就不会顺带安装该平台的其他能力：

```bash
python3 scripts/manage.py install --platform hermes --skill work-like-rico --skill xmind
python3 scripts/manage.py install --platform codex --plugin codex-memory-pro
python3 scripts/manage.py install --platform codex --skill xmind --dry-run
```

统一入口保留同名冲突，重复执行不会创建副本。加 `--home /path/to/temp-home` 可隔离试装；`--dry-run` 只显示计划，不拉取、构建或写目录。Memory MCP 在安装位置构建，私人数据库和凭据留在用户目录。原三个安装脚本继续保留，移除受管入口仍使用其 `--remove` 参数。Claude 三个插件已通过 Claude Code 2.1.229 的市场校验、用户级安装和实际清单发现；尚未进行付费模型会话验收。详见[迁移说明](docs/migration/README.md)。

更新要求工作区干净，使用快进拉取；源码同步成功后才重新安装所选平台。拉取或安装失败都会非零退出，且不会继续后续步骤：

```bash
python3 scripts/manage.py update --platform codex
python3 scripts/manage.py update --platform hermes --skill xmind --dry-run
```

技能入口是指向本仓库的链接，已有技能正文会随源码更新；新增技能仍需重新安装。Codex 缓存和 Claude 受管副本需要由更新命令重装。旧会话是否重新发现新版本取决于平台自身的会话加载时机。

`update` 拉取的是整个共享仓库；模块筛选限制的是随后重装的入口，不是源码拉取范围。已有的其他技能链接也会跟随仓库更新。若只需用当前源码重装某个模块，使用带筛选的 `install`。

核心协议可显式调用：

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
