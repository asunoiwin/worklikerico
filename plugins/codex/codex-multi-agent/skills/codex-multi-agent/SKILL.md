---
name: codex-multi-agent
description: Use structured multi-agent coordination in Codex. Trigger only when the user explicitly asks for sub-agents, delegation, parallel agents, agent collaboration, or multi-agent work.
---

# Codex Multi-Agent

This skill adapts Rico's Claude `multi-agent-enhance` plugin to Codex. It is intentionally stricter than the Claude version because Codex only spawns sub-agents when the user explicitly asks for agent delegation or parallel agent work.

## Tool Mapping

Claude concepts map to Codex as follows:

- `Agent` -> `spawn_agent`
- `SendMessage` -> `send_input`
- `TaskCreate/TaskUpdate/TaskList` -> `update_plan`
- `Wait for agent` -> `wait_agent`
- `Close completed agent` -> `close_agent`
- Claude `general-purpose` -> Codex `default`
- Claude explorer agent -> Codex `explorer`
- Claude implementation agent -> Codex `worker`

## Hard Routing Rule

Spawn agents only when the user's request explicitly asks for:

- sub-agents,
- delegation,
- parallel agents,
- multi-agent work,
- agent collaboration,
- "派 agent",
- "让多个 agent 同时做".

If the user merely asks for depth, research, or careful work, do the work locally.

## Critical Path Rule

Before spawning:

1. Identify the immediate blocker.
2. Keep blocker work local if your next step depends on it.
3. Delegate only sidecar tasks that can run while you make progress locally.
4. Never duplicate delegated work in the main thread.

Good delegation targets:

- independent codebase questions,
- verification that can run while implementation continues,
- disjoint implementation slices,
- long-file outline/summarization,
- report aggregation,
- repeated test/script runs.

Poor delegation targets:

- the next exact fact you need before continuing,
- a tightly coupled design decision,
- edits to the same files another agent owns,
- ambiguous tasks without bounded output.

## Agent Types

Use `explorer` for read-only codebase questions:

- "Where is auth enforced?"
- "Who calls this service?"
- "Which files implement billing webhooks?"

Use `worker` for bounded edits:

- Assign exact ownership of files or modules.
- Say the worker is not alone in the codebase.
- Tell the worker not to revert others' changes.
- Require a final list of changed files.

Use `default` for non-code sidecar work:

- report aggregation,
- doc summarization,
- broad but bounded analysis.

## Handoff Format

Every delegated prompt should require this final shape:

```markdown
## Handoff
- Status: completed / blocked / failed
- Summary: one sentence
- Files changed: paths or none
- Key findings: concise bullets
- Risks: concise bullets
- Next step: one concrete recommendation
```

## Parallel Pattern

When multiple independent tasks exist, spawn them in the same tool turn. Give each agent:

- full context needed for its own task,
- exact output format,
- write ownership if editing,
- clear stop condition.

After spawning, immediately do non-overlapping local work. Use `wait_agent` only when blocked on the result.

## Verification

For code changes:

1. Review each worker's changed files.
2. Run relevant tests locally in the main thread unless verification was delegated and reported clean.
3. Resolve conflicts yourself without reverting user changes.
4. Close agents after their results are integrated.

## Planning

For substantial multi-agent work, maintain a visible plan with `update_plan`. Keep at most one local step `in_progress`; agent work can be described inside pending/in-progress text but should not make the plan noisy.
