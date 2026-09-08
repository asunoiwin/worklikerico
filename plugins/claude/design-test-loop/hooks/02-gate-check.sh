#!/usr/bin/env bash
# PreToolUse hook：拦截 Edit/Write/Bash 工具调用
#
# 状态机 + 4 个 sub-gate：
#   1. DESIGN_PENDING + Edit/Write → 阻塞（要求 design-gate 三件套）
#   2. DESIGN_DONE + Edit/Write    → 检查 spec-first 5 段 → 通过则推进 IMPL_SPEC_OK
#   3. IMPL_*  + Bash(git commit)  → 检查 doubt-review 自审 → 通过才放行 commit
#   4. T1_PASS/T2_PASS + Bash(release) → 阻塞（必先派后续 agent）
#
# 灰度开关（env）：
#   DTL_GATE_LEVEL=warn      → 全部 sub-gate 只警告不阻塞
#   DTL_DISABLE_SPEC_GATE=1  → 关掉 spec-first 检查
#   DTL_DISABLE_DOUBT_GATE=1 → 关掉 doubt-review 检查

set -e

[ "${DTL_HOOKS_ENABLED:-1}" = "1" ] || exit 0

log() {
    if [ "${DTL_VERBOSE:-0}" = "1" ]; then
        printf '%s\n' "$*" >&2
    fi
    return 0
}

read -r INPUT

TOOL_NAME=$(echo "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('tool_name',''))" 2>/dev/null || echo "")
SESSION_ID=$(echo "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('session_id',''))" 2>/dev/null || echo "default")
TRANSCRIPT_PATH=$(echo "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('transcript_path',''))" 2>/dev/null || echo "")
TOOL_INPUT_RAW=$(echo "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(json.dumps(d.get('tool_input',{})))" 2>/dev/null || echo "{}")

STATE_DIR="${WORKLIKERICO_DTL_STATE_DIR:-$HOME/.claude/state/design-test-loop}"
STATE_FILE="$STATE_DIR/${SESSION_ID}.state"
CURRENT_STATE=$(cat "$STATE_FILE" 2>/dev/null || echo "INIT")

# 灰度模式：把所有阻塞改为软警告
GATE_LEVEL="${DTL_GATE_LEVEL:-enforce}"
# 设计门可单独设级别（默认跟随 GATE_LEVEL）。分级灰度：提交/发布门转 enforce，设计门留 warn。
DESIGN_GATE_LEVEL="${DTL_DESIGN_GATE_LEVEL:-$GATE_LEVEL}"

# 风险分档（2026-06-06）：低风险改动（文案/配置/UI/纯读）把设计门+spec门降为软提示，
# 提交门(slop/doubt/lint)和发布门(二测+audit)一律不放宽。判不出=中风险(enforce)，安全兜底。
RISK=$(cat "$STATE_DIR/${SESSION_ID}.risk" 2>/dev/null || echo "MEDIUM")
[ -n "${DTL_FORCE_RISK:-}" ] && RISK=$(printf '%s' "$DTL_FORCE_RISK" | tr '[:lower:]' '[:upper:]')
EFFECTIVE_DESIGN_LEVEL="$DESIGN_GATE_LEVEL"
[ "$RISK" = "LOW" ] && EFFECTIVE_DESIGN_LEVEL="warn"
fail_or_warn() {
    local lvl="${2:-$GATE_LEVEL}"
    if [ "$lvl" = "warn" ]; then
        log "[design-test-loop: 软警告] $1"
        exit 0
    else
        echo "$1" >&2
        exit 2
    fi
}

# ============================================================
# Gate 4: release 前必须完成后续测试 agent
# ============================================================
if [ "$TOOL_NAME" = "Bash" ] && { [ "$CURRENT_STATE" = "T1_PASS" ] || [ "$CURRENT_STATE" = "T2_PASS" ]; }; then
    CMD=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;print(json.load(sys.stdin).get('command',''))" 2>/dev/null || echo "")
    if echo "$CMD" | grep -qE 'update\.sh|gh release|git tag|git push.*--tags'; then
        if [ "$CURRENT_STATE" = "T1_PASS" ]; then
            MISSING="二测（独立 playwright-audit agent）"
            NEXT='Agent(subagent_type="playwright-audit") — 不同 instance、不读一测报告，独立复现一测预期清单'
            BYPASS="T2_PASS"
        else
            MISSING="audit-verify（独立第三 agent）"
            NEXT='Agent(subagent_type="audit-verify") — 独立设计 3 个测试用例对照一测预期'
            BYPASS="AUDIT_PASS"
        fi
        fail_or_warn "$(cat <<EOF
