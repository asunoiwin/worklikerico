#!/usr/bin/env bash
# SessionStart hook：清理 7 天前的 state 文件，避免无限堆积
# 静默运行（任何输出都会进 SessionStart 输出，污染对话开头）

set -e
STATE_DIR="${WORKLIKERICO_DTL_STATE_DIR:-$HOME/.claude/state/design-test-loop}"
[ -d "$STATE_DIR" ] || exit 0

find "$STATE_DIR" -name '*.state' -mtime +7 -delete 2>/dev/null || true
exit 0
