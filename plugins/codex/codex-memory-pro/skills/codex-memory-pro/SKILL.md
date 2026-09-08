---
name: codex-memory-pro
description: Use semantic long-term memory for Codex. Trigger when the user asks to remember, recall, search past decisions, store durable preferences, inspect memory health, clean stale memory, or continue work using remembered project context.
---

# Codex Memory Pro

Use this skill when durable semantic memory is useful. Prefer the MCP tools from `codex-memory-pro` over ad hoc local notes when the information should survive future sessions.

## Tool Intent

- `memory_recall`: retrieve project decisions, preferences, facts, lessons, task context, and entities.
- `memory_store`: save important user preferences, architecture decisions, facts, and lessons.
- `memory_update`: correct an existing memory instead of storing a conflicting duplicate.
- `memory_forget`: delete obsolete or wrong memory.
- `memory_list`: inspect stored memory by scope/category.
- `memory_stats`: check database, recall, and retrieval health.
- `memory_audit`, `memory_cleanup`, `memory_atlas_refresh`, `memory_daily_reorg`: use for maintenance when the user asks for memory quality work.

## Retrieval Rules

1. Before code changes in a project with known history, call memory recall for:
   - the project name,
   - the subsystem,
   - the user's stated constraint or bug.
2. Keep recalled context small. Use the top 3-5 items unless the user asks for exhaustive history.
3. Treat memory as context, not proof. Verify against the repo before making code changes.
4. If a recall is stale or contradicted by the current code, update or forget it after confirming the better fact.

## Storage Rules

Store only durable, reusable information:

- user preferences and constraints,
- architecture decisions,
- non-obvious project facts,
- incident lessons,
- task outcomes worth reusing.

Do not store secrets, transient command output, raw logs, or large copied text. Summarize first.

Use categories consistently:

- `preference`: user/team preferences.
- `decision`: decisions and rationale.
- `fact`: stable facts about systems.
- `entity`: named systems, services, people, or repos.
- `task`: task state or handoff.
- `lesson`: debugging or delivery lessons.
- `other`: only when no category fits.

## Scope Convention

Use `global` for cross-project user preferences. Use a repo or product scope for project facts, for example:

- `larktokenweb`
- `openclaw`
- `codex-memory-pro`

## Codex Behavior

Codex may have its own built-in memories enabled. Use Codex Memory Pro for structured semantic recall and explicit persistence. Use built-in memories for assistant-level conversational preferences.