[design-test-loop: 发布命令被拦截]

现在的阶段是 ${CURRENT_STATE}，还没跑 ${MISSING}。
拦下来的命令开头：$(printf '%s' "$CMD" | python3 -c "import sys;print(sys.stdin.read()[:80])" 2>/dev/null)

要做什么：
  ${NEXT}
完成后状态会自动推进，再跑发布命令就放行。

紧急绕过（必须在对话写明理由）：
  echo ${BYPASS} > ${STATE_FILE}
EOF
)"
    fi
fi

# ============================================================
# Gate 3a: commit 前先清 AI 痕迹（remove-ai-slop）
# ============================================================
if [ "$TOOL_NAME" = "Bash" ] && [ "$DTL_DISABLE_SLOP_GATE" != "1" ]; then
    CMD=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;print(json.load(sys.stdin).get('command',''))" 2>/dev/null || echo "")
    # 解耦：任何 git commit 都查清屎山（不再依赖设计门推进的状态，避免设计门 warn 时整条旁路）
    if echo "$CMD" | grep -qE '^\s*git\s+commit\b'; then

        HAS_SLOP_CLEAN=0
        if [ -f "$TRANSCRIPT_PATH" ] && \
           grep -qiE "remove-ai-slop[：:].{0,16}(已清理|清理完成|无 ?slop|no slop|cleaned)" "$TRANSCRIPT_PATH" 2>/dev/null; then
            HAS_SLOP_CLEAN=1
        fi

        if [ "$HAS_SLOP_CLEAN" = "0" ]; then
            fail_or_warn "$(cat <<'EOF'
[design-test-loop: git commit 被拦截 — 还没清 AI 痕迹]

commit 前要先清一遍本次改动里的 slop（冗余注释 / 过度防御 / 单次变量 / 风格不一致），
再做 doubt-review 自审。顺序：清理 → 自审 → commit。
要先调 remove-ai-slop skill，按它的边界只清本次 diff，结尾带标记：
  remove-ai-slop：已清理（或：本次改动无 slop 可清）

详见 remove-ai-slop skill。

紧急绕过：DTL_DISABLE_SLOP_GATE=1 git commit ...
EOF
)"
        fi
    fi
fi

# ============================================================
# Gate 3: commit 前自审（doubt-review）
# ============================================================
if [ "$TOOL_NAME" = "Bash" ] && [ "$DTL_DISABLE_DOUBT_GATE" != "1" ]; then
    CMD=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;print(json.load(sys.stdin).get('command',''))" 2>/dev/null || echo "")
    # 解耦：任何 git commit 都查 doubt-review（不再依赖设计门推进的状态，避免设计门 warn 时整条旁路）
    if echo "$CMD" | grep -qE '^\s*git\s+commit\b'; then

        HAS_DOUBT=0
        # 识别方式 1：明确标记 "doubt-review：提交前自审"
        # 识别方式 2：同时出现 CLAIM + DOUBT + RECONCILE（中/英）
        # 三个正则各自独立判断（合并成一个大正则会在 BSD grep 触发灾难性回溯）
        if [ -f "$TRANSCRIPT_PATH" ] && \
           { grep -qiE "doubt-review[：:].{0,12}(提交前自审|self.?review|commit.?gate)" "$TRANSCRIPT_PATH" 2>/dev/null \
          || grep -qiE "CLAIM[^a-z].{0,250}DOUBT[^a-z].{0,250}RECONCILE" "$TRANSCRIPT_PATH" 2>/dev/null \
          || grep -qiE "改了啥.{0,250}怀疑点.{0,250}(怎么解|回滚)" "$TRANSCRIPT_PATH" 2>/dev/null; }; then
            HAS_DOUBT=1
        fi

        if [ "$HAS_DOUBT" = "0" ]; then
            fail_or_warn "$(cat <<'EOF'
[design-test-loop: git commit 被拦截]

