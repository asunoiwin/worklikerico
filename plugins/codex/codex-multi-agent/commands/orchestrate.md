---
name: orchestrate
description: Analyze task complexity and route explicit multi-agent work through supervisor-style Codex delegation.
user-invocable: true
arguments:
  - name: task
    description: Task description to analyze and orchestrate.
    required: true
---

# Codex Multi-Agent Orchestration

User task: $ARGUMENTS

## Workflow

1. Score complexity:
   - research/search/compare/analyze: +1
   - design/architecture/plan: +1
   - implementation/change/build: +1
   - audit/test/verify/review: +1
   - documentation/report: +1
   - task text > 100 chars: +1
   - multi-step wording: +2
   - explicit parallel wording: +2

2. Route:
   - score < 3: do it locally.
   - score 3-5: use 2-3 bounded agents only if the user explicitly asked for multi-agent work.
   - score >= 6: use supervisor-style decomposition with 3-5 bounded agents.

3. Execution discipline:
   - Keep the immediate blocker in the main thread.
   - Delegate only sidecar tasks with disjoint read/write scope.
   - Require every agent to return only the Handoff format.
   - Aggregate Handoffs; do not paste raw logs, raw events, or long diffs.
