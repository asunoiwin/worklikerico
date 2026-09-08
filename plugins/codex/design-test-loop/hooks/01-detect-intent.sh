#!/usr/bin/env bash
# UserPromptSubmit hook：检测代码改动意图，初始化状态机
# INIT -> DESIGN_PENDING

set -e

[ "${DTL_HOOKS_ENABLED:-1}" = "1" ] || exit 0

INPUT=$(cat)

HOOK_INPUT="$INPUT" python3 <<'PY'
import json
import os
import pathlib
import sys


def pick(text, keywords):
    for keyword in keywords:
        if keyword in text:
            return keyword
    return ""


def log(message):
    if os.environ.get("DTL_VERBOSE", "0") == "1":
        print(message, file=sys.stderr)


try:
    data = json.loads(os.environ.get("HOOK_INPUT", "{}"))
except json.JSONDecodeError:
    data = {}

prompt = data.get("prompt", "") or ""
cwd = data.get("cwd", "") or ""
session_id = data.get("session_id", "default") or "default"

state_dir = pathlib.Path(
    os.environ.get(
        "WORKLIKERICO_DTL_STATE_DIR",
        str(pathlib.Path.home() / ".codex" / "state" / "design-test-loop"),
    )
)
state_dir.mkdir(parents=True, exist_ok=True)
state_file = state_dir / f"{session_id}.state"

design_trig = pick(
    prompt,
    ["新功能", "新需求", "改造", "重构", "二合一", "合并", "统一", "迁移", "下线", "改版", "整合", "拆分"],
)
code_trig = pick(
    prompt,
    ["修复", "修改", "改动", "实现", "添加", "新增", "删除", "优化", "登录", "鉴权", "邀请", "bug"],
)
test_trig = pick(prompt, ["测试", "验证", "部署", "发布", "上线", "prod", "升级", "deploy", "release"])

# 风险分档（2026-06-06）：高风险全门 enforce；低风险设计/spec 门软提示；判不出=中风险(enforce)。
# 注意：project 路径不再当触发条件——"在项目目录里"不等于"要改代码"（修掉门禁过度触发的硬根因）。
high_trig = pick(prompt, ["计费", "扣费", "余额", "计价", "定价", "鉴权", "认证", "路由", "选路",
                          "状态机", "串单", "迁移", "flyway", "schema", "生产", "prod",
                          "发布", "release", "部署", "deploy"])
low_trig = pick(prompt, ["文案", "README", "readme", "文档", "docs", "注释", "配置", "样式",
                         "css", "纯读", "审计", "分析", "排查", "调研", "方案", "讨论",
                         "咨询", "解释", "为什么", "搞清楚", "不要动代码", "不用修改",
                         "只读", "拼写", "typo", "措辞"])
risk_file = state_dir / f"{session_id}.risk"
risk = "HIGH" if high_trig else ("LOW" if low_trig else "MEDIUM")
risk_file.write_text(risk + "\n", encoding="utf-8")

try:
    current_state = state_file.read_text(encoding="utf-8").strip() or "INIT"
except FileNotFoundError:
    current_state = "INIT"

if design_trig or code_trig or high_trig:
    if current_state in {"INIT", "RELEASED"}:
        state_file.write_text("DESIGN_PENDING\n", encoding="utf-8")
        log(f"[design-test-loop] 检测到代码改动意图（关键字「{design_trig}{code_trig}{high_trig}」，风险={risk}）")
    elif current_state == "DESIGN_PENDING":
        log("[design-test-loop] 还在设计阶段，等 design-gate 三件套输出")

if test_trig:
    log(f"[design-test-loop] 测试关键字「{test_trig}」 -> 走 strict-prod-audit 一测 + 二测，再派 audit-verify 独立复测")
PY

exit 0