写完代码直接 commit 会跳过自审，这是一测翻车的最大来源。
要先在主对话输出 doubt-review 四段：
  - CLAIM（改了啥，1 句话）
  - EXTRACT（关键改动点 2-4 条）
  - DOUBT（怀疑点 3 个，必须用"如果...会怎样"句式）
  - RECONCILE（每个怀疑点的回应：已处理 / 需测覆盖 / 接受残留）

详见 doubt-review skill。

紧急绕过：DTL_DISABLE_DOUBT_GATE=1 git commit ...
EOF
)"
        fi
        # doubt 通过，让后续推进逻辑跑（不在这里改状态）
    fi
fi

# ============================================================
# Gate 3c: commit 前过 lint（代码标准化）
# 控制逻辑全局化、质量标准项目化：本门只负责"去项目找 lint 入口并强制"，
# 具体规则由各项目的 scripts/lint-staged-dispatch.sh 实现（按 staged diff 派发）。
# 项目没接 lint 入口时优雅 no-op，不影响未接入项目。
# ============================================================
if [ "$TOOL_NAME" = "Bash" ] && [ "$DTL_DISABLE_LINT_GATE" != "1" ]; then
    CMD=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;print(json.load(sys.stdin).get('command',''))" 2>/dev/null || echo "")
    if echo "$CMD" | grep -qE '^\s*git\s+commit\b'; then
        PROJ_CWD=$(echo "$INPUT" | python3 -c "import json,sys;print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || echo "")
        [ -z "$PROJ_CWD" ] && PROJ_CWD="$(pwd)"
        DISPATCH="$PROJ_CWD/scripts/lint-staged-dispatch.sh"
        if [ -f "$DISPATCH" ]; then
            if ! ( cd "$PROJ_CWD" && bash "$DISPATCH" ); then
                fail_or_warn "$(cat <<'EOF'
[design-test-loop: git commit 被拦截 — lint 没过（代码标准化）]

本次暂存改动没通过项目 lint（前端 eslint/stylelint/prettier 或后端 spotless/checkstyle / 架构规则）。
只检查本次暂存 diff，不碰存量。按上面 linter 的提示修掉再 commit。

紧急绕过：DTL_DISABLE_LINT_GATE=1 git commit ...
EOF
)"
            fi
        fi
        # 无 dispatch 入口 → no-op（项目尚未接入 lint 基线）
    fi
fi

# ============================================================
# Gate 1+2: Edit/Write 路径
# ============================================================
case "$TOOL_NAME" in
    Edit|Write|NotebookEdit) ;;
    *) exit 0 ;;
esac

