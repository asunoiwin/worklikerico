#!/usr/bin/env bash
# PostToolUse hook：状态机推进
#
# 路径：
#   INIT / DESIGN_DONE / IMPL_SPEC_OK → IMPL_IN_PROGRESS（首次 Edit/Write 完成）
#     INIT 也纳入：没命中设计关键词的活会停在 INIT，过去 Stop 门据此判"没开工"而装睡。
#     动手即在途——首次改文件就点火，堵掉这个盲区。低/中/高风险的轻重由 Stop 门按 .risk 分档。
#   IMPL_IN_PROGRESS → IMPL_DONE（git commit 检测到）
#   IMPL_DONE → T1_PASS（一测 agent 派发）
#   T1_PASS → T2_PASS（独立二测 agent 派发）
#   T2_PASS → AUDIT_PASS（audit-verify 派发）
#   AUDIT_PASS → RELEASED（update.sh / release 命令）

set -e

[ "${DTL_HOOKS_ENABLED:-1}" = "1" ] || exit 0

log() {
    if [ "${DTL_VERBOSE:-0}" = "1" ]; then
        printf '%s\n' "$*" >&2
    fi
    return 0
}

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('tool_name',''))" 2>/dev/null || echo "")
SESSION_ID=$(echo "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('session_id',''))" 2>/dev/null || echo "default")
TOOL_INPUT_RAW=$(echo "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(json.dumps(d.get('tool_input',{})))" 2>/dev/null || echo "{}")
TRANSCRIPT_PATH=$(echo "$INPUT" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('transcript_path',''))" 2>/dev/null || echo "")

STATE_DIR="${WORKLIKERICO_DTL_STATE_DIR:-$HOME/.codex/state/design-test-loop}"
STATE_FILE="$STATE_DIR/${SESSION_ID}.state"

CURRENT_STATE=$(cat "$STATE_FILE" 2>/dev/null || echo "INIT")

case "$CURRENT_STATE" in
    INIT|DESIGN_DONE|IMPL_SPEC_OK)
        # 首次 Edit/Write 通过 → 进入实现状态（INIT 见文件头说明：动手即在途）
        case "$TOOL_NAME" in
            Edit|Write|NotebookEdit|apply_patch|functions.apply_patch)
                echo "IMPL_IN_PROGRESS" > "$STATE_FILE"
                log "[design-test-loop] 进入实现阶段"
                ;;
        esac
        ;;
    IMPL_IN_PROGRESS)
        # 检测 git commit
        if [[ "$TOOL_NAME" =~ ^(Bash|exec_command|functions\.exec_command)$ ]]; then
            CMD=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('command') or d.get('cmd') or '')" 2>/dev/null || echo "")
            if echo "$CMD" | grep -qE 'git\s+commit'; then
                echo "IMPL_DONE" > "$STATE_FILE"
                log "[design-test-loop] commit 完成，下一步跑一测（参考 strict-prod-audit skill）"
            fi
        fi
        ;;
    IMPL_DONE)
        # 一测 agent 完成（Agent tool 调用 + subagent_type 含 test/audit/playwright）
        if [[ "$TOOL_NAME" =~ ^(Agent|spawn_agent|multi_agent_v1\.spawn_agent)$ ]]; then
            SUBAGENT=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;d=json.load(sys.stdin);print(str(d.get('subagent_type') or d.get('agent_type') or '')+' '+str(d.get('description') or d.get('message') or ''))" 2>/dev/null || echo "")
            if echo "$SUBAGENT" | grep -qiE 'test|playwright|一测|devtools'; then
                echo "T1_PASS" > "$STATE_FILE"
                log "[design-test-loop] 一测 agent 已派发，接下来派独立二测（不同 instance + 不读一测报告）"
            fi
        fi
        ;;
    T1_PASS)
        if [[ "$TOOL_NAME" =~ ^(Agent|spawn_agent|multi_agent_v1\.spawn_agent)$ ]]; then
            SUBAGENT=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;d=json.load(sys.stdin);print(str(d.get('subagent_type') or d.get('agent_type') or '')+' '+str(d.get('description') or d.get('message') or ''))" 2>/dev/null || echo "")
            if echo "$SUBAGENT" | grep -qiE 'prod|二测|playwright-audit'; then
                echo "T2_PASS" > "$STATE_FILE"
                log "[design-test-loop] 二测 agent 已派发，下一步派 audit-verify 独立审计"
            fi
        fi
        ;;
    T2_PASS)
        if [[ "$TOOL_NAME" =~ ^(Agent|spawn_agent|multi_agent_v1\.spawn_agent)$ ]]; then
            SUBAGENT=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;d=json.load(sys.stdin);print(str(d.get('subagent_type') or d.get('agent_type') or '')+' '+str(d.get('description') or d.get('message') or ''))" 2>/dev/null || echo "")
            if echo "$SUBAGENT" | grep -qiE 'audit|verify|复测'; then
                echo "AUDIT_PASS" > "$STATE_FILE"
                log "[design-test-loop] audit-verify 已派发，可以发布了"
            fi
        fi
        ;;
    AUDIT_PASS)
        # 软警告：检查会话是否沉淀决策和 ADR（不阻塞）
        SESSION_TRANSCRIPT="$TRANSCRIPT_PATH"
        if [ -f "$SESSION_TRANSCRIPT" ]; then
            HAS_ADR=$(grep -c 'manage_adr' "$SESSION_TRANSCRIPT" 2>/dev/null | tr -d '[:space:]' || echo "0")
            HAS_DECISION=$(grep -cE 'category=decision|"category":\s*"decision"' "$SESSION_TRANSCRIPT" 2>/dev/null | tr -d '[:space:]' || echo "0")
            if [ "$HAS_ADR" -eq 0 ] && [ "$HAS_DECISION" -eq 0 ]; then
                log "[design-test-loop] 软提醒：本次还没写 ADR 也没存决策记忆，发布前建议补一下（manage_adr / memory_store category=decision）"
            elif [ "$HAS_ADR" -eq 0 ]; then
                log "[design-test-loop] 软提醒：没写 ADR，建议补一下"
            elif [ "$HAS_DECISION" -eq 0 ]; then
                log "[design-test-loop] 软提醒：没存决策记忆（category=decision），建议补一下"
            fi
        fi
        # 检测发布命令
        if [[ "$TOOL_NAME" =~ ^(Bash|exec_command|functions\.exec_command)$ ]]; then
            CMD=$(echo "$TOOL_INPUT_RAW" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('command') or d.get('cmd') or '')" 2>/dev/null || echo "")
            if echo "$CMD" | grep -qE 'update\.sh|gh release|git tag'; then
                echo "RELEASED" > "$STATE_FILE"
                log "[design-test-loop] 发布完成"
            fi
        fi
        ;;
esac

exit 0
