---
name: design-gate
description: 设计阶段强约束 — PM gating + 架构师视野融合。任何"新功能/较大改造/模糊需求/含合并迁移下线改版关键字"的代码改动前必走，与 strict-prod-audit 形成"设计→测试"完整链路。Triggers on - 新功能 / 新需求 / 改造 / 重构 / 二合一 / 合并 / 统一 / 迁移 / 下线 / 改版 / 整合 / 拆分 / PM gating / 设计阶段 / 全局视野 / 架构师视角 / 影响面 / blast radius.
---

# 设计阶段强约束 Skill（设计-测试链路上半段）

**核心原则**：编码前先建模功能完整拓扑（数据流 + 模块边界 + 双向影响 + 同类位置），杜绝"看到代码就动"。

**与下半段对接**：本 skill 完成 → 实现 → 触发 strict-prod-audit skill（双轮测试）→ audit-verify（独立审计）

---

## 触发条件

- 新功能 / 较大改造 / 模糊需求
- 需求文本含双面词典关键字：`合并|二合一|统一|迁移|下线|改版|整合|重构|拆分`
- bug 类豁免 PM gating 但**不豁免架构师视野**（仍走第二节）

---

## 第零节：意图对称（v3 新增，硬前置）

**触发**：任何方案输出前必跑。绕过 = 方案与用户期望错位。

**v1.6.9 教训**：用户要求 case 1 + case 2 都"两者都要"（根因 + 验证），但若不显式问，主 agent 容易默认"结果导向"——只看 bug 是否复现，不挖根因。同样 case 2"二合一"用户的真实意图是**业务模型层面的合并**（一个邀请码、奖励策略二选一），不只是 UI tab 合并——只问"合并到哪一档"会得到错的答案。

### 必问对齐（在出方案前）

| 维度 | 问题 | 候选答案需用户选 |
|---|---|---|
| 1. 目的导向 | 这件事是要**结果**（修好/能用）还是**根因**（找清楚为什么）还是**两者都要**？ | 结果 / 根因 / 双修 |
| 2. 真实意图 | 用 1 句话复述"用户真正想要的状态" | 用户认可 = 对称 |
| 3. 范围边界 | 哪些**看似相关**但**不在**本次 scope？ | 列 ≥3 项明确剔除 |
| 4. 交付物 | 用户期待的输出物是文档？代码？测试报告？还是端到端跑通？ | 用户拍 |

### 反模式

- ❌ 看到关键词直接出方案 — 关键词只是入口，意图才是目标
- ❌ 把"我以为的"当"用户说的" — 必须用用户原话或选项确认
- ❌ 跳过这一节直接走第一节 PM gating — 第一节是"怎么做"，第零节是"做什么"，顺序不能反

---

## 第一节：PM gating（产品视角）

### 1.1 盘需求精准（不重复已确认事项）

盘问前先做"已知 vs 未知"扫描（对话历史 + memory_recall + 代码现状）。
只就模糊点用 `/grill-me` 风格提问：每轮 ≤3 问，每问需能让用户做不同决策；≥5 轮无共识 → 自停说明缺什么上下文。

### 1.2 高维产品视角（防局部最优）

出 PRD 前必问三维度，**任一答不出 = 视角不够，回 1.1**：
- **竞品/行业**：同类 SaaS（如 OneAPI/NewAPI/OpenRouter/LiteLLM）怎么做？相同还是差异化？
- **用户终极价值**：用户根诉求是什么？当前功能是路径最短解吗？
- **长期演进**：3 个月后扩展形态？现在设计会变债吗？

### 1.3 出文档/拆任务

`/to-prd`（必含字段：背景 / 竞品对标 / 用户故事 / 反范围 / 分阶段 / 验收 / 风险 / 度量）+ `/to-issues` 拆 vertical slice。
多任务并行前先一句话画"统一收口图"；PRD 长度与改动规模成比例（不倒挂）。

### 1.4 决策日志

