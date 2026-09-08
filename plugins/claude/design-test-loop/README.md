# design-test-loop Plugin v2.0.1

## 当前状态

这套插件的 hook **当前已重新挂回 `~/.claude/settings.json`，并以 `DTL_GATE_LEVEL=warn` 灰度启用**。v2.0 的 `UserPromptSubmit` 曾把中文关键字提示写进 Claude 上下文，其中一次出现坏 UTF-8 字节，触发 `The model's tool call could not be parsed`；v2.0.1 已修复并改成默认静默。

v2.0.1 已做止血修复：
- hook 默认静默，不再把提醒写进每轮对话
- `01-detect-intent.sh` 改用 Python 做 Unicode 匹配，不再让 bash/grep 处理中文关键字
- 新增 `scripts/self-test.sh`，切硬阻塞前必须先跑过

切硬阻塞建议顺序：

```bash
~/.claude/plugins/design-test-loop/scripts/self-test.sh
# 确认 3-5 天无误判和 parse 错误后，再从 warn 切回硬阻塞
```

完整设计-实现-测试链路硬约束。**3 个 hook + 4 个 gate**，把"AI 写代码屎山 / 不自审 / 不验真实效果"三大问题用工具级拦截兜底。

## 为什么有这个插件

光靠 CLAUDE.md 写规则没用——Claude 读了照样违反。这个插件用 bash hook 在工具调用层拦截：

| 想拦的行为 | 拦在哪 |
|---|---|
| 没想清楚就动手 | **Gate-1**（Edit/Write 前要先输出设计三件套） |
| 方案阶段没有分派体系 | **Gate-1**（项目经理类任务可用 PM 工作包设计门：工作包 / RACI / 并行 / 验收 / 阻塞） |
| 屎山式乱写 | **Gate-2**（Edit/Write 前要先写 5 段精简 PRD） |
| 写完一堆 AI 痕迹就 commit | **Gate-3**（git commit 前先 remove-ai-slop 清理本次 diff） |
| 写完不自审就 commit | **Gate-3**（清理后再做 4 段自审） |
| 没测就发布 | **Gate-4**（release 前要先派 agent 跑测试） |

绕过每个 gate 都要写明理由（被审计时可追溯）。

## 状态机

```
INIT
  ↓ UserPromptSubmit 命中"修复/改造/优化"等关键字
DESIGN_PENDING            ← Gate-1：Edit/Write 被拦
  ↓ 主对话输出 design-gate 三件套（影响面 + 同类全检 + 双面影响）
DESIGN_DONE               ← Gate-2：Edit/Write 仍被拦
  ↓ 主对话输出 spec-first 5 段
IMPL_SPEC_OK
  ↓ 首次 Edit/Write 通过
IMPL_IN_PROGRESS          ← Gate-3：git commit 被拦
  ↓ remove-ai-slop 清理本次 diff + doubt-review 自审
IMPL_DONE
  ↓ 派一测 agent
T1_PASS                   ← Gate-4：release 被拦
  ↓ 派独立二测 agent
T2_PASS                   ← Gate-4：release 仍被拦
  ↓ 派 audit-verify agent
AUDIT_PASS
  ↓ update.sh / git tag / gh release
RELEASED 🎉
```

## 4 个 Gate 详解

### Gate-1 设计门（DESIGN_PENDING）
**拦谁**：Edit / Write / NotebookEdit
**要求**：主对话输出下面两条路径之一。

工程设计路径：
- **影响面五元**：后端 / DB / 接口 / 前端 / 配置 各扫一遍
- **同类全检三栏**：已修 / 未修 / 不需修 + 理由
- **双面影响声明**：用户面 / admin 面 / DB 影响

PM 工作包路径：
- **工作包/任务卡**：每包写清输入、输出、交付物
- **RACI/DRI/岗位负责人**：谁执行、谁审查、谁验收、谁拍板
- **并行泳道与依赖**：哪些能并行、哪些前置、哪些会阻塞
- **验收标准 / Done 定义**：每包可验证断言和证据
- **未决决策 / 阻塞条件 / 风险升级口**：什么时候必须停下来找用户或负责人

