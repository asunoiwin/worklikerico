---
name: delegate
description: Delegate low-dependency sidecar work in Codex when the user explicitly asks to use agents, parallel agents, or delegation. Covers long-file outlines, report aggregation, compile validation, release workflows, locator tasks, test batches, and bug-fix rechecks.
---

# Delegate Pattern

Use this skill only after the user explicitly permits agent delegation. Its purpose is to keep the main Codex thread focused on decisions and integration while agents handle bounded sidecar work.

## Decision Matrix

| Scenario | Delegate to | Write access |
|---|---|---|
| Long file outline | `explorer` | none |
| Report aggregation | `default` | none unless asked |
| Compile validation | `worker` | only compile-fix files |
| Release workflow | local main thread unless explicitly delegated | repo metadata only |
| Grep/context locator | `explorer` | none |
| Batch tests | `default` or `worker` | none unless fixing test harness |
| Bug-fix recheck | `default` | none |
| Disjoint implementation slice | `worker` | exact owned files only |

## Prompt Templates

### Long File Outline

Ask an `explorer`:

```text
Read ABSOLUTE_PATH and produce a concise outline under 500 tokens.
Include line-numbered symbol map, key dependencies, major behavior blocks, and risks.
Do not paste large code.
Return only the Handoff format.
```

### Report Aggregator

Ask a `default` agent:

```text
Read these reports:
- PATH1
- PATH2

Summarize into a table:
| Report | Pass/fail | Real issue | External issue | Recommendation |

Keep it under 800 tokens. Do not quote long passages.
Return only the Handoff format.
```

### Compile Validator

Ask a `worker`:

```text
You are not alone in the codebase; do not revert changes made by others.
Run the specified compile command.
If it fails, fix only import/type/signature errors in OWNED_PATHS.
Stop after 3 repair attempts.
Return command result and changed files in the Handoff format.
```

### Locator

Ask an `explorer`:

```text
Find KEYWORD in PROJECT.
Return file path, line number, and a short paraphrased context for each relevant hit.
Keep output under 300 tokens.
Return only the Handoff format.
```

### Test Batch Runner

Ask a `default` or `worker`:

```text
Run these scripts in order with a 60s timeout each:
- SCRIPT1
- SCRIPT2

Do not fix product code.
Summarize:
| Script | Pass | Fail | Key finding |
Return only the Handoff format.
```

### Bug-Fix Recheck

Ask a `default` agent:

```text
Verify this bug fix:
- Bug: DESC
- Method: HOW
- Expected: EXPECTED

Run the smallest reliable check.
Report PASS or FAIL plus the minimal reproduction command if failing.
Return only the Handoff format.
```

## Integration Rule

Do not treat agent output as final until the main thread has integrated it. Review changed files, run necessary tests, then close the agent.