PRD 通过审批后关键决策落 `memory_store(category='decision', importance≥0.85)`，含选 A 不选 B 理由 + 反范围 + 验收基准。
下次同类需求 1.1 先 `memory_recall` 召回。

### 1.5 豁免（保留 hotfix 通道）

"小改/hotfix/立刻做" / 单文件<50 行 / bug 根因已明确 → 跳 1.1-1.3，仍走规则 5 + **第二节架构师视野**。
跳过必须一句话说明理由。

### 1.6 反 PM 自爆

简单需求强行走流程 = 违反"简单优先"原则；自检"这套流程现在带来清晰还是耗时"。

---

## 第二节：架构师视野（任何代码改动必走，bug 类不豁免）

**与 PM 视角互补**：PM 看"做什么 / 给谁用 / 反范围"，架构师看"改 A 影响哪些 B / 怎么避免改一半"。

### 2.0 Codebase Graph 必查（v4 新增，硬前置；缺证据 = 拒绝编码）

**触发**：第零节意图对称完成后立即跑，**先于 2.1 五元清单**。
**根因**：v1.6.6 / v1.6.9 改一半 bug 反复出现，本质是 grep 找不全。codebase-memory-mcp 有 47k 边的图谱，但 PM gating 从未强制调用 → 同类位置漏改。

**强制四查（larktokenweb 已索引为 `Users-rico-claude-larktokenweb`，其他项目用对应 project 名）**：

| 查询 | 工具 | 目的 | 输出形式 |
|---|---|---|---|
| Q1 调用方追溯 | `trace_path(function_name, mode='calls')` 或 `query_graph` 找 CALLS 入边 | 改 A 函数 → 谁在调用？影响哪些上游路径？ | 列 ≥1 跳调用方，标"已评估/需改" |
| Q2 同变更耦合 | `query_graph` 查 FILE_CHANGES_WITH 边（按 coupling_score 排序） | 历史上和我要改的文件**总是一起改**的兄弟文件 | 列 top 5 耦合文件 + score |
| Q3 同 pattern 检索 | `search_graph(name_pattern=...)` + `query_graph` 查 SIMILAR_TO 边 | 语义/结构相似的位置（漏改高发区） | 列 ≥3 同类节点 + 已修/未修/不需修 |
| Q4 路由影响 | `query_graph` 查 Route 节点 + HTTP_CALLS 边 | admin/user 双面接口是否都覆盖 | 列受影响 Route，标 admin/user 两侧 |
| **Q5 一键 blast radius** | 调 `blast-radius` skill 的 `impact` 能力（设计阶段）/ `detect_changes` 能力（commit 前） | 自动编排 Q1-Q4 + 风险等级 + 同 pattern 漏改候选 | 见 blast-radius skill 输出格式 |

**Q5 用法**：
- **设计阶段**（还没动代码）：对每个要改的核心函数调 `impact(qualified_name)` → 拿 depth 1/2/3 调用方 + 风险等级
- **编码完成准备 commit**：调 `detect_changes` → 一次拿全本次改动的下游影响 + 高耦合伙伴 + 漏改候选

Q5 是 Q1-Q4 的"一键编排器"，**优先用 Q5**；只有图谱未覆盖的特殊场景（如纯配置文件、纯前端样式）才退回手动 Q1-Q4。

**输出要求**：Q5 的 blast-radius 报告 + Q1-Q4 补漏证据全列在设计稿"## Codebase Graph 证据"段，**Q5 未跑或报告缺段 = 拒绝编码**。

**与 2.3 同义词 grep 的关系**：图查询是**结构层**（精确，找定义和边），grep 是**文本层**（兜底，找字符串/配置/注释）。两层互补，不能互相替代——图查不到的字符串配置仍需 grep。

**与下游对接**：本节输出的 "同类位置 + 耦合文件 + 受影响 Route" 直接喂给 2.1 五元清单作为命中项的来源；strict-prod-audit 的测试矩阵也要覆盖这些位置。

