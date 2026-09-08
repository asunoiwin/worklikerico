#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
DECISION=$(HOOK_INPUT="$INPUT" python3 <<'PY'
import json
import os
import re

raw = os.environ.get("HOOK_INPUT", "")
try:
    payload = json.loads(raw)
except (json.JSONDecodeError, TypeError):
    print("unknown:invalid-json")
    raise SystemExit

def direct_status(value):
    if isinstance(value, dict):
        for key in ("status", "outcome", "result"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    return None

status = None
for key in ("agent_status", "status", "outcome"):
    candidate = payload.get(key)
    if isinstance(candidate, str):
        status = candidate
        break

reason = payload.get("reason")
if status is None:
    status = direct_status(reason)
if status is None and isinstance(reason, str):
    status = reason

if not status:
    print("unknown:missing-status")
    raise SystemExit

text = re.sub(r"[_-]+", " ", status.strip().lower())
complete = re.match(r"^(completed|complete|succeeded|success|task appears complete)\b", text)
cancelled = re.match(r"^(cancelled|canceled)\b", text)
failed = re.match(r"^(failed|failure|error|timed out|timeout|blocked)\b", text)

if complete:
    print("complete")
elif cancelled:
    print("cancelled")
elif failed:
    print("failed:" + text.splitlines()[0][:120])
else:
    print("unknown:unrecognized-status")
PY
)

case "$DECISION" in
  complete|cancelled)
    exit 0
    ;;
  failed:*)
    cat >&2 <<'EOF'
[codex-multi-agent] 子 agent 的结构化终态为失败、超时或阻塞。
→ 保留已有部分结果并整理为 Handoff。
→ 只重试失败阶段，最多 2 次。
→ 仍失败时由主线程接手，或派 recovery-agent 诊断。
EOF
    exit 2
    ;;
  unknown:*)
    if [ "${WORKLIKERICO_HOOK_VERBOSE:-0}" = "1" ]; then
      printf '[codex-multi-agent] SubagentStop %s；不阻断，交由主线程按可见状态处理。\n' "${DECISION#unknown:}" >&2
    fi
    exit 0
    ;;
esac
