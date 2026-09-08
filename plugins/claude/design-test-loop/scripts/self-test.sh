#!/usr/bin/env bash
# Smoke tests for design-test-loop hooks. Run before re-enabling the plugin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
TMP_DIR="$(mktemp -d)"
STATE_DIR="$TMP_DIR/state"
export WORKLIKERICO_DTL_STATE_DIR="$STATE_DIR"
SESSION_ID="dtl-selftest-$$"
STATE_FILE="${STATE_DIR}/${SESSION_ID}.state"

cleanup() {
    rm -f "$STATE_FILE" "${STATE_DIR}/${SESSION_ID}.risk"
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$STATE_DIR"

assert_eq() {
    local expected="$1"
    local actual="$2"
    local label="$3"
    if [ "$expected" != "$actual" ]; then
        printf 'FAIL: %s\nexpected: %s\nactual: %s\n' "$label" "$expected" "$actual" >&2
        exit 1
    fi
}

assert_empty_file() {
    local path="$1"
    local label="$2"
    if [ -s "$path" ]; then
        printf 'FAIL: %s should be empty\n' "$label" >&2
        cat "$path" >&2
        exit 1
    fi
}

assert_utf8_file() {
    local path="$1"
    python3 - "$path" <<'PY'
import pathlib
import sys

pathlib.Path(sys.argv[1]).read_bytes().decode("utf-8")
PY
}

USER_PROMPT_INPUT="{\"prompt\":\"修复并测试一个按钮问题\",\"cwd\":\"/tmp/worklikerico-selftest\",\"session_id\":\"${SESSION_ID}\"}"

# 1. UserPromptSubmit must be silent by default but still update state.
printf '%s\n' "$USER_PROMPT_INPUT" \
    | bash "${PLUGIN_DIR}/hooks/01-detect-intent.sh" \
        >"${TMP_DIR}/detect.out" 2>"${TMP_DIR}/detect.err"
assert_empty_file "${TMP_DIR}/detect.out" "detect stdout"
assert_empty_file "${TMP_DIR}/detect.err" "detect stderr"
assert_eq "DESIGN_PENDING" "$(cat "$STATE_FILE")" "detect state"

# 2. Verbose mode may print, but output must be valid UTF-8.
echo "INIT" > "$STATE_FILE"
printf '%s\n' "$USER_PROMPT_INPUT" \
    | DTL_VERBOSE=1 bash "${PLUGIN_DIR}/hooks/01-detect-intent.sh" \
        >"${TMP_DIR}/verbose.out" 2>"${TMP_DIR}/verbose.err"
assert_empty_file "${TMP_DIR}/verbose.out" "verbose stdout"
assert_utf8_file "${TMP_DIR}/verbose.err"

# 3. Disabled mode should do nothing.
rm -f "$STATE_FILE"
printf '%s\n' "$USER_PROMPT_INPUT" \
    | DTL_HOOKS_ENABLED=0 bash "${PLUGIN_DIR}/hooks/01-detect-intent.sh" \
        >"${TMP_DIR}/disabled.out" 2>"${TMP_DIR}/disabled.err"
assert_empty_file "${TMP_DIR}/disabled.out" "disabled stdout"
assert_empty_file "${TMP_DIR}/disabled.err" "disabled stderr"
if [ -e "$STATE_FILE" ]; then
    printf 'FAIL: disabled hook created state file\n' >&2
    exit 1
fi

# 4. Enforced design gate should block Edit in DESIGN_PENDING.
#    显式设 DTL_DESIGN_GATE_LEVEL=enforce，使本用例不受运行时环境（可能为 warn）干扰。
echo "DESIGN_PENDING" > "$STATE_FILE"
PRE_INPUT="{\"tool_name\":\"Edit\",\"session_id\":\"${SESSION_ID}\",\"transcript_path\":\"${TMP_DIR}/empty-transcript.jsonl\",\"tool_input\":{\"file_path\":\"/tmp/a.txt\"}}"
set +e
printf '%s\n' "$PRE_INPUT" \
    | DTL_GATE_LEVEL=enforce DTL_DESIGN_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/gate.out" 2>"${TMP_DIR}/gate.err"
gate_code=$?
set -e
assert_eq "2" "$gate_code" "gate exit code"
assert_empty_file "${TMP_DIR}/gate.out" "gate stdout"
grep -q '设计阶段' "${TMP_DIR}/gate.err"

# 4b. 分级门禁：DTL_GATE_LEVEL=enforce 但 DTL_DESIGN_GATE_LEVEL=warn 时，
#     设计门应放行(0)，而提交门仍应拦截(2)。这是无人值守方案的核心配置。
echo "DESIGN_PENDING" > "$STATE_FILE"
printf '%s\n' "$PRE_INPUT" \
    | DTL_GATE_LEVEL=enforce DTL_DESIGN_GATE_LEVEL=warn bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/split.out" 2>"${TMP_DIR}/split.err"
assert_empty_file "${TMP_DIR}/split.out" "split design-gate stdout"
assert_empty_file "${TMP_DIR}/split.err" "split design-gate stderr (warn 静默)"

# 4c. 续作误触发根因修复：低风险(RISK=LOW)软门放行 Edit 时，状态必须推进过设计门，
#     不能把 DESIGN_PENDING 留成"炸弹"（否则后续 risk 抬回 MEDIUM 会硬门误拦续作）。
#     注意：这里 DTL_DESIGN_GATE_LEVEL=enforce，靠 RISK=LOW 单独把有效级别降为 warn，验证降级路径会推进状态。
echo "DESIGN_PENDING" > "$STATE_FILE"
echo "LOW" > "${STATE_DIR}/${SESSION_ID}.risk"
set +e
printf '%s\n' "$PRE_INPUT" \
    | DTL_GATE_LEVEL=enforce DTL_DESIGN_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/lowadv.out" 2>"${TMP_DIR}/lowadv.err"
lowadv_code=$?
set -e
assert_eq "0" "$lowadv_code" "低风险软门应放行(exit 0)"
if [ "$(cat "$STATE_FILE")" = "DESIGN_PENDING" ]; then
    printf 'FAIL: 低风险软门后状态仍赖在 DESIGN_PENDING（炸弹未拆，续作会被误拦）\n' >&2
    exit 1
fi
assert_empty_file "${TMP_DIR}/lowadv.out" "low-advance stdout"
rm -f "${STATE_DIR}/${SESSION_ID}.risk"

# 5. Warn mode should not block and should stay silent unless DTL_VERBOSE=1.
#    显式设 DTL_DESIGN_GATE_LEVEL=warn 使本用例不受运行时环境（现默认 enforce）干扰。
printf '%s\n' "$PRE_INPUT" \
    | DTL_GATE_LEVEL=warn DTL_DESIGN_GATE_LEVEL=warn bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/warn.out" 2>"${TMP_DIR}/warn.err"
assert_empty_file "${TMP_DIR}/warn.out" "warn stdout"
assert_empty_file "${TMP_DIR}/warn.err" "warn stderr"

# 6. PostToolUse should update state silently.
echo "IMPL_SPEC_OK" > "$STATE_FILE"
POST_INPUT="{\"tool_name\":\"Edit\",\"session_id\":\"${SESSION_ID}\",\"tool_input\":{\"file_path\":\"/tmp/a.txt\"}}"
printf '%s\n' "$POST_INPUT" \
    | bash "${PLUGIN_DIR}/hooks/03-state-advance.sh" \
        >"${TMP_DIR}/post.out" 2>"${TMP_DIR}/post.err"
assert_empty_file "${TMP_DIR}/post.out" "post stdout"
assert_empty_file "${TMP_DIR}/post.err" "post stderr"
assert_eq "IMPL_IN_PROGRESS" "$(cat "$STATE_FILE")" "post state"

# 7. Gate-3a remove-ai-slop: block without clean marker (enforce), silent in warn, pass when marked.
echo "IMPL_IN_PROGRESS" > "$STATE_FILE"
: > "${TMP_DIR}/empty-transcript.jsonl"
COMMIT_INPUT="{\"tool_name\":\"Bash\",\"session_id\":\"${SESSION_ID}\",\"transcript_path\":\"${TMP_DIR}/empty-transcript.jsonl\",\"tool_input\":{\"command\":\"git commit -m x\"}}"
set +e
printf '%s\n' "$COMMIT_INPUT" \
    | DTL_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/slop.out" 2>"${TMP_DIR}/slop.err"
slop_code=$?
set -e
assert_eq "2" "$slop_code" "slop gate exit code"
assert_empty_file "${TMP_DIR}/slop.out" "slop stdout"
grep -q 'AI 痕迹' "${TMP_DIR}/slop.err"

printf '%s\n' "$COMMIT_INPUT" \
    | DTL_GATE_LEVEL=warn bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/slopwarn.out" 2>"${TMP_DIR}/slopwarn.err"
assert_empty_file "${TMP_DIR}/slopwarn.out" "slop warn stdout"
assert_empty_file "${TMP_DIR}/slopwarn.err" "slop warn stderr"

printf 'remove-ai-slop：已清理\n' > "${TMP_DIR}/clean-transcript.jsonl"
CLEAN_INPUT="{\"tool_name\":\"Bash\",\"session_id\":\"${SESSION_ID}\",\"transcript_path\":\"${TMP_DIR}/clean-transcript.jsonl\",\"tool_input\":{\"command\":\"git commit -m x\"}}"
set +e
printf '%s\n' "$CLEAN_INPUT" \
    | DTL_DISABLE_DOUBT_GATE=1 DTL_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/slopok.out" 2>"${TMP_DIR}/slopok.err"
slopok_code=$?
set -e
assert_eq "0" "$slopok_code" "slop gate pass when marked"

# 7b. 解耦验证：提交门不再依赖 IMPL 状态——DESIGN_PENDING 下 git commit 无清理标记也应拦截。
echo "DESIGN_PENDING" > "$STATE_FILE"
: > "${TMP_DIR}/empty-transcript.jsonl"
set +e
printf '%s\n' "$COMMIT_INPUT" \
    | DTL_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/decouple.out" 2>"${TMP_DIR}/decouple.err"
decouple_code=$?
set -e
assert_eq "2" "$decouple_code" "commit gate decoupled from IMPL state (DESIGN_PENDING 也拦)"

# 7c. Gate 3c lint 子门（代码标准化）：无 dispatch 入口 no-op；入口失败拦；入口通过放行。
echo "IMPL_IN_PROGRESS" > "$STATE_FILE"
printf 'remove-ai-slop：已清理\n' > "${TMP_DIR}/clean-transcript.jsonl"
LINT_PROJ="${TMP_DIR}/proj"
mkdir -p "${LINT_PROJ}/scripts"
# (a) 无入口 → no-op 放行（cwd 指向没有 dispatch 的目录；隔离 slop/doubt 门）
NOLINT_INPUT="{\"tool_name\":\"Bash\",\"session_id\":\"${SESSION_ID}\",\"cwd\":\"${TMP_DIR}\",\"transcript_path\":\"${TMP_DIR}/clean-transcript.jsonl\",\"tool_input\":{\"command\":\"git commit -m x\"}}"
set +e
printf '%s\n' "$NOLINT_INPUT" | DTL_DISABLE_SLOP_GATE=1 DTL_DISABLE_DOUBT_GATE=1 DTL_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" >/dev/null 2>&1
nolint_code=$?
set -e
assert_eq "0" "$nolint_code" "lint gate no-op when no dispatch entry"
# (b) 入口失败 → 拦截
printf '#!/usr/bin/env bash\nexit 1\n' > "${LINT_PROJ}/scripts/lint-staged-dispatch.sh"
LINT_INPUT="{\"tool_name\":\"Bash\",\"session_id\":\"${SESSION_ID}\",\"cwd\":\"${LINT_PROJ}\",\"transcript_path\":\"${TMP_DIR}/clean-transcript.jsonl\",\"tool_input\":{\"command\":\"git commit -m x\"}}"
set +e
printf '%s\n' "$LINT_INPUT" | DTL_DISABLE_SLOP_GATE=1 DTL_DISABLE_DOUBT_GATE=1 DTL_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" >/dev/null 2>&1
faillint_code=$?
set -e
assert_eq "2" "$faillint_code" "lint gate blocks when dispatch fails"
# (c) 入口通过 → 放行
printf '#!/usr/bin/env bash\nexit 0\n' > "${LINT_PROJ}/scripts/lint-staged-dispatch.sh"
set +e
printf '%s\n' "$LINT_INPUT" | DTL_DISABLE_SLOP_GATE=1 DTL_DISABLE_DOUBT_GATE=1 DTL_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" >/dev/null 2>&1
passlint_code=$?
set -e
assert_eq "0" "$passlint_code" "lint gate passes when dispatch ok"

# 8. 风险分档（2026-06-06）：低风险标记下，设计门即便 enforce 也应放行（降为软提示）。
echo "DESIGN_PENDING" > "$STATE_FILE"
echo "LOW" > "${STATE_DIR}/${SESSION_ID}.risk"
set +e
printf '%s\n' "$PRE_INPUT" \
    | DTL_GATE_LEVEL=enforce DTL_DESIGN_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/lowrisk.out" 2>"${TMP_DIR}/lowrisk.err"
lowrisk_code=$?
set -e
assert_eq "0" "$lowrisk_code" "low-risk design gate passes even under enforce"
assert_empty_file "${TMP_DIR}/lowrisk.out" "low-risk stdout"

# 8b. 高风险标记下，设计门 enforce 仍应硬拦（计费安全网不被风险分档削弱）。
echo "DESIGN_PENDING" > "$STATE_FILE"
echo "HIGH" > "${STATE_DIR}/${SESSION_ID}.risk"
set +e
printf '%s\n' "$PRE_INPUT" \
    | DTL_GATE_LEVEL=enforce DTL_DESIGN_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >/dev/null 2>"${TMP_DIR}/highrisk.err"
highrisk_code=$?
set -e
assert_eq "2" "$highrisk_code" "high-risk design gate still blocks under enforce"

# 8c. 风险分档不影响发布门：低风险也不能绕过"发布前必过二测"。
echo "T1_PASS" > "$STATE_FILE"
echo "LOW" > "${STATE_DIR}/${SESSION_ID}.risk"
RELEASE_INPUT="{\"tool_name\":\"Bash\",\"session_id\":\"${SESSION_ID}\",\"transcript_path\":\"${TMP_DIR}/empty-transcript.jsonl\",\"tool_input\":{\"command\":\"bash deploy/update.sh\"}}"
: > "${TMP_DIR}/empty-transcript.jsonl"
set +e
printf '%s\n' "$RELEASE_INPUT" \
    | DTL_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >/dev/null 2>"${TMP_DIR}/release.err"
release_code=$?
set -e
assert_eq "2" "$release_code" "release gate still enforces even for low-risk"
rm -f "${STATE_DIR}/${SESSION_ID}.risk"

# 8d. detect-intent：项目目录 + 纯读 prompt（无代码意图词）→ 不进 DESIGN_PENDING（project_trig 已移除），且标 LOW。
rm -f "$STATE_FILE" "${STATE_DIR}/${SESSION_ID}.risk"
READ_INPUT="{\"prompt\":\"分析一下这个目录\",\"cwd\":\"/tmp/worklikerico-readonly\",\"session_id\":\"${SESSION_ID}\"}"
printf '%s\n' "$READ_INPUT" | bash "${PLUGIN_DIR}/hooks/01-detect-intent.sh" >/dev/null 2>&1
if [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE")" = "DESIGN_PENDING" ]; then
    printf 'FAIL: 项目目录下的纯读 prompt 不应进入 DESIGN_PENDING\n' >&2
    exit 1
fi
assert_eq "LOW" "$(cat "${STATE_DIR}/${SESSION_ID}.risk" 2>/dev/null)" "纯读 prompt 应标记为 LOW 风险"

# 8e. 方案/讨论类 prompt 不应进入 DESIGN_PENDING，且标 LOW，避免普通咨询走重实现门。
rm -f "$STATE_FILE" "${STATE_DIR}/${SESSION_ID}.risk"
PLAN_INPUT="{\"prompt\":\"关于整体方案的制定我存在疑问，这个会话不要动代码，只讨论为什么没有达到预期\",\"cwd\":\"/tmp/worklikerico-plan\",\"session_id\":\"${SESSION_ID}\"}"
printf '%s\n' "$PLAN_INPUT" | bash "${PLUGIN_DIR}/hooks/01-detect-intent.sh" >/dev/null 2>&1
if [ -f "$STATE_FILE" ] && [ "$(cat "$STATE_FILE")" = "DESIGN_PENDING" ]; then
    printf 'FAIL: 方案讨论 prompt 不应进入 DESIGN_PENDING\n' >&2
    exit 1
fi
assert_eq "LOW" "$(cat "${STATE_DIR}/${SESSION_ID}.risk" 2>/dev/null)" "方案讨论 prompt 应标记为 LOW 风险"

# 9. PM 工作包设计门：无需工程三件套，只要工作包/RACI/并行/验收/阻塞齐，就通过 Gate-1。
echo "DESIGN_PENDING" > "$STATE_FILE"
cat > "${TMP_DIR}/pm-transcript.jsonl" <<'EOF'
{"type":"assistant","message":{"content":[{"type":"text","text":"PM 工作包设计门：\n工作包/任务卡：每个 work package 都写输入、输出、交付物。\nRACI/DRI/岗位负责人：产品负责人负责验收，后端子 agent 执行，QA agent 审查。\n并行泳道与依赖：A 可并行，B 依赖 A 解锁，C 串行避免冲突。\n验收标准 / Done 定义：每个工作包必须有可验证断言和证据。\n未决决策 / 阻塞条件 / 风险升级：涉及凭据和生产发布需要 Rico 拍板。"}]}}}
EOF
PM_INPUT="{\"tool_name\":\"Edit\",\"session_id\":\"${SESSION_ID}\",\"transcript_path\":\"${TMP_DIR}/pm-transcript.jsonl\",\"tool_input\":{\"file_path\":\"/tmp/a.txt\"}}"
set +e
printf '%s\n' "$PM_INPUT" \
    | DTL_DISABLE_SPEC_GATE=1 DTL_GATE_LEVEL=enforce DTL_DESIGN_GATE_LEVEL=enforce bash "${PLUGIN_DIR}/hooks/02-gate-check.sh" \
        >"${TMP_DIR}/pmgate.out" 2>"${TMP_DIR}/pmgate.err"
pmgate_code=$?
set -e
assert_eq "0" "$pmgate_code" "PM work-package design gate should pass Gate-1"
assert_eq "DESIGN_DONE" "$(cat "$STATE_FILE")" "PM work-package design gate should advance state"

printf 'design-test-loop self-test OK\n'
