# design-test-loop Plugin

完整设计-测试链路硬约束 plugin。状态机驱动 + PreToolUse 工具拦截 + 三 skill 闭环。

## 核心价值

把"设计→实现→测试→审计"流程从**主 agent 自觉**升级为**工具调用级硬拦截**：
- **PreToolUse hook 阻塞 Edit/Write**：未通过 design-gate 的代码改动被拒绝
- **会话级状态机**：每个 session 独立跟踪，不可跳过流程
- **3 skill 闭环**：design-gate（设计）→ strict-prod-audit（双轮测试）→ audit-verify（独立审计）

## 状态机

```
INIT
  ↓ UserPromptSubmit 检测代码改动关键字
DESIGN_PENDING
  ↓ 主 agent 输出 Blast radius 五元 + Grep 三栏 + 双面影响声明
DESIGN_DONE              ← PreToolUse hook 检查到此才放行 Edit/Write
  ↓ Edit/Write 执行
IMPL_IN_PROGRESS
  ↓ git commit 检测到
IMPL_DONE
  ↓ 一测 agent 派发（subagent_type 含 test/playwright）
T1_PASS
  ↓ 二测 agent 派发（不同 instance + playwright-audit）
T2_PASS
  ↓ audit-verify agent 派发
AUDIT_PASS
  ↓ update.sh / git tag / gh release
RELEASED 🎉
```

## 触发关键字

### 设计触发
新功能 / 新需求 / 改造 / 重构 / 二合一 / 合并 / 统一 / 迁移 / 下线 / 改版 / 整合 / 拆分

### 代码改动触发
修复 / 修改 / 改动 / 实现 / 添加 / 新增 / 删除 / 优化 / 登录 / 鉴权 / 邀请 / bug

### 测试触发
测试 / 验证 / 部署 / 发布 / 上线 / prod / 升级 / deploy / release

### 项目触发
cwd 含 larktokenweb / panmode

闲聊（"今天天气"等）不触发，不污染 context。

## 文件结构

```
plugins/codex/design-test-loop/
├── .codex-plugin/plugin.json          (manifest)
├── README.md            (本文件)
├── hooks/
│   ├── 01-detect-intent.sh      (UserPromptSubmit: 检测意图 → 推进 INIT→DESIGN_PENDING)
│   ├── 02-gate-check.sh          (PreToolUse Edit/Write: 检查 design-gate 三件套，未通过阻塞)
│   └── 03-state-advance.sh       (PostToolUse: 状态机推进 DESIGN_DONE→IMPL→T1→T2→AUDIT→RELEASED)
└── state/                (运行时生成，每个 session 一个 .state 文件，默认 git ignore)

plugins/codex/design-test-loop/skills/
├── design-gate/SKILL.md         (设计阶段：PM gating + 架构师视野)
├── strict-prod-audit/SKILL.md   (双轮测试：dev 一测 + prod 二测)
└── audit-verify/SKILL.md        (独立审计：第三 agent 复测)
```

## 设计-测试链路三 skill

### 1. design-gate
触发：新功能 / 改造 / 双面词典关键字
输出：Blast radius 五元清单 + 同义词 Grep 三栏 + 双面影响声明 + （可选 PRD）

### 2. strict-prod-audit
触发：任何代码改动后
输出：dev VM 一测 + prod 二测（独立 agent）+ 角色矩阵 6 行 + PASS 三层断言 + 报告 11 必填字段

### 3. audit-verify
触发：strict-prod-audit 二测 PASS 后
输出：独立第三 agent 复测，不读二测报告，仅看原始需求 + 一测预期，独立设计 3 测试用例。结论不一致即阻断 + escalate。

## 紧急绕过

如确需绕过 PreToolUse 阻塞（如 hook 误判），手动写状态文件：
```bash
echo DESIGN_DONE > ~/.codex/state/design-test-loop/<session_id>.state
```
绕过必须在主对话写明理由（被 audit 时可追溯）。

## 状态查询

查当前 session 状态：
```bash
cat ~/.codex/state/design-test-loop/<session_id>.state
```

清理过期状态（手动）：
```bash
find ~/.codex/state/design-test-loop -mtime +7 -delete
```

## 验证

启动新 Codex session 后任意输入"修复一个 bug" → 应看到：
```
[design-test-loop plugin] state: INIT → DESIGN_PENDING
→ 触发关键字「修复」
→ 必走 design-gate skill
→ 通过 design-gate 后才能 Edit/Write（PreToolUse 已启用阻塞）
```

然后尝试 Edit 文件 → 被阻塞，stderr 显示缺失要素 + 操作步骤。

当前会话若已在插件安装前启动，可能需要新开会话才能看到 plugin hook 和 skill 列表。

## 已知限制

1. **无法 100% 强制思考路径**：agent 仍可"应付式"输出 Blast radius 表然后错改。Plugin 只能拦截工具调用，不能拦截思考。
2. **transcript_path grep 依赖关键字**：agent 必须在输出中含特定字符串（"Blast radius"、"已修/未修/不需修"、"用户面影响"等）才能被识别为通过。可能需调正则。
3. **状态文件未自动清理**：每个 session 一个文件，长期会堆积。建议每周 cron。

## 移除 plugin

```bash
# 1. 从 ~/.codex/config.toml 移除 design-test-loop marketplace/plugin 注册
# 2. 删除 plugin 目录
python3 scripts/install_codex_plugins.py --remove
```

## 版本

- v1.0.0 (2026-05-10)：初版，含 PreToolUse 阻塞 + 完整状态机
