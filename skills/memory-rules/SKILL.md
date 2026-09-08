---
name: memory-rules
description: 记忆系统使用规范 — 什么时候 store 什么、什么时候 capture 经验、什么时候开 task、scope 怎么定。从 CLAUDE.md 迁移过来按需触发，避免污染常规对话 context。Triggers on - memory_store / memory_capture / lesson_capture / task_create / 记忆规则 / 怎么记 / scope / 项目记忆.
---

# memory-rules — 记忆系统使用规范

## 三维度

claude-memory-pro 把持久化分成三类，**不要混用**：

| 维度 | 是什么 | 工具 |
|---|---|---|
| **记忆** | 事实 / 偏好 / 决策 | `memory_store` / `memory_capture` |
| **任务** | 跨会话进行中的工作 | `task_create` / `task_list` |
| **经验** | 避坑教训（试错 + 反模式） | `lesson_capture` / `lesson_recall` |

## 什么时候 store 什么

| 类型 | 工具调用 | 触发时机 | scope |
|---|---|---|---|
| **偏好** preference | `memory_store(category="preference")` | 学到用户习惯 | global |
| **事实/架构** fact | `memory_store(category="fact")` | 学到项目技术事实 | 项目名 |
| **决策** decision | `memory_store(category="decision", importance≥0.9)` | PRD 通过 / 方案选定 | 项目名 |
| **任务** task | `task_create(subject≥4字, project必填)` | 跨会话工作开启 | task:项目名 |
| **经验** lesson | `lesson_capture(pitfall≥10字, solution≥5字, triggerKeywords≥1)` | 试错 >10 分钟 / 反模式 / 误导报错 / 同坑二刷 | lesson:项目名 |

**不确定值不值记** → 用 `memory_capture`，让插件自动判断要不要落库。

## scope 怎么定

- **global**：跨项目通用（用户身份 / 工作习惯 / 工具偏好）
- **项目名**（如 `larktokenweb`）：项目特定的事实和决策
- **task:项目名**：项目任务列表
- **lesson:项目名**：项目教训库

scope 写错的后果：跨项目召回不到，相当于丢失。

## 经验捕获的硬要求

`lesson_capture` 三件套缺一不可：

1. **pitfall**（坑是什么）≥10 字 — 别写"代码报错"，写"用 npx 调 mcp 时 path 含空格导致 spawn failed"
2. **solution**（怎么解的）≥5 字 — 写具体修法，不写"修好了"
3. **triggerKeywords**（什么词出现时该召回这条）≥1 个 — 这是召回入口，**绝不能留空**

triggerKeywords 留空 = 这条经验等于丢失，下次同坑还会踩。

## 对话开始时的强制召回

每个新对话开头按 cwd 判项目，跑这 4 个召回：

1. `memory_recall("Rico 用户偏好")` — 拿全局偏好
2. `memory_recall("项目名 项目架构")` — 拿项目事实
3. `task_list(project=项目名, status="open")` — 拿在做的任务
4. `lesson_recall(keywords=用户首条消息关键词, project=项目名)` — 拿相关经验

用户消息含具体技术名词（如 `flyway` / `nginx` / `鉴权`）时额外 `lesson_recall` 该词。

## 不允许做的事

- ❌ 写 `MEMORY.md` 或任何文件式记忆系统（已迁到插件）
- ❌ 跳过 SessionStart 召回
- ❌ 把"任务"当普通 memory 存（用 task_create）
- ❌ 把"经验"当普通 memory 存（用 lesson_capture）
- ❌ `lesson_capture` triggerKeywords 留空
