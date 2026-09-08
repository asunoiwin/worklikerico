#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STOP="$ROOT/hooks/03-subagent-stop.sh"
RESULT="$ROOT/hooks/02-result-guard.sh"
TMP="$(mktemp -d)"

run_case() {
  local expected="$1" script="$2" input="$3" name="$4"
  set +e
  printf '%s' "$input" | bash "$script" >"$TMP/out" 2>"$TMP/err"
  local actual=$?
  set -e
  if [ "$actual" -ne "$expected" ]; then
    printf 'FAIL %s expected=%s actual=%s\n' "$name" "$expected" "$actual" >&2
    cat "$TMP/err" >&2
    exit 1
  fi
}

run_case 0 "$STOP" '{"hook_event_name":"SubagentStop","reason":"completed; risks mention failed blocked timeout but subtask is done"}' "completed reason wins"
run_case 0 "$STOP" '{"hook_event_name":"SubagentStop","status":"completed","diagnostics":{"status":"error","log":"timeout"}}' "nested error ignored"
run_case 0 "$STOP" '{"hook_event_name":"SubagentStop","reason":{"status":"success","details":"blocked word in risk"}}' "reason status success"
run_case 2 "$STOP" '{"hook_event_name":"SubagentStop","reason":{"status":"failed","details":"worker crashed"}}' "real failure"
run_case 2 "$STOP" '{"hook_event_name":"SubagentStop","agent_status":"timeout"}' "real timeout"
run_case 0 "$STOP" '{"hook_event_name":"SubagentStop","agent_status":"cancelled"}' "cancelled stops quietly"
[ ! -s "$TMP/err" ] || { echo "FAIL cancelled triggered recovery output" >&2; cat "$TMP/err" >&2; exit 1; }
run_case 0 "$STOP" '{"hook_event_name":"SubagentStop","reason":{"status":"canceled","details":"user requested stop"}}' "canceled stops quietly"
[ ! -s "$TMP/err" ] || { echo "FAIL canceled triggered recovery output" >&2; cat "$TMP/err" >&2; exit 1; }
run_case 0 "$STOP" '{"hook_event_name":"SubagentStop","diagnostics":{"status":"error"}}' "missing status safe"
run_case 0 "$STOP" '{broken json' "malformed safe"
run_case 0 "$STOP" '{"hook_event_name":"SubagentStop","reason":"completed; overall goal incomplete"}' "subtask versus total goal"

run_case 0 "$RESULT" '{"hook_event_name":"PostToolUse","tool_name":"wait_agent","tool_result":"waiting; no mailbox update"}' "wait progress needs no handoff"
run_case 0 "$RESULT" '{"hook_event_name":"PostToolUse","tool_name":"claude_tail","tool_result":"ordinary progress"}' "tail progress needs no handoff"
run_case 2 "$RESULT" '{"hook_event_name":"PostToolUse","tool_name":"claude_result","tool_result":"finished without summary"}' "terminal result requires handoff"
run_case 0 "$RESULT" '{"hook_event_name":"PostToolUse","tool_name":"claude_result","tool_result":"## Handoff\n- Status: completed"}' "terminal handoff accepted"
run_case 0 "$RESULT" '{broken json' "malformed result safe"

echo "codex-multi-agent hook tests OK"
