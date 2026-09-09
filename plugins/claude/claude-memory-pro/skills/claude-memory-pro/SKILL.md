---
name: claude-memory-pro
description: 使用 Claude Memory Pro 召回、保存、修正和维护跨会话语义记忆。
---

# Claude Memory Pro

在回答涉及用户偏好、历史决策或项目上下文的问题前，先用 `memory_recall` 检索。记忆是上下文，不是当前事实证明；涉及代码或运行状态时仍要现场核验。

只保存长期可复用的偏好、事实、决策和实体信息。用户要求“记住”或给出稳定规则时用 `memory_store`；需要自动判断偏好、决策或纠错时用 `memory_capture`。不要保存凭据、临时日志、问候语、模板噪声或大段原文。

使用准确分类：`preference`、`fact`、`decision`、`entity`。跨项目偏好用 `global`，项目知识用独立 scope。存储前依赖 MCP 的去重和噪声过滤；相似度超过 98% 的重复记忆应跳过。

`memory_recall` 通过知识图谱路由并结合向量与 BM25 排序，同时追踪召回频率。记忆较多时可用 `memory_atlas` 构建关联；使用 `memory_habits` 查看晋升候选。Dream 的 light、deep、REM 阶段用于晋升高频记忆；用 `memory_dream status` 查看状态，只有用户明确要求维护时才运行 `run` 或 `reorg`。日常整理用 `memory_dream reorg` 重建图谱、检测冲突并标记过期内容。

清理、遗忘或重组是会改变记忆库的操作，必须与用户意图一致并先检查目标范围。