# ----- Gate 1: DESIGN_PENDING 必须完成 design-gate -----
if [ "$CURRENT_STATE" = "DESIGN_PENDING" ]; then
    HAS_BLAST=0
    HAS_GREP=0
    HAS_DOUBLE_FACE=0
    HAS_PM_WORK=0
    HAS_PM_OWNER=0
    HAS_PM_PARALLEL=0
    HAS_PM_ACCEPT=0
    HAS_PM_BLOCK=0

    if [ -f "$TRANSCRIPT_PATH" ]; then
        HAS_BLAST=0; grep -q -iE "(blast.?radius|影响面|爆炸半径).{0,30}(五元|清单|分析|评估|breakdown|analysis|checklist)" "$TRANSCRIPT_PATH" 2>/dev/null && HAS_BLAST=1
        HAS_GREP=0; grep -q -iE "(已修.{0,3}未修.{0,3}不需修)|(已修/未修/不需修)|(fixed.{0,3}pending.{0,3}(skip|n/?a))|(grep 同.{0,3}pattern)" "$TRANSCRIPT_PATH" 2>/dev/null && HAS_GREP=1
        HAS_DOUBLE_FACE=0; grep -q -iE "(用户面|admin 面|双面影响|admin/.{0,5}user|admin\\s*\\+\\s*user|user-?side.{0,10}admin-?side|前端.{0,8}影响.{0,30}后端.{0,8}影响|后端.{0,8}影响.{0,30}前端.{0,8}影响)" "$TRANSCRIPT_PATH" 2>/dev/null && HAS_DOUBLE_FACE=1

        # PM design gate: for project-manager style planning before code, accept a dispatchable
        # work system instead of the engineering-only design-gate triplet.
        HAS_PM_WORK=0; grep -q -iE "(工作包|任务卡|work package|workstream).{0,80}(输入|输出|产出|交付物|任务)" "$TRANSCRIPT_PATH" 2>/dev/null && HAS_PM_WORK=1
        HAS_PM_OWNER=0; grep -q -iE "(RACI|DRI|负责人|责任人|岗位|子 ?agent|owner).{0,80}(负责|执行|审查|验收|拍板|分工)" "$TRANSCRIPT_PATH" 2>/dev/null && HAS_PM_OWNER=1
        HAS_PM_PARALLEL=0; grep -q -iE "(并行|泳道|parallel|依赖|前置).{0,100}(可并行|串行|依赖|阻塞|解锁|先后)" "$TRANSCRIPT_PATH" 2>/dev/null && HAS_PM_PARALLEL=1
        HAS_PM_ACCEPT=0; grep -q -iE "(验收标准|Done 定义|done definition|完成定义|验收口|可验证).{0,100}(通过|断言|证据|标准|条件)" "$TRANSCRIPT_PATH" 2>/dev/null && HAS_PM_ACCEPT=1
        HAS_PM_BLOCK=0; grep -q -iE "(未决决策|开放问题|阻塞条件|风险升级|升级条件|需要.*拍板|blocker).{0,100}(决策|阻塞|升级|拍板|风险|条件)" "$TRANSCRIPT_PATH" 2>/dev/null && HAS_PM_BLOCK=1
    fi

    if { [ "$HAS_BLAST" -gt 0 ] && [ "$HAS_GREP" -gt 0 ] && [ "$HAS_DOUBLE_FACE" -gt 0 ]; } || \
       { [ "$HAS_PM_WORK" -gt 0 ] && [ "$HAS_PM_OWNER" -gt 0 ] && [ "$HAS_PM_PARALLEL" -gt 0 ] && [ "$HAS_PM_ACCEPT" -gt 0 ] && [ "$HAS_PM_BLOCK" -gt 0 ]; }; then
        echo "DESIGN_DONE" > "$STATE_FILE"
        log "[design-test-loop] 设计阶段通过：工程设计三件套或 PM 工作包设计门已齐"
        # 不 exit 0，让下面 spec-first gate 也跑一次
        CURRENT_STATE="DESIGN_DONE"
    else
        MISSING=""
        if ! { [ "$HAS_BLAST" -gt 0 ] && [ "$HAS_GREP" -gt 0 ] && [ "$HAS_DOUBLE_FACE" -gt 0 ]; }; then
            MISSING="${MISSING}\n  工程设计门可选路径缺："
            [ "$HAS_BLAST" = "0" ] && MISSING="${MISSING}\n    - 影响面五元清单（后端/DB/接口/前端/配置 各扫一遍）"
            [ "$HAS_GREP" = "0" ] && MISSING="${MISSING}\n    - 同义词扫描三栏（已修/未修/不需修+理由）"
            [ "$HAS_DOUBLE_FACE" = "0" ] && MISSING="${MISSING}\n    - 双面影响声明（用户面 / admin 面 / DB 影响）"
        fi
        if ! { [ "$HAS_PM_WORK" -gt 0 ] && [ "$HAS_PM_OWNER" -gt 0 ] && [ "$HAS_PM_PARALLEL" -gt 0 ] && [ "$HAS_PM_ACCEPT" -gt 0 ] && [ "$HAS_PM_BLOCK" -gt 0 ]; }; then
            MISSING="${MISSING}\n  PM 工作包设计门可选路径缺："
            [ "$HAS_PM_WORK" = "0" ] && MISSING="${MISSING}\n    - 工作包/任务卡（每包输入、输出、交付物）"
            [ "$HAS_PM_OWNER" = "0" ] && MISSING="${MISSING}\n    - RACI/DRI/岗位负责人（谁执行、谁审查、谁验收）"
            [ "$HAS_PM_PARALLEL" = "0" ] && MISSING="${MISSING}\n    - 并行泳道与依赖（哪些可并行、哪些前置/阻塞）"
            [ "$HAS_PM_ACCEPT" = "0" ] && MISSING="${MISSING}\n    - 验收标准 / Done 定义（可验证断言和证据）"
            [ "$HAS_PM_BLOCK" = "0" ] && MISSING="${MISSING}\n    - 未决决策 / 阻塞条件 / 风险升级口"
        fi
        if [ "$EFFECTIVE_DESIGN_LEVEL" = "warn" ]; then
            # 软门（低风险）：放行的同时把状态推进过设计门，绝不把 DESIGN_PENDING 留成"待办炸弹"。
            # 否则后续某条消息措辞没命中 low 关键词、risk 被重算成 MEDIUM 时，赖在原地的
            # DESIGN_PENDING 会突然变硬门，误拦同一摊活的续作 Edit（续作误触发根因，2026-06-26 修）。
            echo "DESIGN_DONE" > "$STATE_FILE"
            CURRENT_STATE="DESIGN_DONE"
            log "[design-test-loop: 软警告] 低风险跳过设计门，状态推进到 DESIGN_DONE（防后续 risk 抬档误拦续作）"
        else
            fail_or_warn "$(cat <<EOF