### 2.1 Blast radius 五元清单（编码前必填，缺项 = 拒绝编码）

| 维度 | 命中项 | 已检查 |
|---|---|---|
| 后端模块/包 | (e.g. billing-service/invite) | [ ] |
| DB 表/字段 | (e.g. user_invite, marketing_rule, t_admin_inbox.detail_json) | [ ] |
| API endpoint | **admin/* + user/* 双查**（如 /api/auth/login adminLogin true/false 双分支） | [ ] |
| 前端页面 | **用户面 + admin 面双列**（必查 admin 配置/审计/统计页） | [ ] |
| 配置项/规则 | 营销/计费/权限/系统配置 | [ ] |

### 2.2 双面需求识别词典

需求文本含 `合并|二合一|统一|迁移|下线|改版|整合|重构|拆分` →
- 强制 grep `admin/*` 列出 admin 配置页
- 强制查 `db/migration/` 是否需新增迁移
- 输出"用户面影响 / admin 面影响 / DB 影响"三段，**每段非空**

### 2.3 同义词 grep（规则 6 升级）

grep 关键字 ≥3：中文词 + 英文词 + 业务缩写
- e.g. "邀请" → invite / referral / 推荐 / 返佣 / 邀请码
- e.g. "登录" → login / auth / Auth / signin / 鉴权
- e.g. "计费" → billing / charge / cost / 费用 / 扣费

输出三栏：**已修 / 未修 / 不需修+理由**，缺一栏视为未执行。
单关键字 grep 视为未执行。

### 2.4 接口路径双探针

鉴权 / 角色逻辑 / 权限 / 配置类接口若有 admin/user 双分支：
- 改一面必查另一面
- 仅改 `AdminAuthService` 不查 `UserAuthService` = 改一半 = 失格
- e.g. v1.6.6 admin 用户名 LOWER 修了，但用户面登录仍报"系统繁忙" — 因为没改 UserAuthService

### 2.5 配对操作必双向（CLAUDE.md 规则 6 引用）

加密 ↔ 解密 / 缓存写 ↔ 失效 / 鉴权前置 ↔ 兜底校验 / controller 拆分 ↔ URL 仍可达 / 用户面新增 ↔ admin 配置页对应

---

## 第三节：输出格式（设计阶段最终交付）

```markdown
## Codebase Graph 证据（v4 新增，先于五元清单）
- Q1 调用方追溯（trace_path）: ...（列调用方 + 已评估状态）
- Q2 同变更耦合（FILE_CHANGES_WITH top5）: A.java(0.82) / B.ts(0.71) / ...
- Q3 同 pattern 节点（SIMILAR_TO / search_graph）:
  | 节点 | 状态 | 理由 |
  | X.foo() | 已修 | 直接相关 |
  | Y.bar() | 未修 | 同 pattern 待改 |
  | Z.baz() | 不需修 | 业务不同 |
- Q4 受影响 Route: /api/admin/login（admin 面）/ /api/user/login（用户面）

## Blast Radius 五元清单
| 维度 | 命中项 | 已检查 |
| 后端模块 | ... | ✓ |
| DB 字段 | ... | ✓ |
| API endpoint | ... admin/* + user/* | ✓ |
| 前端页 | ... 用户面 + admin 面 | ✓ |
| 配置项 | ... | ✓ |

## 同义词 Grep 矩阵
关键字组：[X / Y / Z]（≥3）
| 文件 | 行 | 状态 | 理由 |
| A.java | 100 | 已修 | 直接相关 |
| B.java | 200 | 未修 | 同 pattern 待改 |
| C.java | 50 | 不需修 | 业务语义不同 |

## 双面影响声明
- 用户面影响: ...
- Admin 面影响: ...
- DB 影响: ...

## PRD（如适用）
（链接 to-prd skill 输出 / 或一句话说明豁免理由）
```

---

## 失败惩罚

- **缺 Codebase Graph 证据四查任一项 → 不进入实现阶段**（v4 新增）
- 缺 Blast radius 表 → 不进入实现阶段
- 缺 Grep 三栏 → 视为未做同类全检
- "用户面/admin 面/DB 影响"任一段空白 → 视为视角不全，回 PM gating 1.1
- 实现完跳过 strict-prod-audit skill → 双轮测试硬约束失败
- **strict-prod-audit + audit-verify 通过后跳过第四节 SOP 沉淀 → 经验丢失，下次同类问题重蹈覆辙**（v4 新增）

---

## 第四节：SOP 沉淀（v4 新增，audit-verify PASS 后强制）

**触发**：audit-verify 独立审计 PASS 后立即跑。绕过 = 经验不复用 = 同坑二刷。
**根因**：每次方案/教训只在当下会话存在，没有结构化沉淀 → 下次同类需求 PM gating 1.1 / `memory_recall` 召不回 → 重复设计、重复试错。

### 4.1 必沉淀的三类资产

| 资产 | 工具 | 触发条件 | scope |
|---|---|---|---|
| **决策**（为什么选 A 不选 B） | `memory_store(category='decision', importance≥0.9)` | PM gating 1.2 三维度任一有取舍 | 项目名 |
| **教训**（试错 / 反模式 / 误导报错 / 改一半教训） | `lesson_capture(pitfall, solution, triggerKeywords≥3)` | 第零节意图错位 / 2.0 图查询发现漏改 / 2.4 双探针 catch / audit-verify 暴露二测假阳性 | lesson:项目名 |
| **架构决策**（涉及模块边界 / 数据模型 / 跨服务契约） | `manage_adr(mode='update')` 写入 codebase-memory-mcp | 2.1 五元清单含 DB 字段新增 / API 契约变更 / 模块拆分合并 | codebase 项目 |

### 4.2 沉淀字段最小集（缺字段视为未沉淀）

**decision**：
- 决策：选 A 不选 B
- 备选：B 是什么、为什么不选
- 反范围：明确不做什么
- 验收基准：怎么判断有效
- 关联 PRD/issue 链接

**lesson**：
- pitfall：≥10 字描述坑长什么样（一句话能让未来 Claude 一眼认出）
- solution：≥5 字描述怎么解（动作可执行，不是"小心点"）
- triggerKeywords：≥3 个未来 lesson_recall 能命中的词（含中文 + 英文 + 业务缩写）
- root_cause_layer：标注落在 CLAUDE.md 规则 5 的哪一层（设计 / 状态流转 / 数据结构 / 边界条件）

**ADR**：
- 标题、状态（accepted/superseded）、决策、上下文、后果
- 链接到 codebase 节点（function qualified_name / file path）

### 4.3 反模式

- ❌ `lesson_capture` triggerKeywords 留空或 <3 → recall 永远不命中 = 等于没存
- ❌ `decision` 不写"为什么不选 B" → 三个月后看不出取舍逻辑，等同于没存
- ❌ 把 ADR 当 decision 存到 claude-memory-pro → 跨项目无法被 codebase MCP 关联
- ❌ 沉淀写完不在本次设计稿"## SOP 沉淀回执"段贴 memory ID / ADR ID → 无法审计是否真存了

### 4.4 输出格式追加（第三节末尾）

```markdown
## SOP 沉淀回执（v4 新增，audit-verify PASS 后填）
- decision ID: mem-xxx（importance=0.92, scope=larktokenweb）
- lesson ID: lesson-xxx（triggerKeywords=[邀请码,invite,referral]）
- ADR ID: adr-xxx（manage_adr 写入 codebase-memory-mcp）
- 不沉淀理由（如适用）: ...（hotfix/纯重构等可豁免，但须一句话说明）
```

---

## 与下游 skill 对接

完成本 skill → 实现 → 必触发 `strict-prod-audit` skill（双轮测试） → 二测 PASS 后必触发 `audit-verify` skill（独立审计）。
