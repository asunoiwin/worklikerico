---
name: strict-prod-audit
description: 双轮测试 v2 — 矩阵覆盖 + 三层断言 + blast radius 五元清单 + 双 agent 独立验证。修复发布前后强制走此流程。Triggers on - 严格实测 / 双轮测试 / strict audit / 修复验证 / prod 验收 / 一测 / 二测 / DOM 检查 / 假阳性防护 / playwright 二测 / regression UI / 真实用户视角 / 和你看到的不一样.
---

# 严格双轮测试 Skill v2

**核心原则（v2 改版）**：
1. **矩阵化优先于临场设计** — 测试覆盖必填矩阵，不靠 agent 现场决定
2. **三层断言取代 status 200** — HTTP 2xx + DOM 元素 + 业务字段值，缺一不算 PASS
3. **双 agent 独立验证** — 一测二测必须不同 agent 实例 + 不读对方报告
4. **未测维度强制声明** — 缺口要写出来，"未测"不等于"OK"
5. **实证优先于推理（v3 新增）** — 子 agent 文本推理 ≠ 实证；任何根因假设必须 prod 日志 grep + curl 实打 + 文案双向 grep 至少各一次

---

## 阶段 -1：根因证据采集（v3 新增，强制硬约束）

**触发**：任何 prod bug 修复前必跑。绕过即视为方向多半错。

**v1.6.6/v1.6.7/v1.6.8 三轮假修复教训**：所有人靠子 agent 文本推理猜根因（"应该是嵌套子查询 NPE / 异常吞掉 / @Transactional rollback…"），全错。v1.6.9 是因为拉了真日志一行命中 `String.toLowerCase() ... null` 才实锤 `UserServiceImpl.java:117`。

### 三件套

| # | 动作 | 工具 / 命令 | 通过标准 |
|---|---|---|---|
| 1 | **拉真异常 stack** | `larktokenweb/audit-tools/grep-prod-log.sh "<现象关键字>"` | 拿到完整 ERROR 行（含异常类型 + 消息），不接受推测的异常类型 |
| 2 | **curl 实打 prod** | `audit-tools/curl-prod-login.sh` 或针对性 curl | 拿到真实 HTTP code + body.message，确认与用户描述的现象**一致** |
| 3 | **用户报错文案双向 grep** | `grep -rn "<用户描述的文案>" --include="*.java" --include="*.vue" --include="*.js"` | 找到所有抛出位置：前端文案？后端 BizException？GlobalExceptionHandler 兜底？三个分类必须分清楚 |

### 反模式

- ❌ 子 agent 直接推测根因然后开始改 — 必拒
- ❌ "我觉得应该是 XX 异常" — 没 grep prod 日志就是猜
- ❌ "前端显示 X" — 没 grep 前端代码就是没排除前端兜底
- ❌ 一个子 agent 报告就动手 — 必跑两个独立 agent + curl 实证三角验证

### 子 agent 跑偏检测

派调查 sub-agent 后，**主 agent 必须**：
1. 让 sub-agent 给 file:line 证据
2. 主 agent 自己 curl 或 grep 验证 file:line 真的是断点
3. 子 agent 推测的根因 ≠ prod 日志真异常 → **重派**，标"上次跑偏方向"作为反例

---

## 阶段 0：改动前 blast radius 五元清单（强制）

**编码前**输出下表，缺项视为未通过 PM gating：

