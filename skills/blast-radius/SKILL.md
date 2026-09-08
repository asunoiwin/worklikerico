---
name: blast-radius
description: 编码前/编码中爆炸半径分析 — 基于 codebase-memory-mcp 编排实现 GitNexus 同款三能力（detect_changes / impact / rename），零第三方依赖、零 license 风险。Triggers on - blast radius / 影响面 / 爆炸半径 / detect_changes / impact analysis / 改一半 / 同类全检 / 协调重命名 / 改 A 影响哪些 B / git diff 影响 / 上游调用方 / 跨文件重命名.
---

# Blast Radius Skill

**核心定位**：design-gate 第 2.0 节"Codebase Graph 必查"的执行器。把"手 chain trace_path + query_graph"封装成三个一键命令，对齐 GitNexus 的 detect_changes / impact / rename，但**纯本地编排、不引入任何第三方 MCP**。

**与 codebase-memory-mcp 的关系**：本 skill 不是新工具，而是**指令编排层**——告诉 Claude 在三种典型场景下，如何固定套路地调用现有图谱工具，输出结构化报告。

**前置**：项目已被 codebase-memory-mcp 索引（larktokenweb 已索引为 `Users-rico-claude-larktokenweb`）。未索引先跑 `index_repository`。

---

## 能力一：detect_changes（git diff → 受影响进程 + 风险等级）

**用途**：编码完成准备 commit 前 / strict-prod-audit 一测前必跑。回答"我刚改的这些代码，下游会炸哪些地方"。

**输入**：当前 git working tree（未暂存 + 已暂存 diff）或指定 commit range。

**执行步骤**（按序，不可跳）：

1. **拿变动符号**：跑 `bash ~/.claude/plugins/design-test-loop/scripts/git-diff-to-symbols.sh [optional-range]`，输出 JSON：
   ```json
   {"files":[{"path":"a.java","changed_symbols":["UserService.login","UserService.logout"]}], "raw_diff_lines": 142}
   ```
2. **对每个变动符号跑 trace_path**：
   - `trace_path(function_name=symbol, mode='calls')` 拿上游调用方（depth 1, 2）
   - 调用方数 ≥10 → 标 `HIGH risk`；3-9 → `MEDIUM`；0-2 → `LOW`
3. **对每个变动文件查 FILE_CHANGES_WITH**：
   ```cypher
   MATCH (f:File {file_path: 'a.java'})-[r:FILE_CHANGES_WITH]-(other:File)
   WHERE r.coupling_score > 0.5
   RETURN other.file_path, r.coupling_score ORDER BY r.coupling_score DESC LIMIT 5
   ```
   高耦合文件标"建议同步检查"。
4. **查受影响 Route**：变动符号若是 Controller/Handler，`query_graph` 查 Route 节点直接依赖。
5. **同 pattern 漏改检查**：每个变动符号跑 `query_graph` 查 SIMILAR_TO 边，列同模式但本次未改的节点。

**输出格式**（必须三段全列）：

```markdown
## Detect Changes Report

### 1. 变动统计
- 变动文件: 5
- 变动符号: 12
- diff 行数: 142

### 2. 受影响下游（按风险排序）
| 变动符号 | 上游调用方数 | 风险 | 关键调用方 |
| UserService.login | 14 | HIGH | LoginController, AuthFilter, AdminLoginController... |
| UserService.logout | 3 | MEDIUM | LogoutHandler, SessionCleanup |

### 3. 高耦合文件（FILE_CHANGES_WITH 建议同步检查）
| 本次变动文件 | 高耦合伙伴 | coupling_score | 已同步? |
| UserService.java | UserMapper.xml | 0.91 | ❌ 需检查 |
| UserService.java | UserController.java | 0.84 | ✅ 已改 |

### 4. 受影响 Route
- POST /api/user/login → UserService.login (HIGH)
- POST /api/admin/login → AdminAuthService.login (未变动但同 pattern，⚠️ 需评估)

### 5. 同 pattern 漏改候选（SIMILAR_TO）
| 变动符号 | 相似节点 | jaccard | 状态 |
| UserService.login | AdminAuthService.login | 0.78 | ⚠️ 未改，同义词 grep 已确认双面需求 |
```

