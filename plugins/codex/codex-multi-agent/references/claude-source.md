# Claude Source Adaptation Notes

This plugin is adapted from Rico's Claude `multi-agent-enhance` plugin.

Important changes for Codex:

- Claude's proactive auto-routing is narrowed: Codex agent spawning still requires explicit user permission, but the plugin now emits a routing reminder when explicit multi-agent/delegation intent is detected.
- Claude `Agent` prompts are translated to Codex `spawn_agent` guidance and synced into `~/.codex/agents/supervisor.toml` and `~/.codex/agents/recovery-agent.toml`.
- Claude task tools are translated to Codex planning plus main-thread integration.
- Claude hooks are ported as Codex plugin hooks for intent routing, subagent failure reminders, and raw-result/context blowup guards.
- Supervisor/recovery-agent behavior is available both as plugin source files and as installed Codex agent types.

Source concepts preserved:

- complexity scoring,
- structured handoff,
- failure recovery,
- sidecar delegation,
- report aggregation,
- compile/test validation,
- long-file outlines,
- disjoint write ownership.
