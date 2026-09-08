# 迁移与安装边界

本仓库把 Rico 自建的工作协议、跨平台插件和独立技能放在一个公开源码树中。运行时数据仍留在每台机器的用户目录，不属于 Git 资产。

统一安装与维护入口是 [asunoiwin/worklikerico](https://github.com/asunoiwin/worklikerico)。各包保留的旧 README、仓库链接和版本号用于来源追溯；安装请使用本页脚本，修复与新功能只在统一仓库维护。11 个已迁入的旧仓库已归档，历史提交和本地未提交改动仍保留。4 个含未推送提交的旧仓已另外生成私有 Git bundle，并通过实际克隆与提交对象检查验证可恢复。

## 安装

先检查待发布内容：

```bash
python3 scripts/verify_publication.py
```

安装通用技能。安装器使用指向当前克隆的符号链接；重复执行不会重复创建，卸载只删除仍指向本仓库的链接：

```bash
python3 scripts/install_skills.py
python3 scripts/install_skills.py --remove
```

安装 Codex 插件。脚本通过仓库市场清单安装三个插件，并在 Codex 的插件缓存中构建 Memory MCP；它不在源码树中生成 `node_modules` 或 `dist`：

```bash
python3 scripts/install_codex_plugins.py
python3 scripts/install_codex_plugins.py --remove
```

安装 Claude 插件。脚本把源码复制到用户级受管目录，构建 Memory MCP，再把三个插件链接到 Claude 的本地插件目录：

```bash
python3 scripts/install_claude_plugins.py
python3 scripts/install_claude_plugins.py --remove
```

用隔离 HOME 验证时，把 `--home /path/to/temp-home` 传给任一脚本。Memory MCP 的密钥必须由运行环境提供；仓库只保存变量名和默认的非敏感服务参数。

## 目录约定

- `skill/work-like-rico/` 是唯一工作协议源，保留既有路径。
- `plugins/{claude,codex}/` 按平台保存原 manifest 名称。
- `skills/` 保存独立能力；Claude 历史工作流候选只安装到 Claude。
- `catalog/` 保存机器可读资产与第三方依赖。
- `docs/migration/` 保存来源、差异决策与已知问题。

安装器用于安装或卸载受管入口。私人数据库和旧源码工作树不随源码归并删除；插件缓存更新会重新安装相应包，运行数据应放在用户数据目录。

## 本机切换结果（2026-09-08）

- 19 项技能对应 41 个实际入口，全部链接到统一源码；20 个旧实体移入私有回滚区，重复安装没有新增变化。
- Codex 三个 `@worklikerico` 插件已启用，旧身份已禁用；旧市场和缓存保留用于当前会话兼容与回滚。
- Claude 三个受管插件已构建，Memory 入口和 4 条 DTL hook 已切换；两个旧手工插件目录移入回滚区。
- 两套 Memory MCP 均通过 initialize 和 tools/list，分别发现 21 个工具；未执行记忆读写，私有 env 逐值保持，数据库路径语义不变。
- 本机没有 Claude CLI，尚未验证 Claude 新会话的插件发现。Codex 新任务按新身份加载插件；当前会话所需的两个旧 hook 已同步修复。
- GitHub 的 11 个旧能力仓已实际核对为 archived，`worklikerico` 保持活跃。业务项目和第三方仓库不在这次归并范围内。