**失败条件**：任一段缺失 = 视为未跑，design-gate 不放行 commit。

---

## 能力二：impact（一键符号级 blast radius）

**用途**：设计阶段评估"如果我改 X 函数，影响面到底多大"。比 detect_changes 早，**还没动手前**用。

**输入**：单个符号 qualified_name（如 `com.lark.token.service.UserService.login`）。

**执行步骤**：

1. `trace_path(function_name=X, mode='calls')` 拿全部上游调用方
2. 按 depth 分组：depth 1（直接调用方）/ depth 2（间接）/ depth 3+（远端）
3. 每个调用方计算 confidence：基于 CALLS 边的 `confidence` 属性（codebase-memory-mcp 自带）
4. `query_graph` 查所有 USAGE 边指向 X 的位置（变量引用、import 等）
5. 若 X 是 entry_point 或 is_exported=true → 额外查 Route + 外部 HTTP_CALLS

**输出格式**：

```markdown
## Impact Analysis: com.lark.token.service.UserService.login

### Depth 1（直接调用方，6）
- LoginController.doLogin [CALLS 0.95]
- AdminLoginController.adminLogin [CALLS 0.92]
- AuthFilter.preHandle [CALLS 0.88]
- ... (3 more)

### Depth 2（间接调用方，14）
- LoginController ← /api/user/login Route handler [HTTP_CALLS]
- AdminLoginController ← /api/admin/login Route handler [HTTP_CALLS]
- ...

### USAGE（非调用，引用 10 处）
- com.lark.token.dto.LoginRequest [import]
- ...

### 总结
- 总 blast radius: 30 节点
- 风险等级: HIGH（>20）
- 必须双面检查: ✅（命中 admin/* + user/* 双 Route）
- 建议测试矩阵: 用户登录 / admin 登录 / 401 / 429 / 并发
```

---

## 能力三：rename（协调多文件重命名）

**用途**：要把函数/类/字段从旧名改成新名，需要一次性拿全所有引用点。

**输入**：`{ old_name: "X", new_name: "Y", scope: "qualified_name" or "name" }`

**执行步骤**：

1. `search_graph(name_pattern=old_name)` 拿定义节点
2. `query_graph` 查所有指向定义的 CALLS / USAGE / IMPORTS / DEFINES_METHOD 边
3. `get_code_snippet(qualified_name)` 读每个引用点上下文，确认是真引用而非同名变量
4. 输出"按文件分组的编辑清单"：每个文件列出需要替换的行号 + 旧字符串 + 新字符串

**输出格式**：

```markdown
## Rename Plan: UserService.login → UserService.authenticate

### 影响文件: 8

#### src/.../UserService.java（定义）
- 第 42 行: `public User login(...)` → `public User authenticate(...)`
- 第 78 行: 内部递归调用 `this.login(...)` → `this.authenticate(...)`

#### src/.../LoginController.java（调用方）
- 第 30 行: `userService.login(req)` → `userService.authenticate(req)`

... （列全部）

### ⚠️ 风险点
- 第 5 个文件 `Test.java:120` 有同名局部变量 `String login = ...`，**不应替换**
- public API 改名会破坏外部调用方，需检查是否有 SDK 客户端依赖

### 建议执行
- 用 `Edit replace_all` 批量改纯函数调用
- 用单条 `Edit` 改有歧义的 5 处
- 改完跑 `detect_changes` 验证无遗漏
```

**反模式**：
- ❌ 跳过步骤 3 的 get_code_snippet 直接 grep-replace → 误改同名变量
- ❌ rename 完不跑 detect_changes 验证 → 漏改导致编译失败

---

## 失败惩罚

- detect_changes 缺任一段 → design-gate 不放行 commit
- impact 跳 depth 分组 → 视为未做分析
- rename 跳第 3 步上下文校验 → 视为暴力替换，回 design-gate 1.1

## 与 design-gate v4 对接

- design-gate 第 2.0 节 Q5 = 调本 skill 的 detect_changes（pre-commit）
- design-gate 第 2.0 节 Q1 升级 = 调本 skill 的 impact（设计阶段）
- 大型重命名/拆分需求 = 调本 skill 的 rename
