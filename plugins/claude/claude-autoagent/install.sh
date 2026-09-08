#!/bin/bash
# claude-autoagent 安装脚本
# 将 agent 和 command 文件复制到 Claude Code 用户目录

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "=== claude-autoagent 安装 ==="

# 创建目录
mkdir -p "$CLAUDE_DIR/agents"
mkdir -p "$CLAUDE_DIR/commands"

# 复制 agents
cp "$SCRIPT_DIR/agents/supervisor.md" "$CLAUDE_DIR/agents/supervisor.md"
cp "$SCRIPT_DIR/agents/recovery-agent.md" "$CLAUDE_DIR/agents/recovery-agent.md"
echo "✓ agents 已安装"

# 复制 commands
cp "$SCRIPT_DIR/commands/orchestrate.md" "$CLAUDE_DIR/commands/orchestrate.md"
echo "✓ commands 已安装"

echo ""
echo "=== 安装完成 ==="
echo ""
echo "可选：自动路由 hook（UserPromptSubmit）"
echo "请参考 hooks/auto-route-prompt.md 手动添加到 ~/.claude/settings.json"
echo ""
echo "可用组件："
echo "  - supervisor agent: 自动任务编排"
echo "  - recovery-agent: 故障诊断与恢复"
echo "  - /orchestrate: 手动触发多 agent 编排"
echo ""
echo "重启 Claude Code 会话后生效。"