详见 `design-gate` skill。

### Gate-2 实现门（DESIGN_DONE）
**拦谁**：Edit / Write / NotebookEdit
**要求**：主对话输出 spec-first 5 段
1. **目标**（一句话）
2. **产出物**（具体改哪些文件 / 新增什么）
3. **边界**（不做什么，≥3 条）
4. **测试标准**（可验证断言，≥2 条）
5. **影响面**（核心路径上 1-2 个最重要的连带）

详见 `spec-first` skill。

### Gate-3 提交门（IMPL_IN_PROGRESS）
**拦谁**：Bash 命令含 `git commit`
**要求**：两件事，顺序为「先清理、再自审」——

**① remove-ai-slop 清理本次 diff**
- 清掉本次改动引入的 AI 痕迹：冗余注释 / 对本区域反常的过度防御 / 类型逃逸 / 单次使用变量 / 风格不一致
- 只清不重构、不拆方法、不评架构；风格一致的写法不算 slop，保留
- 结尾带标记 `remove-ai-slop：已清理`（或「本次改动无 slop 可清」）hook 才放行
- 详见 `remove-ai-slop` skill。绕过：`DTL_DISABLE_SLOP_GATE=1`

**② doubt-review 4 段自审**
- **CLAIM**：改了啥（1 句话）
- **EXTRACT**：关键改动点（2-4 条）
- **DOUBT**：怀疑点（3 个，"如果...会怎样"句式）
- **RECONCILE**：每个怀疑的回应（已处理 / 需测覆盖 / 接受残留风险）
- 详见 `doubt-review` skill。绕过：`DTL_DISABLE_DOUBT_GATE=1`

### Gate-4 发布门（T1_PASS / T2_PASS）
**拦谁**：Bash 命令含 `update.sh` / `gh release` / `git tag` / `git push --tags`
**要求**：把下一阶段测试 agent 派完
- T1_PASS：派独立二测 agent（不同 instance、不读一测报告）
- T2_PASS：派 audit-verify agent（独立设计 3 个测试用例）

## 触发关键字

**设计触发**：新功能 / 新需求 / 改造 / 重构 / 二合一 / 合并 / 统一 / 迁移 / 下线 / 改版 / 整合 / 拆分
**代码改动触发**：修复 / 修改 / 改动 / 实现 / 添加 / 新增 / 删除 / 优化 / 登录 / 鉴权 / 邀请 / bug
**测试触发**：测试 / 验证 / 部署 / 发布 / 上线 / prod / 升级 / deploy / release
**项目触发**：当前目录含 `larktokenweb` / `panmode`

闲聊不会触发，不污染对话。

方案 / 讨论 / 只读诊断 / 不动代码类 prompt 会标成 LOW 风险，不进入实现状态机；只有真正出现修改、实现、改造等代码意图时才启动 `DESIGN_PENDING`。

## 灰度 / 紧急绕过

如果误判太多或新功能开发期，用环境变量降级：

```bash
# 完全关闭 hook（故障止血）
export DTL_HOOKS_ENABLED=0

# 打开 hook 调试输出；默认静默，避免污染 Claude 工具调用上下文
export DTL_VERBOSE=1

# 全部 gate 改软警告（推荐先这样跑几天看误判率）
export DTL_GATE_LEVEL=warn

# 单独关闭 spec-first / doubt-review
export DTL_DISABLE_SPEC_GATE=1
export DTL_DISABLE_DOUBT_GATE=1
```

单次绕过某个 state（写明理由）：
```bash
echo DESIGN_DONE > ~/.claude/state/design-test-loop/<session-id>.state
```

## 联动 skill 清单

