---
name: audit-verify
description: 独立审计 agent — 二测 PASS 后强制独立复测。不读二测报告，仅看原始需求 + 一测预期清单，独立设计测试，对比结论。Triggers on - 独立审计 / audit / 复测 / 防止假阳性 / 二测后审计 / regression-audit.
---

# 独立审计 Skill

**核心原则**：二测 agent 自己写报告自己判 PASS = 自证。本 skill 强制由不同 agent 实例做独立复测。

## 触发时机

任何 strict-prod-audit 二测 agent 报告 PASS 后，主 agent **必须**派 audit-agent 一次：
- audit-agent 是独立 agent 实例（不能复用 second-test agent）
- 仅传入：原始需求文本 + 一测的"prod 预期清单"
- **不传**：二测报告 / 二测 agent 的 ID / 二测发现的问题

## 任务约束

audit-agent 收到任务后：
1. 独立设计 3 个测试用例（覆盖至少 3 种角色 + 至少 1 个负向用例）
2. 跑测试，输出原始 DOM 文本 + 截图
3. 给独立结论 PASS/FAIL/UNCLEAR
4. **不审阅二测报告**（即便有 ID 也不调 SendMessage）

## 主 agent 收到 audit 结论后

| 二测结论 | audit 结论 | 动作 |
|---|---|---|
| PASS | PASS | 真 PASS，可发布 |
| PASS | FAIL | **阻断**，escalate 用户 + 重测 |
| PASS | UNCLEAR | escalate 用户决定 |
| FAIL | * | 阻断，先修 |

## audit-agent 任务模板（精简版）

```
你是独立审计 agent。任务：对刚部署的修复做独立复测。

【收到的信息】
- 原始需求：<...>
- 一测的 prod 预期清单：<...>

【你不能看的】
- 二测 agent 的报告
- 二测 agent 的截图

【你要做的】
1. 独立设计 3 个测试用例（至少 3 种角色 + 1 个负向）
2. 用 playwright 跑测试，prod URL 已知
3. 抓 DOM 文本 / console error / 业务字段
4. 给结论 PASS / FAIL / UNCLEAR

【角色矩阵】
鉴权类必跑：admin / 当场注册 qa+ 账号 / impersonate 已有用户
其他类至少 2 种角色

【输出】
- 设计的 3 个测试用例
- 每个测试用例的 5 件套证据（DOM/console/network/截图/业务字段）
- 结论
```

## 月度审计

每月跑一次：
- audit 结论 vs 二测结论 不一致率（健康 5-15%）
- < 2% → audit 在抄
- > 30% → 二测烂
