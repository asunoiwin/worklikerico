# 迁移与安装边界

本仓库把 Rico 自建的工作协议、跨平台插件和独立技能放在一个公开源码树中。运行时数据仍留在每台机器的用户目录，不属于 Git 资产。

统一安装与维护入口是 [asunoiwin/worklikerico](https://github.com/asunoiwin/worklikerico)。各包保留的旧 README、仓库链接和版本号用于来源追溯；安装请使用本页脚本，修复与新功能只在统一仓库维护。旧仓库在确认迁入后归档，历史提交和本地未提交改动仍保留。4 个含未推送提交的旧仓已另外生成私有 Git bundle，并通过实际克隆与提交对象检查验证可恢复。

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

旧仓库、现有个人配置、数据库和 hook state 都不会由这些迁移脚本删除或修改。