| skill | 在哪个 gate 用 | 干什么 |
|---|---|---|
| `design-gate` | Gate-1 | 输出设计三件套 |
| `spec-first` | Gate-2 | 输出 5 段精简 PRD |
| `remove-ai-slop` | Gate-3 | commit 前清掉本次 diff 的 AI 痕迹（清理类黑盒测试冠军，零误伤）|
| `doubt-review` | Gate-3 | 清理后输出 4 段自审 |
| `strict-prod-audit` | 一测 + 二测 | 双轮测试 SOP |
| `devtools-verify` | 一测 | 用 Chrome DevTools MCP 做结构化 DOM 断言（替代部分 playwright 截图）|
| `audit-verify` | Gate-4 | 独立第三 agent 复测 |
| `blast-radius` | Gate-1 | 影响面分析工具 |
| `memory-rules` | 全程 | 记忆系统使用规范 |
| `channel-onboarding` | 新接渠道时 | 接入 SOP |

## 文件结构

```
~/.claude/plugins/design-test-loop/
├── plugin.json
├── README.md（本文件）
├── hooks/
│   ├── 01-detect-intent.sh     UserPromptSubmit：识别意图，启动状态机
│   ├── 02-gate-check.sh        PreToolUse：4 个 gate 的拦截逻辑
│   └── 03-state-advance.sh     PostToolUse：状态机推进
├── state/                       每个 session 一个 .state 文件
└── scripts/
    └── git-diff-to-symbols.sh   blast-radius 辅助脚本

~/.claude/skills/
├── design-gate/
├── spec-first/         （v2.0 新增）
├── doubt-review/       （v2.0 新增）
├── devtools-verify/    （v2.0 新增）
├── memory-rules/       （v2.0 新增）
├── strict-prod-audit/
├── audit-verify/
├── blast-radius/
└── channel-onboarding/
```

## 已知限制

1. **拦不了思考路径**：Claude 仍可"应付式"输出三件套然后错改。Hook 只能挡工具调用，挡不了脑子里怎么想。
2. **依赖关键字识别**：transcript grep 必须命中特定字符串，可能误判。每个 skill 文件最后都有"关键字提示"段，告诉主 agent 输出时该带哪些标记词。
3. **生成风格无法 hook 强制**：比如"说人话"、"先排查根因"这些只能留 CLAUDE.md。
4. **状态文件需手动清理**：每 session 一个文件，默认存放在 `~/.claude/state/design-test-loop/`；也可用 `WORKLIKERICO_DTL_STATE_DIR` 改到其他运行目录。

## 升级 / 移除

升级（保留状态）：直接覆盖 hooks/*.sh 和 plugin.json，会话继续走原状态。

移除：
```bash
# 1. 从 ~/.claude/settings.json 移除三个 hook 注册
# 2. 删 plugin 目录
rm -rf ~/.claude/plugins/design-test-loop/
# 3. （可选）skill 目录可保留，仍能手动调
```

## 版本

- **v2.1.0 (2026-06-01)**：Gate-3 提交门加「清理环」——commit 前先用 `remove-ai-slop`（清理类黑盒测试冠军）清掉本次 diff 的 AI 痕迹，再走 doubt-review 自审；新增绕过开关 `DTL_DISABLE_SLOP_GATE`；补 self-test 用例；顺手修了提交门 `grep -c` 无匹配时的整数比较隐患
- **v2.1.1 (2026-06-09)**：Gate-1 增加 PM 工作包设计门（工作包/RACI/并行泳道/验收/未决决策），方案/讨论/只读类 prompt 标 LOW 风险，避免普通咨询进入重实现门。
- **v2.0.1 (2026-06-01)**：修复 UserPromptSubmit 中文关键字坏 UTF-8 风险；hook 默认静默；新增 self-test；全局 settings 以 `DTL_GATE_LEVEL=warn` 灰度启用
- **v2.0.0 (2026-06-01)**：加 Gate-2（spec-first）+ Gate-3（doubt-review）；新增 devtools-verify / memory-rules skill；改写所有 hook 提示语为"说人话"风格；加灰度开关
- v1.0.0 (2026-05-10)：初版，PreToolUse 阻塞 + 完整状态机
