#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
PROMPT=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("prompt") or d.get("user_prompt") or "")' 2>/dev/null || true)

if ! printf '%s' "$PROMPT" | grep -Eqi 'sub-?agent|多.?agent|多个[[:space:]]*agent|并行.?agent|委派|delegate|delegation|让多个[[:space:]]*agent|同时.*agent|orchestrate'; then
  exit 0
fi

cat <<'EOF'
[codex-multi-agent] 检测到显式多 agent/委派意图。
→ 先识别主线程 immediate blocker，主线程继续关键路径。
→ 只委派低依赖旁路任务，且每个 agent 必须有任务边界、读写范围、停止条件。
→ 每个 agent 只允许返回 Handoff 摘要，不得回灌全文日志、全文 diff、全文 events。
→ 失败/超时/无 Handoff 时先恢复部分结果，必要时派 recovery-agent。
EOF