[design-test-loop: $TOOL_NAME 被拦截 — 设计阶段没过]

需求关键字触发了 design-gate。现在支持两条过门路径：工程设计三件套，或 PM 工作包设计门。当前还缺：${MISSING}

要做什么：调 design-gate skill 输出工程三件套；如果这是项目经理/方案编排类任务，则输出 PM 工作包设计门五件套。
紧急绕过：echo DESIGN_DONE > ${STATE_FILE}
EOF
)" "$EFFECTIVE_DESIGN_LEVEL"
        fi
    fi
fi

# ----- Gate 2: DESIGN_DONE 首次 Edit 前必须输出 spec-first -----
if [ "$CURRENT_STATE" = "DESIGN_DONE" ] && [ "$DTL_DISABLE_SPEC_GATE" != "1" ]; then
    HAS_SPEC=0
    if [ -f "$TRANSCRIPT_PATH" ]; then
        # 识别方式 1：明确标记 "spec-first：实现前对齐"
        SM_MARK=0; grep -q -iE "spec-first[：:].{0,12}(实现前|对齐|spec.?gate)" "$TRANSCRIPT_PATH" 2>/dev/null && SM_MARK=1
        # 识别方式 2：5 段关键字全齐（目标 + 产出物 + 边界 + 测试标准 + 影响面）
        SM_5SECTIONS=0; grep -q -iE "目标.{0,250}产出物.{0,250}边界.{0,250}测试标准.{0,250}影响面" "$TRANSCRIPT_PATH" 2>/dev/null && SM_5SECTIONS=1
        if [ "$SM_MARK" -gt 0 ] || [ "$SM_5SECTIONS" -gt 0 ]; then
            HAS_SPEC=1
        fi
    fi

    if [ "$HAS_SPEC" = "1" ]; then
        echo "IMPL_SPEC_OK" > "$STATE_FILE"
        log "[design-test-loop] 实现前 spec-first 5 段已齐，放行写代码"
        exit 0
    elif [ "$EFFECTIVE_DESIGN_LEVEL" = "warn" ]; then
        # 软门（低风险）：同理推进过 spec 门，不把 DESIGN_DONE 留成炸弹。
        echo "IMPL_SPEC_OK" > "$STATE_FILE"
        log "[design-test-loop: 软警告] 低风险跳过 spec 门，状态推进到 IMPL_SPEC_OK（防后续误拦）"
        exit 0
    else
        fail_or_warn "$(cat <<'EOF'
[design-test-loop: 写代码前要先写 spec-first 5 段]

设计阶段过了，但还没说清楚这一手要落到哪里。
要先在主对话输出 spec-first 5 段：
  1. 目标（一句话讲解决什么问题）
  2. 产出物（具体改哪些文件 / 新增什么）
  3. 边界（明确不做什么，≥3 条）
  4. 测试标准（可验证的断言，≥2 条）
  5. 影响面（核心路径上 1-2 个最重要的连带）

详见 spec-first skill。

紧急绕过（开发新插件等场景）：DTL_DISABLE_SPEC_GATE=1
或本次跳过：echo IMPL_SPEC_OK > ${STATE_FILE}
EOF
)" "$EFFECTIVE_DESIGN_LEVEL"
    fi
fi

# 其他状态（IMPL_SPEC_OK / IMPL_IN_PROGRESS / IMPL_DONE / T1_PASS 等）放行 Edit/Write
exit 0
