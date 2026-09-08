#!/bin/bash
# PostToolUse hook for SubagentStop — auto-detect agent failures and suggest recovery
# This hook fires when a subagent stops, checks if it stopped abnormally,
# and injects context for the main agent to take recovery action.

INPUT=$(cat)

# Extract tool name and response
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Only process SubagentStop events (though matcher handles this)
if [ -z "$TOOL_NAME" ]; then
  exit 0
fi

# Check if the agent result indicates failure
AGENT_RESULT=$(echo "$INPUT" | jq -r '.tool_response // empty')
if [ -z "$AGENT_RESULT" ]; then
  exit 0
fi

# Look for failure signals in the response
HAS_ERROR=$(echo "$AGENT_RESULT" | jq -r 'if type == "object" then (.error // .status // empty) else empty end' 2>/dev/null)

if echo "$HAS_ERROR" | grep -qi "error\|failed\|timeout"; then
  # PostToolUse 不支持 additionalContext，只能通过非零退出码标记异常
  # 用 stderr 输出提示（会显示在 hook error 区域）
  echo "[multi-agent-enhance] 检测到子 agent 异常退出，建议调用 recovery-agent 诊断恢复" >&2
fi
