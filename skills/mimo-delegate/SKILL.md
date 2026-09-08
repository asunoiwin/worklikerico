---
name: mimo-delegate
description: Delegate bounded research, coding, review, tool-use, or parallel sub-agent work to the local MiMoCode CLI with deterministic timeout, model selection, permission isolation, evidence capture, and cleanup. Use when the user explicitly asks to call or compare MiMo, wants MiMo as a sub-agent, requests a MiMo second opinion, or when a bounded side task is intentionally assigned to MiMo from Claude or Codex.
---

# MiMo Delegate

Use the bundled wrapper instead of invoking `mimo run` directly. It prevents silent approval hangs, captures tool and actor evidence, terminates residual processes, rejects malformed handoffs, and removes the temporary MiMo session.

Treat the directory containing this file as `<SKILL_DIR>`.

## Workflow

1. Keep the task bounded. State the exact working directory, allowed writes, forbidden files, expected output, verification, and stop condition in the prompt. For coding work, explicitly forbid deleting/truncating tests, weakening assertions, replacing real fixtures with mocks, or claiming commands/metrics that were not run.
   When the host is Codex `workspace-write`, command subprocesses need outbound network enabled and MiMo runtime-state directories writable. If the host was not launched that way, do not repeatedly retry a silent MiMo start; follow the Codex host command in the operations reference or report the outer-sandbox blocker.
2. Discover the currently exposed model IDs; never infer an ID from a marketing model name.

   ```bash
   python3 <SKILL_DIR>/scripts/mimo_delegate.py models \
     --provider xiaomi --refresh --verbose
   ```

3. Choose the narrowest permission mode:

   - `read-only` (default): read/search/fetch only; no shell, edit, skill, or child-agent tools.
   - `workspace-write`: code changes inside `--cwd`; the wrapper adds a macOS filesystem sandbox because MiMo's tool permission alone does not reliably constrain shell redirection.
   - `full`: no filesystem sandbox and automatic approval bypass. Use only when the user explicitly authorizes unrestricted MiMo access and the task is already externally isolated.

4. Run one delegation. Pass the exact `provider/model` ID only after it appears in refreshed `models` output. Never relabel or silently fall back from `mimo/mimo-auto` to a marketing model.

   ```bash
   python3 <SKILL_DIR>/scripts/mimo_delegate.py run \
     --cwd /absolute/workspace \
     --model xiaomi/mimo-v2.5-pro \
     --permission-mode read-only \
     --timeout 180 \
     --prompt 'Inspect the requested files and return findings with exact evidence.'
   ```

5. Inspect the JSON result before trusting the prose:

   - require `status: success` and `handoff.valid: true`;
   - check `permission_event`, `timed_out`, `terminated_after_idle_result`, `terminated_descendant_pids`, `failed_tool_uses`, `integrity_warnings`, and `stderr_tail`;
   - treat any `host_verification_required: true` result as unaccepted worker evidence;
   - independently verify changed files/tests for coding work;
   - for nested parallel work, require distinct successful `actors`, `parallel_overlap_detected: true`, and no `actor_scheduling_violation`.

6. Return a compact handoff. Do not paste raw event logs.

## Delegation contracts

For implementation prompts, include writable files or modules, forbidden files, done definition, exact verification commands, and adversarial cases. Keep MiMo in `workspace-write`; pass one or more cwd-relative `--write-path` values so the OS sandbox enforces the declared write scope. Do not use `full` merely to avoid a failed tool call. MiMo self-tests are first-pass evidence only: the host must inspect the diff and rerun decisive typecheck/build/tests before acceptance.

For research prompts, require real tool evidence. This MiMo installation exposes `webfetch` but not a native `websearch` tool. Use a search API or search-result URL through `webfetch`, then fetch the authoritative result. Do not claim native web search occurred when only direct fetching occurred.

For multiple independent lanes, prefer host-owned concurrency: launch separate wrapper processes in independent worktrees/copies or with disjoint `--write-path` allowlists, then let Codex/Claude supervise them. This avoids making MiMo both scheduler and worker. Use nested MiMo actors only when the user specifically needs them or the work shares one MiMo context; require every spawn before the first wait, do not invent undocumented actor parameters such as `timeout_ms`, and fail the run if a spawn occurs after waiting starts. A final answer that merely says “parallel” is insufficient.

## Acceptance and recovery

- Never promote MiMo prose or green tests directly into project authority. Verify source-level invariants, negative cases, real fixtures, build output, and measured values independently.
- Treat `integrity_warnings`, failed actor tools, missing/empty Handoff fields, invalid Status values, reported `blocked/failed`, timeouts, or incomplete actors as a failed delegation even if MiMo says success.
- On one bounded failure, preserve usable files and retry only the failed slice with a corrected contract. On repeated scheduling/quality failure, stop nested orchestration and let the host take over or launch separate single-scope workers.
- The wrapper recovers final text without `step_finish` after the idle window and kills detached descendants on exit. Inspect these fields; recurring recovery means the model/runtime is unstable, not clean success.
- Use `--allow-freeform-result` only for deliberate diagnostics. Normal delegations must return the required Handoff.

## Output format

```markdown
## Handoff
- Status: completed / blocked / failed
- Summary: one sentence
- Files changed: paths or none
- Key findings: concise bullets
- Risks: concise bullets
- Verification: commands and pass/fail
- Next step: one concrete recommendation
```

Read [references/operations.md](references/operations.md) when changing permission modes, adding providers/models, diagnosing a failure, benchmarking, or invoking multiple MiMo actors.
