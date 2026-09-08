---
name: i18n-audit
description: 一键运行三层中文化审计（i18n-mcp + 代码扫描 + Playwright 视觉检查），发现所有英文残留
user-invocable: true
arguments:
  - name: path
    description: 项目路径（默认当前目录）
    required: false
---

# 中文化完整性审计

启动 i18n-auditor agent 对项目进行三层全面审计。

项目路径: $ARGUMENTS（如果未指定则使用当前工作目录）

请立即启动 Agent tool，使用以下参数：
- name: "i18n-auditor"
- prompt 中包含项目路径和以下指令：

"对项目 [项目路径] 执行完整的三层中文化审计。
Layer 1: 使用 i18n MCP 工具扫描翻译文件健康度和缺失 key。
Layer 2: 用 Grep 扫描 .vue/.ts/.java 文件中所有用户可见的英文文本。
Layer 3: 如果服务已启动，用 Playwright 截图检查页面英文残留。
按照系统提示中的审计流程逐步执行，最后输出完整的中文化审计报告。"

等 agent 完成后，将审计报告展示给用户，并询问是否要自动修复发现的问题。
