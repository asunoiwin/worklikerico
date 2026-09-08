---
name: delegate
description: 把对 opus 主对话依赖度低的任务系统化下放给 sonnet/haiku agent 执行。一个统一入口管理 7 类常见 token 浪费场景：长文件读取、报告整合、编译验证、发版流程、grep+sed 局部读取、批量测试跑批、bug 修复 recheck。Triggers - 长文件 / 读源码 / outline / 整合报告 / 多份报告 / 看报告 / 编译 / mvn compile / 发版 / 提交 + tag / commit-tag / grep 定位 / 批量测试 / bug 修复验证 / recheck / 节约 token / 派 agent 帮我做.
---

# Multi-Agent Toolkit — Delegate Pattern

**核心理念**：普通编码派 Sonnet，复杂决策和正式审查派 Opus，纯机械任务才派 Haiku；主对话只保留协调和验收。

## 决策矩阵

| 场景 | 旧做法（贵）| 新做法（省）| 模型 | 节约 |
|---|---|---|---|---|
| 看长文件 (>500 行) | Read 全文 | 派 agent 出 outline | sonnet | 75% |
| 整合多份 agent 报告 | Read 每份 | 派 agent 总结成 1 份 | sonnet | 70% |
| 编译验证 + 修编译错误 | 主对话 mvn + 看 stderr + 修 | 派 agent 跑通即可 | sonnet | 50% |
| bump + commit + tag + push | 主对话 6-8 步 | 派 agent 一气完成 | haiku | 80% |
| grep + sed 局部代码读取 | 主对话多轮 | 派 agent 一次定位 | haiku | 60% |
| 批量跑测试脚本 + 摘要 | 主对话逐个跑 | 派 agent 跑完出表 | sonnet | 65% |
| bug 修复后 recheck | 主对话写脚本 | 派 agent 用现有脚本 | sonnet | 70% |

---

## 七大模式

### 模式 1：Long File Outline

**触发**：需要看文件 > 500 行

**做法**：派 sonnet agent 输出标准 outline，主对话只持有 outline。

```
Agent({
  subagent_type: "general-purpose",
  model: "sonnet",
  description: "outline 长文件",
  prompt: `读 {ABSOLUTE_PATH}（{N}行），输出 <500 token outline，不 paste 代码：

  ## Symbol Map（按行号）
  - L{n}  package/class/@注解/方法签名

  ## 关键字段
  - 注入依赖
  - @Value 配置

  ## 已有特性区
  - L{x}-{y}: 一句话功能

  约束：四节齐全，<500 token，行号标记，不输出代码`
})
```

**Cache**：outline 写到 `<filepath>.outline.md` + memory_store 键 `outline:<path>:<commit>`。

---

### 模式 2：Report Aggregator

**触发**：3+ 份 agent 报告需要整合结论

**做法**：派 sonnet agent 读所有 .md 报告 + 输出表格汇总。

```
Agent({
  model: "sonnet",
  description: "整合 N 份测试报告",
  prompt: `读以下报告：
  - /path/to/report1.md
  - /path/to/report2.md
  - ...

  输出表格汇总（不 quote 原文）：
  | 报告 | 通过/失败 | 真问题（panmode 修） | 上游问题 | 建议 |

  最后给整体结论 3 行。约束：<800 token，不复述具体测试数据。`
})
```

---

### 模式 3：Compile Validator

**触发**：改代码后需要 mvn 编译验证

**做法**：派 sonnet agent 跑 compile + 看错误 + 必要时修 import / 类型 / 重命名。

```
Agent({
  model: "sonnet",
  description: "编译 + 修编译错误",
  prompt: `cd {project} 跑：
    mvn -q -DskipTests -pl platform-gateway -am compile

  如果失败：看 stderr 找具体错误（缺 import / 类型不匹配 / 找不到符号），自己 grep + Edit 修，最多 3 轮。
  如果 3 轮还失败：报告原始错误给主对话。
  成功：报告"编译通过"。

  不要修业务逻辑，只修编译错误。`
})
```

---

### 模式 4：Release Workflow

**触发**：要发版（bump + commit + tag + push）

**做法**：派 haiku agent 执行标准流程。

