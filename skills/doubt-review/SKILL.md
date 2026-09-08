---
name: doubt-review
description: commit 前强制自审 — 用对抗式 prompt 给自己挑刺。CLAIM/EXTRACT/DOUBT/RECONCILE 四步快速版。是 design-test-loop 插件的"提交门"——git commit 前必触发，否则 hook 拦截。Triggers on - doubt-review / 自审 / 提交前 / 上车前 / commit 前 / 对抗式 / claim doubt.
---

# doubt-review — commit 前给自己挑刺

## 这个 skill 在干嘛

你刚写完代码，**心理上已经认定它对了**——这是写代码最危险的时刻。
doubt-review 强制你**换个视角**重看一遍：假装一个不信任你的 reviewer 来审，专门找漏洞。

插件会在你跑 `git commit` 前检查输出里有没有自审段落，没有就拦截。

## 4 步快速模板

```markdown
## doubt-review：提交前自审

**CLAIM（我做了啥）**：用 1 句话讲这次改动做了什么，不带辩护语气。
比如"修复了 RelayController 在 retry-exhausted 时 drift 越权的 bug"。

**EXTRACT（关键改动点）**：列 2-4 个核心改动行为，每条具体到"在哪个文件、改了什么逻辑"。
比如：
- RelayController.tryRetryExhaustedGroupDrift 第三参数改传 user.allowedGroups
- GroupDriftService.findCheaperGroup 增加 null 守卫返回 empty

**DOUBT（怀疑点）**：自己挑 3 个最可能翻车的怀疑点。
强制用"如果...会怎样"句式。比如：
- 如果 user.allowedGroups 是空集合呢？是不是会让所有请求都失败？
- 如果原 allowedGroups 已经是全集，剔除后只剩 null 呢？
- 如果并发请求修改了 user 的 allowedGroups，是不是会用到陈旧值？

**RECONCILE（怎么解）**：对每个 DOUBT 给一句话回应——"已处理 / 需测覆盖 / 接受残留风险"。
比如：
- 空集合 → 已加 isEmpty 短路返回原 allowedGroups
- 全集剔除 → 用 unit test 覆盖（已加测试用例 testEmptyCandidateSet）
- 并发陈旧值 → 接受残留（user.allowedGroups 修改频率极低，权衡复杂度后不加锁）
```

## 触发时机

- **git commit 之前** → 插件强制（PreToolUse Bash hook 拦截）
- 任何"准备发布 / 准备提交 / 准备上线"的关头主动触发
- strict-prod-audit 一测开始前作为预检

## 怎么挑出有效的 DOUBT

DOUBT 不是为了凑数。挑刺方向参考：

1. **边界值**：空 / null / 0 / 最大 / 负数 / 超长
2. **并发**：两个请求同时进，状态会不会错？
3. **回滚**：这改动出错了，能不能 1 分钟内回滚？
4. **配套修改有没有漏**：grep 同 pattern 检查过了吗？
5. **上下游影响**：调这个函数的地方 / 被这个函数调用的地方，有没有依赖被打破？
6. **配置 / 环境差异**：dev VM 跑通了，prod 配置不同会怎样？

每次自审至少覆盖 2 个不同方向，**不要 3 条都是边界值**。

## 反模式

- ❌ DOUBT 写"代码应该没问题"——这不是怀疑，是辩护
- ❌ RECONCILE 全是"已处理"——一个"接受残留风险"都没有，说明 DOUBT 挑得太软
- ❌ 把 strict-prod-audit 的测试报告当 doubt-review 交差（这是 commit 前自审，不是测试结果）
- ❌ 简单格式化改动也走完整流程（hook 对 `git commit -m` 不带代码改动的允许跳过——但建议至少 1 行 CLAIM）

## hotfix 快速版

紧急 hotfix 可压缩到 3 步：

- **改了啥**：1 句话
- **最大的怀疑点**：1 条最可能翻车的
- **回滚方案**：怎么 1 分钟回滚

但**不允许完全跳过**——hotfix 翻车最多，反而更需要自审。

## 关键字提示（插件用来识别）

输出时必须含这两个标记词其中之一，hook 才能识别为通过：

- `doubt-review：提交前自审`（推荐）
- 或同时出现 `CLAIM` + `DOUBT` + `RECONCILE` 三个词

否则即便写了自审，hook 也认不出来。