| 维度 | 命中项 | 已检查 |
|---|---|---|
| 后端模块/包 | (e.g. billing-service/invite) | [ ] |
| DB 表/字段 | (e.g. user_invite, marketing_rule, t_admin_inbox.detail_json) | [ ] |
| API endpoint | 含 admin/* + user/* 双查 | [ ] |
| 前端页面 | 用户面 + admin 面双列（必查 admin 配置页） | [ ] |
| 配置项/规则 | 营销/计费/权限/系统配置 | [ ] |

### 双面需求识别（强触发）

需求文本含 `合并|二合一|统一|迁移|下线|改版|整合|重构|拆分` →
**必须执行**：
1. `grep -r <核心名词同义词集>` admin/* 列出 admin 配置页（同义词 ≥3：中文 + 英文 + 缩写，如 "邀请" → invite/referral/推荐/返佣/邀请码）
2. 查 `db/migration/` 是否需新增迁移
3. 输出"用户面影响 / admin 面影响 / DB 影响"三段，**每段非空**

---

## 阶段 1：本地一测（dev VM）

**目标**：穷尽 + 建预期清单。dev 环境无负担，高/中/低/无风险都做。

**输出**："prod 预期清单"——每个修复点列出"prod 应该看到 X，不应看到 Y"，移交二测当基线。

---

## 阶段 2：prod 二测（独立 agent，不读一测报告）

**铁律**：必须用与一测**不同的 agent 实例**，仅看原始需求 + 一测的"prod 预期清单"，独立设计测试。结论不一致 → 强制 escalate。

### 操作风险分级

| 风险 | 例子 | 二测可做？ |
|---|---|---|
| **无风险** | 登录、查看、点查看/展开/筛选/分页/dropdown、抓 DOM、impersonate、API GET | ✅ |
| **低风险** | 注册新测试账号（qa+v{ver}+{ts}@example.com）、提交异常表单 | ✅ |
| **中风险** | 修改自己测试账号属性、本人小额充值、临时关 captcha 测后开回 | ⚠️ 谨慎 |
| **高风险** | 下线在用模型、删真实用户数据、批量操作、改 prod 系统配置、SQL UPDATE/DELETE | ❌ 严禁 |

### 测试身份矩阵（鉴权类必跑 6 行；其他类至少 3 行）

| # | 角色 | 标识 | 用途 |
|---|---|---|---|
| 1 | admin | lark / lark123 | 后台功能 |
| 2 | 老用户已调用 | impersonate 任意有 usage_log 记录的 user | 计费/账单/账户余额 |
| 3 | 老用户无调用 | impersonate 注册>7天但 usage_log=0 的 user | 引导流 |
| 4 | 当场新注册 | 现场注册 `qa+v{semver}+{yyMMddHHmmss}@example.com` 密码 `Qa@Test123!` | 注册流 |
| 5 | impersonate 态 | admin 注入老用户 | 客服场景 |
| 6 | 未登录 | 无 cookie 直接访问 | 鉴权拦截/重定向 |

**禁止**：仅用 admin lark 测过 = 伪 PASS（admin 接口走 AdminAuthService，普通用户走 UserAuthService，是不同代码路径）。

### 接口入参分支矩阵（鉴权/角色逻辑类必跑）

每个接口列出业务分支表。例：

```
/api/auth/login:
  - {adminLogin:true, username:"lark"}      期望 200 + admin token
  - {adminLogin:true, username:"LARK"}      期望 200 + admin token（大小写）
  - {adminLogin:false, username:user_a}     期望 200 + user token
  - {adminLogin:false, username:USER_A}     期望 200 + user token（大小写）
  - {adminLogin:undefined, ...}             期望默认分支
  - {adminLogin:false, password:""}         期望 4xx + "密码错误"
```

### 边界用例 8 件套

每个新接口必测：空 / 单字符 / 超长 256 / 前后空格 / 大小写混合 / Unicode 中文 / Emoji / SQL 注入符号 `'"--`。

### 跨页业务流程一条龙

注册 → 登录 → 建 API key → 调用 API → 查账单 → 充值 → 邀请 → 退出。每步抓 console error + network 4xx/5xx。

### PASS 三层断言（缺一不算 PASS）

1. **HTTP 层**：2xx
2. **DOM 层**：关键元素出现 + 文案匹配（`expect(page.locator(...)).toContainText(...)`）
3. **业务层**：业务字段值正确（如登录后 `localStorage.token_user` / `window.__USER__.username` 非空）

**反例**："系统繁忙" = HTTP 500 = FAIL（不接受 200 但页面报错）

---

## 阶段 3：报告必填字段（缺一作废）

```
[修复 PR / commit hash]: ...
[Blast radius 五元清单已检查]: 后端模块=X 个 / DB 字段=Y 处 / endpoint=Z 个 / 前端页面=N 个 / 配置项=M 项
[影响面 grep 结果]: 命令 + 命中清单 + 每个文件"已修/不需修+理由"，关键字 ≥3 同义词
[接口分支矩阵]: 表格 接口 / 入参分支 / 期望 / 实际 / 通过
[角色矩阵执行]: 6 行 × 通过/失败/未测+理由（"未测"必须给业务理由）
[新注册账号 email]: 当场新建 qa+ 账号，给注册时间戳 + user_id
[跨页一条龙截图]: 注册→登录→调用→账单→退出，每步 1 张截图 + URL
[console error 清单]: 各页 {url, errors:[], 4xx:[], 5xx:[]}
[业务断言]: HTTP + DOM + 业务字段值，三层
[负向用例]: 错密码/空/超长/特殊字符 各 1 例 + 期望错误码 vs 实际
[未覆盖维度声明]: "本次未测 X 因 Y，风险等级 Z，建议下次补测"——空白即作废
[5 件套证据]: 截图 / HAR / cookies.json / console.log / network.har
```

---

## 阶段 4：独立审计（强制，由不同 agent 跑）

主 agent 收到二测 PASS 后，**必须**派 audit-agent 独立复测：
- audit-agent 不读二测报告
- 仅看原始需求 + 一测预期清单
- 独立设计 3 个测试用例
- 对比结论：一致 → 真 PASS；不一致 → 阻断合并 + escalate

---

## 已踩过的坑（lesson 库精简版）

### 坑 1: API 200 ≠ UI 工作（fmtTime 类型错）
- 必抓 console error + DOM 实际文本，不能仅看 Network。

### 坑 2: admin/lark 账号本身没业务数据 / 不走用户代码路径
- admin 走 AdminAuthService（已 LOWER），普通用户走 UserAuthService（可能没 LOWER）= 不同代码路径
- 必须用 impersonate 已有用户或新注册账号验证用户面。

### 坑 3: headless tooltip / hover 不触发
- 标 NEEDS_MANUAL_CHECK，不能 PASS 也不能 FAIL。

### 坑 4: 浏览器缓存到老 chunk
- 部署后 CF Purge + 提示 Cmd+Shift+R + agent 用 incognito + no-cache。

### 坑 5: API 字段 ≠ UI 显示字段
- grep 前端 source 找出 badge 渲染字段 vs 筛选过滤字段，列出冲突。

### 坑 6: v-if 隐藏关键按钮
- 抓全部行类型 + 按钮分布表，模式清晰即定位条件源。

### 坑 7: 非 chat 模型类型探测路径
- 改完后必 e2e 实测：触发不同 model_type 的健康检查。

### 坑 8: 上游返回 model_type 不一定为真
- catalog 数据需校准；前端兜底；考虑 model_types 多值列。

### 坑 9: 修复引发二次 bug
- 同义词 grep ≥3 关键字 + 列"已修/未修/不需修"三栏。

### 坑 10: 双面需求只改一面
- "二合一/合并/统一" 类必须扫 admin 配置页 + DB schema，不能仅改用户面。

### 坑 11: 一测二测同 agent 共谋
- 二测必须独立 agent 实例 + 不读一测报告。

### 坑 12: "PASS" 概念坍缩
- HTTP 200 + 无 console error ≠ PASS。必须三层断言（HTTP + DOM + 业务字段）。

---

## larktokenweb 项目专属页面清单（回归扫描必跑）

### 用户面（~20 页）
```
/dashboard, /dashboard/keys, /dashboard/keys/new, /dashboard/logs,
/dashboard/billing, /dashboard/billing/recharge, /dashboard/billing/invoices,
/dashboard/usage, /dashboard/models, /dashboard/playground,
/dashboard/invite, /dashboard/invite/records, /dashboard/profile,
/dashboard/profile/security, /dashboard/profile/api-tokens,
/dashboard/notifications, /dashboard/support, /dashboard/support/new,
/dashboard/docs, /dashboard/announcements
```

### Admin 面（~30 页）
```
/larkyun, /larkyun/users, /larkyun/users/:id, /larkyun/channels,
/larkyun/channels/new, /larkyun/channels/health, /larkyun/models,
/larkyun/prices, /larkyun/orders, /larkyun/orders/recharge,
/larkyun/billing/invoices, /larkyun/billing/subscriptions,
/larkyun/logs/api, /larkyun/logs/audit, /larkyun/logs/error,
/larkyun/invite/config, /larkyun/invite/records, /larkyun/invite/rewards,
/larkyun/announcements, /larkyun/support/tickets,
/larkyun/risk/blacklist, /larkyun/risk/rules,
/larkyun/system/config, /larkyun/system/healthcheck, /larkyun/inbox
```

每次升级二测**page.goto 全部 + console.error 抓取**（10 分钟内完成）。

---

## 测试账号管理

- 注册：`qa+v{semver}+{yyMMddHHmmss}@example.com`，密码统一 `Qa@Test123!`
- 清理 SQL（每周日 cron）：
```sql
DELETE FROM relay.t_user
WHERE email LIKE 'qa+%@example.com'
  AND created_at < NOW() - INTERVAL '7 days'
  AND id NOT IN (SELECT user_id FROM relay.t_order WHERE status='paid');
```
- 风控白名单：email LIKE 'qa+%' 跳过频控

---

## 触发条件（自动 invoke）

用户消息含以下词时优先走此 skill:
- "严格实测" / "严格 DOM" / "严格审计" / "双轮测试"
- "修复后请实测" / "再走一遍" / "本地先测再 prod"
- "测一下是否生效" / "deploy 后验证"
- "和你看到的不一样" / "为什么我看到的和你不同"（典型缓存/视角不一致信号）
- 已有 lesson 触发关键词: playwright / 二测 / fmtTime / 假阳性 / DOM 检查