```
Agent({
  model: "haiku",
  description: "bump 版本 + commit + tag + push",
  prompt: `执行发版流程：
  1. 当前版本：{CURRENT}（如 1.4.52）
  2. 目标版本：{NEXT}（如 1.4.53）
  3. 提交信息：{COMMIT_MSG}

  步骤：
    cd {project}
    find . -name "pom.xml" -not -path "*/target/*" | xargs grep -l "{CURRENT}" | xargs sed -i '' "s/{CURRENT}/{NEXT}/g"
    git add -A
    git commit -m "{COMMIT_MSG}"
    git tag v{NEXT}
    git push origin master --tags

  报告：commit hash + tag 名 + 是否 push 成功。`
})
```

---

### 模式 5：Grep+Sed Locator

**触发**：知道关键字但不知行号

**做法**：派 haiku agent 一次拿到上下文。

```
Agent({
  model: "haiku",
  description: "定位 + 取上下文",
  prompt: `在 {project} 找 "{KEYWORD}" 的所有出现，每个返回：
  - 文件路径
  - 行号
  - 上下 5 行的代码片段

  用 grep -rn + sed -n 'X-5,X+5p'。<300 token。`
})
```

---

### 模式 6：Test Batch Runner

**触发**：N 个测试脚本需要全部跑 + 摘要

**做法**：派 sonnet agent 顺序跑 + 汇总。

```
Agent({
  model: "sonnet",
  description: "跑 N 个测试脚本",
  prompt: `cd {test_dir} 顺序跑：
  - script1.py
  - script2.py
  - ...

  每个脚本：
  - 启动时 print
  - 完成或失败都记录
  - 最多 60s 超时，超时 SIGINT 看 partial output

  最后输出汇总表：
  | 脚本 | 通过 | 失败 | 关键发现 |

  约束：不修脚本（除非编译/语法错误），不主动修复 bug，只跑 + 报告。`
})
```

---

### 模式 7：Recheck Bug Fix

**触发**：发版后验证某 bug 真修了

**做法**：派 sonnet agent 跑 recheck 脚本（如有）或写最小 curl 验证。

```
Agent({
  model: "sonnet",
  description: "recheck bug X",
  prompt: `验证 bug 是否已修：
  - bug 描述：{DESC}
  - 测试方式：{HOW}（最小 curl / pytest / 现有脚本）
  - 期望：{EXPECTED}
  - 实际：自己跑 + 对比

  报告：PASS / FAIL + 1 行原因。如 FAIL 给最小复现命令。`
})
```

---

### 模式 8：True Parallel Batch（真并行）

**触发**：2-4 个完全独立的子任务，互不依赖文件或结果

**做法**：在**同一响应**中发出多个 Agent tool call（运行时真并发）。

```
# 同一消息里并行发出，不要顺序发
Agent({ model: "sonnet", description: "任务A", prompt: "..." })
Agent({ model: "sonnet", description: "任务B", prompt: "..." })
Agent({ model: "haiku",  description: "任务C", prompt: "..." })
```

**关键约束**：
- 每个 agent 有**完整独立上下文**，不依赖其他 agent 的中间结果
- 并发 agent 不能写同一文件（会产生冲突）
- 主对话只持有**结果摘要**，不 Read 子 agent 的中间输出
- 推荐并发数：2-4 个；超过 4 个拆成两波

**节约**：相比顺序执行，主 context 减少 60-80%（子 agent 输出不回流）

---

## 何时不要派 agent

- ❌ 单次 < 500 token 的简单 grep / sed → 直接 Bash
- ❌ 单次 1-2 行的 Edit → 直接做
- ❌ 决策类（架构、bug 根因分析）→ Opus 主对话
- ❌ 用户对话理解 → Opus 主对话
- ❌ 多 agent 并发协调（这本身需要 Opus）

## 调用建议

- 一次只派 1-2 个 agent，避免主对话需要并发整合（反而费）
- 用 ScheduleWakeup 串行（每次主对话只接收 1 份报告）
- agent 完成通知里的 result summary 已够用，**永远不要 Read agent transcript**

## 累计节约

按今天经验，全面应用此 plugin **可节约 50-70% Opus token**。
