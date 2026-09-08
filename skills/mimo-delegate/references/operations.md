# MiMo Delegate operations reference

## Installation and discovery

The wrapper resolves MiMo in this order: explicit `--mimo-bin`, `MIMO_BIN`, `PATH`, then `~/.mimocode/bin/mimo`.

Model selection is dynamic:

```bash
python3 <SKILL_DIR>/scripts/mimo_delegate.py models --provider xiaomi --refresh --verbose
python3 <SKILL_DIR>/scripts/mimo_delegate.py models --provider mimo --refresh --verbose
python3 <SKILL_DIR>/scripts/mimo_delegate.py models --provider openrouter
```

Pass an exact `provider/model` string with `--model`. An unavailable model returns `status: invalid_model`; never silently fall back. On the 2026-07-17 tested installation, refreshed `xiaomi` discovery exposed `xiaomi/mimo-v2.5`, `xiaomi/mimo-v2.5-pro`, and `xiaomi/mimo-v2.5-pro-ultraspeed`. Availability can change, so discovery remains mandatory. The alias `mimo/mimo-auto` does not prove which marketing model the server routes to and must not be relabeled.

## Permission model

The wrapper injects an ephemeral `MIMOCODE_CONFIG_CONTENT` agent for each run and does not persist global permission changes.

| Mode | MiMo tools | OS write boundary | Intended use |
|---|---|---|---|
| `read-only` | read, glob, grep, lsp, webfetch | No edit/bash/actor tools | inspection, research, review |
| `workspace-write` | read, edit, bash, fetch, skills, actors | macOS `sandbox-exec`: working directory plus MiMo runtime state | bounded coding and parallel workers |
| `full` | all | none; adds `--dangerously-skip-permissions` | explicitly authorized, externally isolated work |

`workspace-write` fails closed with `sandbox_unavailable` off macOS. Do not weaken that behavior without adding and testing an equivalent OS sandbox for the target platform.

Use repeatable `--write-path <cwd-relative-path>` flags to enforce narrower write ownership. Without `--write-path`, the compatibility default allows the full `--cwd`; therefore parallel writers must use independent worktrees/copies or explicit disjoint allowlists.

MiMo runtime state remains writable under `~/.local/share/mimocode`, `~/.cache/mimocode`, and `~/.local/state/mimocode`; product/project files outside `--cwd` are not writable in `workspace-write`. The subprocess receives a private temporary directory which is removed after the run.

### Codex host sandbox

Codex `workspace-write` disables command/subprocess network by default. Because MiMo is a hosted-model CLI, a Codex host must explicitly enable outbound network for the run. It also needs MiMo's three runtime-state directories as writable roots so session creation and cleanup do not pause for approval:

```bash
codex exec \
  --sandbox workspace-write \
  -c 'sandbox_workspace_write.network_access=true' \
  --add-dir "$HOME/.local/share/mimocode" \
  --add-dir "$HOME/.cache/mimocode" \
  --add-dir "$HOME/.local/state/mimocode" \
  'Use $mimo-delegate for the bounded task.'
```

Without command network, MiMo can start but emit no model events until the wrapper timeout. Treat that as an outer Codex sandbox blocker, not a MiMo permission request. Do not switch the MiMo run to `full`; `full` cannot override its parent Codex sandbox.

## Reliability behavior

- A permission-request event returns `permission_required` and a non-zero exit immediately.
- Overall timeout returns `timeout` and terminates the entire process group.
- MiMo may emit a final result but omit `step_finish` or keep its process alive. The wrapper recovers after `--result-idle-seconds`, terminates it, and records `terminated_after_result` / `terminated_after_idle_result`.
- Before terminating the main process group, the wrapper snapshots and kills descendants, including children that created a separate process group. Inspect `terminated_descendant_pids`; recurring non-empty values are runtime instability evidence.
- By default the session is deleted and a newly created, known-empty `.mimocode` metadata directory is removed. Existing workspace MiMo configuration is preserved.
- Normal runs require the seven-field Handoff. Fields must be non-empty and Status must be exactly `completed`, `blocked`, or `failed`. Invalid Handoffs return `invalid_handoff`; a self-reported blocked/failed Handoff returns `reported_blocked` / `reported_failed`.
- `tool_uses` may contain failed calls even when prose says success. The result exposes `failed_tool_uses`; actor failures return `actor_tool_error`.
- Suspicious destructive test commands are reported as non-secret `integrity_warnings`. They are review triggers, not proof that final files are correct or incorrect.
- `host_verification_required` and `acceptance_status: unverified_by_host` are deliberate: wrapper success never equals project acceptance.
- Use `--raw-log` only for diagnostics. Raw logs can contain file contents and tool parameters; keep them outside deliverables. The parent directory must already exist and the wrapper uses exclusive creation, refusing to overwrite any existing path.

## Network research

Current tested tool availability:

- `webfetch`: working.
- native `websearch`: unavailable, including with external plugins enabled.

For search, fetch a purpose-built API such as GitHub Search, or a search-result endpoint, then fetch the selected authoritative URL. Report this as fetch-based search, not native search-tool support.

## Parallel actors

Prefer launching independent wrapper processes from the host, each in an independent worktree/copy or with a disjoint `--write-path` allowlist. Use MiMo's nested actor scheduler only when shared MiMo context is material.

When nested actors are used, ask MiMo to issue all actor spawn operations before any wait operation. Do not pass undocumented fields such as `timeout_ms`. The wrapper extracts actor creation/completion timestamps and returns:

- `actors`: actor IDs, model metadata, outcomes, and timestamps;
- `parallel_overlap_detected`: whether at least two completed actor lifetimes overlap.
- `actor_actions`: the observed spawn/wait sequence.

Require successful actor outcomes, overlap evidence, and no spawn after the first wait. A spawn-after-wait sequence returns `actor_scheduling_violation`. Parallel workers inherit the parent run's task context; keep writable scopes disjoint inside the sandboxed workspace.

## Quality and acceptance discipline

MiMo is an implementation worker, not its own acceptance authority. In the prompt, freeze writable/forbidden paths, exact commands, negative cases, and the required Handoff. Forbid deleting or truncating tests, weakening assertions, replacing real fixtures with permissive mocks, or inventing metrics.

After a coding run, the host must:

1. inspect changed files and failed tool/integrity signals;
2. run typecheck/build/tests independently;
3. exercise the contract with adversarial inputs rather than only replaying worker tests;
4. keep production/readiness claims unchanged until independent evidence supports them.

If one lane times out or fails quality review, retry only that bounded slice. Repeated actor scheduling failures, false-positive tests, or process cleanup events require host takeover or separate single-scope wrapper runs.

## Benchmark discipline

Use identical clean copies, prompts, visible tests, and external hidden verification. Alternate run order to reduce warm-cache bias. Record wall time, first-pass public/hidden tests, unrelated changes, and real tool evidence. Two microtasks can identify gross speed or correctness differences but cannot establish general model equivalence.

If `mimo/mimo-auto` is the tested ID, label results with that ID. Do not relabel it as MiMo-V2.5 unless provider metadata independently confirms the routing. Compare model quality only after host-side hidden verification; MiMo-reported test counts or recommendations are not benchmark truth.

## Maintenance checks

```bash
python3 -m py_compile <SKILL_DIR>/scripts/mimo_delegate.py
python3 -m unittest -v <SKILL_DIR>/scripts/test_mimo_delegate.py
```

Run Codex skill validation after edits, then mirror the same directory into Claude's skill root. The `SKILL.md` frontmatter intentionally uses only `name` and `description` for cross-compatibility.
