#!/usr/bin/env python3
"""Deterministic MiMoCode delegation wrapper for Claude and Codex skills."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, TextIO


KNOWN_METADATA_FILES = {".gitignore", ".cron-lock"}
MAX_DIAGNOSTIC_LINE = 2000
HANDOFF_FIELDS = ("Status", "Summary", "Files changed", "Key findings", "Risks", "Verification", "Next step")
FAILED_TOOL_STATUSES = {"error", "failed", "cancelled", "canceled", "rejected"}
MODE_AGENTS = {
    "read-only": "mimo-delegate-readonly",
    "workspace-write": "mimo-delegate-workspace",
    "full": "mimo-delegate-full",
}


def _clip_diagnostic(line: str) -> str:
    if len(line) <= MAX_DIAGNOSTIC_LINE:
        return line
    return f"{line[:MAX_DIAGNOSTIC_LINE]}...[truncated {len(line) - MAX_DIAGNOSTIC_LINE} chars]"


def _runtime_config(permission_mode: str, agent_name: str) -> str:
    common_prompt = (
        "You are a bounded delegate launched by another coding agent. Complete only the stated task, "
        "use tools when evidence is required, and never ask the user a question. Never delete, truncate, "
        "or weaken existing tests to obtain a pass. Never claim a build, metric, or verification that you did "
        "not actually run. Treat your own test result as worker evidence, not final acceptance. End with a "
        "Handoff containing Status, Summary, Files changed, Key findings, Risks, Verification, and Next step. "
        "The Status value must be exactly one of: completed, blocked, failed."
    )
    read_permissions: dict[str, Any] = {
        "*": "deny",
        "read": {"*": "allow", "*.env": "deny", "*.env.*": "deny", "*.env.example": "allow"},
        "glob": "allow",
        "grep": "allow",
        "lsp": "allow",
        "webfetch": "allow",
        "websearch": "allow",
        "codesearch": "allow",
        "external_directory": "deny",
        "question": "deny",
        "doom_loop": "deny",
    }
    workspace_permissions = {
        **read_permissions,
        "edit": "allow",
        "bash": "allow",
        "skill": "allow",
        "task": "allow",
        "actor": "allow",
    }
    full_permissions = {
        "*": "allow",
        "question": "deny",
        "doom_loop": "deny",
    }
    permissions = {
        "read-only": read_permissions,
        "workspace-write": workspace_permissions,
        "full": full_permissions,
    }[permission_mode]
    config = {
        "agent": {
            agent_name: {
                "description": f"MiMo delegate runtime for {permission_mode} tasks",
                "mode": "primary",
                "prompt": common_prompt,
                "permission": permissions,
            }
        }
    }
    return json.dumps(config, ensure_ascii=False)


def _check_handoff(text: str | None) -> dict[str, Any]:
    if not text:
        return {
            "valid": False,
            "missing_fields": list(HANDOFF_FIELDS),
            "empty_fields": [],
            "reported_status": None,
            "invalid_status": False,
        }
    field_names = "|".join(re.escape(field) for field in HANDOFF_FIELDS)
    marker = re.compile(rf"(?im)^(?:-\s*)?(?:\*\*)?({field_names})(?:\*\*)?\s*:")
    matches = list(marker.finditer(text))
    values: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        values.setdefault(match.group(1), text[match.end() : end].strip())
    missing = [field for field in HANDOFF_FIELDS if field not in values]
    empty = [field for field in HANDOFF_FIELDS if field in values and not values[field]]
    status_value = values.get("Status", "").strip().lower().strip("*")
    reported = status_value if status_value in {"completed", "blocked", "failed"} else None
    invalid_status = "Status" in values and reported is None
    return {
        "valid": not missing and not empty and not invalid_status,
        "missing_fields": missing,
        "empty_fields": empty,
        "reported_status": reported,
        "invalid_status": invalid_status,
    }


def _integrity_warning_codes(event: dict[str, Any]) -> set[str]:
    if event.get("type") != "tool_use":
        return set()
    part = event.get("part") if isinstance(event.get("part"), dict) else {}
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    tool_input = state.get("input")
    if tool_input is None:
        return set()
    compact = json.dumps(tool_input, ensure_ascii=False).lower()
    warnings: set[str] = set()
    if re.search(r"\btruncate\s+-s\s+0\b", compact):
        warnings.add("zero_length_truncate")
    if re.search(r"\b(?:rm|unlink)\b[^\n]*(?:test|spec)", compact):
        warnings.add("test_file_deletion_command")
    if re.search(r">\s*[^\s;]+(?:test|spec)[^\s;]*", compact):
        warnings.add("test_file_overwrite_redirection")
    return warnings


def _descendant_pids(root_pid: int) -> list[int]:
    try:
        completed = subprocess.run(
            ["/bin/ps", "-axo", "pid=,ppid="],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    children: dict[int, list[int]] = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            pid, ppid = map(int, fields)
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)
    found: list[int] = []
    pending = list(children.get(root_pid, []))
    while pending:
        pid = pending.pop()
        if pid in found:
            continue
        found.append(pid)
        pending.extend(children.get(pid, []))
    return found


def _terminate_descendants(pids: list[int], grace: float = 0.5) -> list[int]:
    attempted: list[int] = []
    for pid in reversed(pids):
        try:
            os.kill(pid, signal.SIGTERM)
            attempted.append(pid)
        except ProcessLookupError:
            pass
    if attempted:
        time.sleep(grace)
    for pid in attempted:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return attempted


def _macos_write_sandbox(
    command: list[str],
    cwd: Path,
    temp_dir: Path,
    write_paths: list[Path] | None = None,
) -> list[str] | None:
    sandbox_exec = Path("/usr/bin/sandbox-exec")
    if sys.platform != "darwin" or not sandbox_exec.is_file():
        return None
    writable = [
        *(path.resolve() for path in (write_paths or [cwd])),
        temp_dir.resolve(),
        (Path.home() / ".local" / "share" / "mimocode").resolve(),
        (Path.home() / ".cache" / "mimocode").resolve(),
        (Path.home() / ".local" / "state" / "mimocode").resolve(),
    ]

    def quote(path: Path) -> str:
        return str(path).replace("\\", "\\\\").replace('"', '\\"')

    exceptions = " ".join(f'(require-not (subpath "{quote(path)}"))' for path in writable)
    git_metadata = cwd.resolve() / ".git"
    profile = (
        f"(version 1) (allow default) (deny file-write* (require-all {exceptions})) "
        f'(deny file-write* (subpath "{quote(git_metadata)}"))'
    )
    return [str(sandbox_exec), "-p", profile, *command]


def find_mimo(explicit: str | None = None) -> str:
    candidates = [explicit, os.environ.get("MIMO_BIN"), shutil.which("mimo")]
    candidates.append(str(Path.home() / ".mimocode" / "bin" / "mimo"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise FileNotFoundError("MiMoCode CLI not found; set MIMO_BIN or add ~/.mimocode/bin to PATH")


def _reader(stream: TextIO, channel: str, output: queue.Queue[tuple[str, str | None]]) -> None:
    try:
        for line in iter(stream.readline, ""):
            output.put((channel, line.rstrip("\n")))
    finally:
        output.put((channel, None))


def _terminate_group(proc: subprocess.Popen[str], grace: float = 1.0) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        pass


def _is_permission_request(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type", "")).lower().replace("_", ".")
    if event_type in {"permission.asked", "permission.ask", "permission.requested"}:
        return True
    compact = json.dumps(event, ensure_ascii=False).lower()
    return "permission.asked" in compact or '"permission"' in compact and '"ask"' in compact


def _cleanup_new_workspace_metadata(cwd: Path, existed_before: bool) -> dict[str, Any]:
    metadata = cwd / ".mimocode"
    result: dict[str, Any] = {"attempted": not existed_before, "removed": False, "preserved": []}
    if existed_before or not metadata.is_dir():
        return result
    children = list(metadata.iterdir())
    unknown = [child.name for child in children if child.name not in KNOWN_METADATA_FILES]
    if unknown:
        result["preserved"] = sorted(unknown)
        return result
    for child in children:
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
    try:
        metadata.rmdir()
        result["removed"] = True
    except OSError:
        result["preserved"] = sorted(child.name for child in metadata.iterdir())
    return result


def _delete_session(mimo_bin: str, session_id: str | None) -> dict[str, Any]:
    if not session_id:
        return {"attempted": False, "deleted": False}
    try:
        completed = subprocess.run(
            [mimo_bin, "session", "delete", session_id],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"attempted": True, "deleted": False, "error": str(exc)}
    return {
        "attempted": True,
        "deleted": completed.returncode == 0,
        "returncode": completed.returncode,
    }


def run_delegate(
    *,
    prompt: str,
    cwd: Path,
    model: str | None = None,
    agent: str | None = None,
    permission_mode: str = "read-only",
    timeout: float = 600,
    settle_seconds: float = 2.0,
    result_idle_seconds: float = 15.0,
    require_handoff: bool = True,
    title: str = "mimo-delegate",
    mimo_bin: str | None = None,
    allow_plugins: bool = False,
    keep_session: bool = False,
    keep_workspace_metadata: bool = False,
    raw_log: Path | None = None,
    write_paths: list[Path] | None = None,
) -> tuple[int, dict[str, Any]]:
    started = time.monotonic()
    cwd = cwd.expanduser().resolve()
    if not cwd.is_dir():
        return 2, {"status": "invalid_cwd", "cwd": str(cwd), "error": "directory does not exist"}
    if permission_mode not in {"read-only", "workspace-write", "full"}:
        return 2, {"status": "invalid_permission_mode", "permission_mode": permission_mode}
    resolved_write_paths: list[Path] = []
    for path in write_paths or []:
        resolved = (cwd / path).resolve() if not path.is_absolute() else path.expanduser().resolve()
        if not resolved.is_relative_to(cwd):
            return 2, {
                "status": "invalid_write_path",
                "cwd": str(cwd),
                "write_path": str(resolved),
                "error": "write paths must stay inside cwd",
            }
        resolved_write_paths.append(resolved)
    if resolved_write_paths and permission_mode != "workspace-write":
        return 2, {
            "status": "invalid_write_path_mode",
            "error": "--write-path is only valid with workspace-write",
        }

    try:
        binary = find_mimo(mimo_bin)
    except FileNotFoundError as exc:
        return 127, {"status": "missing_binary", "error": str(exc)}

    selected_agent = agent or MODE_AGENTS[permission_mode]
    if agent and agent != MODE_AGENTS[permission_mode]:
        return 2, {
            "status": "unsafe_agent_selection",
            "error": f"{permission_mode} mode requires wrapper-managed agent {MODE_AGENTS[permission_mode]}",
            "agent": selected_agent,
        }

    command = [binary, "run"]
    if not allow_plugins:
        command.append("--pure")
    command.extend(["--format", "json", "--dir", str(cwd), "--agent", selected_agent, "--title", title])
    if model:
        command.extend(["--model", model])
    if permission_mode == "full":
        command.append("--dangerously-skip-permissions")
    command.append(prompt)
    execution_command = command
    sandbox_temp: tempfile.TemporaryDirectory[str] | None = None
    sandboxed = False
    if permission_mode == "workspace-write":
        sandbox_temp = tempfile.TemporaryDirectory(prefix="mimo-delegate-")
        execution_command = _macos_write_sandbox(
            command,
            cwd,
            Path(sandbox_temp.name),
            resolved_write_paths or None,
        )
        if execution_command is None:
            sandbox_temp.cleanup()
            return 2, {
                "status": "sandbox_unavailable",
                "error": "workspace-write requires the macOS sandbox-exec filesystem backstop",
            }
        sandboxed = True

    metadata_existed = (cwd / ".mimocode").exists()
    events: list[dict[str, Any]] = []
    texts: list[str] = []
    tools: list[dict[str, Any]] = []
    actor_runs: dict[str, dict[str, Any]] = {}
    actor_actions: list[str] = []
    integrity_warnings: set[str] = set()
    stderr_tail: deque[str] = deque(maxlen=60)
    malformed_tail: deque[str] = deque(maxlen=20)
    session_id: str | None = None
    terminal_seen_at: float | None = None
    last_activity_at: float | None = None
    permission_event: dict[str, Any] | None = None
    raw_handle: TextIO | None = None

    if raw_log:
        raw_log = raw_log.expanduser().resolve()
        if not raw_log.parent.is_dir():
            if sandbox_temp:
                sandbox_temp.cleanup()
            return 2, {
                "status": "invalid_raw_log_parent",
                "error": "raw log parent directory must already exist",
            }
        try:
            raw_handle = raw_log.open("x", encoding="utf-8")
        except FileExistsError:
            if sandbox_temp:
                sandbox_temp.cleanup()
            return 2, {
                "status": "raw_log_exists",
                "error": "refusing to overwrite an existing raw log",
                "raw_log": str(raw_log),
            }
        except OSError as exc:
            if sandbox_temp:
                sandbox_temp.cleanup()
            return 2, {
                "status": "invalid_raw_log",
                "error": str(exc),
                "raw_log": str(raw_log),
            }

    try:
        child_env = os.environ.copy()
        child_env["MIMOCODE_CONFIG_CONTENT"] = _runtime_config(permission_mode, selected_agent)
        if sandbox_temp:
            child_env["TMPDIR"] = sandbox_temp.name
        proc = subprocess.Popen(
            execution_command,
            cwd=str(cwd),
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except OSError as exc:
        if sandbox_temp:
            sandbox_temp.cleanup()
        if raw_handle:
            raw_handle.close()
        return 126, {"status": "start_failed", "error": str(exc), "command": command[:-1] + ["<prompt>"]}

    output_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
    assert proc.stdout is not None and proc.stderr is not None
    threads = [
        threading.Thread(target=_reader, args=(proc.stdout, "stdout", output_queue), daemon=True),
        threading.Thread(target=_reader, args=(proc.stderr, "stderr", output_queue), daemon=True),
    ]
    for thread in threads:
        thread.start()

    status = "process_error"
    timed_out = False
    terminated_after_result = False
    terminated_after_idle_result = False
    deadline = started + timeout
    open_channels = {"stdout", "stderr"}

    try:
        while True:
            now = time.monotonic()
            if now >= deadline:
                status = "timeout"
                timed_out = True
                break
            if permission_event is not None:
                status = "permission_required"
                break
            if terminal_seen_at is not None and now - terminal_seen_at >= settle_seconds:
                status = "success" if texts else "no_result"
                if proc.poll() is None:
                    terminated_after_result = True
                break
            if texts and terminal_seen_at is None and last_activity_at is not None and now - last_activity_at >= result_idle_seconds:
                status = "success"
                if proc.poll() is None:
                    terminated_after_result = True
                    terminated_after_idle_result = True
                break
            if proc.poll() is not None and not open_channels and output_queue.empty():
                status = "success" if texts and proc.returncode == 0 else "process_error"
                break

            wait_for = min(0.2, max(0.01, deadline - now))
            try:
                channel, line = output_queue.get(timeout=wait_for)
            except queue.Empty:
                continue
            if line is None:
                open_channels.discard(channel)
                continue
            if raw_handle:
                raw_handle.write(f"{channel}\t{line}\n")
                raw_handle.flush()
            if channel == "stderr":
                stderr_tail.append(_clip_diagnostic(line))
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                malformed_tail.append(line)
                continue
            if not isinstance(event, dict):
                continue
            events.append(event)
            last_activity_at = time.monotonic()
            integrity_warnings.update(_integrity_warning_codes(event))
            session_id = session_id or event.get("sessionID")
            if _is_permission_request(event):
                permission_event = event
                continue
            event_type = event.get("type")
            part = event.get("part") if isinstance(event.get("part"), dict) else {}
            if event_type == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
            if event_type == "tool_use":
                state = part.get("state") if isinstance(part.get("state"), dict) else {}
                metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
                tool_name = part.get("tool")
                tools.append(
                    {
                        "tool": tool_name,
                        "status": state.get("status"),
                        "actor_id": metadata.get("actorId"),
                        "model": metadata.get("model"),
                        "time": state.get("time"),
                    }
                )
                if tool_name == "actor":
                    tool_input = state.get("input") if isinstance(state.get("input"), dict) else {}
                    operation = tool_input.get("operation") if isinstance(tool_input.get("operation"), dict) else {}
                    action = operation.get("action")
                    if action:
                        actor_actions.append(str(action))
                    if action == "spawn" and metadata.get("actorId"):
                        actor_id = str(metadata["actorId"])
                        actor_runs[actor_id] = {
                            "actor_id": actor_id,
                            "description": operation.get("description"),
                            "model": metadata.get("model"),
                            "created": (state.get("time") or {}).get("start"),
                            "completed": None,
                            "outcome": None,
                        }
                    elif action == "wait":
                        actor_id = str(operation.get("actor_id", ""))
                        output = state.get("output")
                        try:
                            actor_output = json.loads(output) if isinstance(output, str) else {}
                        except json.JSONDecodeError:
                            actor_output = {}
                        if actor_id:
                            actor = actor_runs.setdefault(actor_id, {"actor_id": actor_id})
                            timing = actor_output.get("time") if isinstance(actor_output.get("time"), dict) else {}
                            actor.update(
                                {
                                    "completed": timing.get("completed"),
                                    "outcome": actor_output.get("lastOutcome"),
                                    "reported_status": actor_output.get("reportedStatus"),
                                }
                            )
            if event_type == "step_finish" and part.get("reason") == "stop":
                terminal_seen_at = time.monotonic()
            elif event_type in {"tool_use", "step_start"}:
                terminal_seen_at = None
    finally:
        descendant_pids = _descendant_pids(proc.pid)
        terminated_descendants = _terminate_descendants(descendant_pids)
        _terminate_group(proc)
        for thread in threads:
            thread.join(timeout=0.5)
        proc.stdout.close()
        proc.stderr.close()
        if raw_handle:
            raw_handle.close()

    elapsed = round(time.monotonic() - started, 3)
    if status == "process_error" and any("ProviderModelNotFoundError" in line for line in stderr_tail):
        status = "invalid_model"
    if status == "success":
        if any(tool.get("tool") == "actor" and str(tool.get("status", "")).lower() in FAILED_TOOL_STATUSES for tool in tools):
            status = "actor_tool_error"
        elif "wait" in actor_actions and any(
            action == "spawn" for action in actor_actions[actor_actions.index("wait") + 1 :]
        ):
            status = "actor_scheduling_violation"
        elif actor_runs and any(actor.get("completed") is None for actor in actor_runs.values()):
            status = "incomplete_actors"
        elif actor_runs and any(actor.get("outcome") != "success" for actor in actor_runs.values()):
            status = "actor_error"
    if status == "success" and integrity_warnings:
        status = "integrity_review_required"
    handoff = _check_handoff(texts[-1] if texts else None)
    if status == "success" and require_handoff and not handoff["valid"]:
        status = "invalid_handoff"
    if status == "success" and handoff["reported_status"] in {"blocked", "failed"}:
        status = f"reported_{handoff['reported_status']}"
    cleanup = {"session": {"attempted": False, "deleted": False}, "workspace_metadata": {}}
    if not keep_session:
        cleanup["session"] = _delete_session(binary, session_id)
    if keep_workspace_metadata:
        cleanup["workspace_metadata"] = {"attempted": False, "removed": False}
    else:
        cleanup["workspace_metadata"] = _cleanup_new_workspace_metadata(cwd, metadata_existed)
    if sandbox_temp:
        sandbox_temp.cleanup()

    result = {
        "status": status,
        "cwd": str(cwd),
        "model_requested": model,
        "agent": selected_agent,
        "permission_mode": permission_mode,
        "os_write_sandbox": sandboxed,
        "write_paths": [str(path) for path in resolved_write_paths],
        "elapsed_seconds": elapsed,
        "exit_code": proc.returncode,
        "timed_out": timed_out,
        "terminated_after_result": terminated_after_result,
        "terminated_after_idle_result": terminated_after_idle_result,
        "terminated_descendant_pids": terminated_descendants,
        "session_id": session_id,
        "final_text": texts[-1] if texts else None,
        "text_events": len(texts),
        "event_count": len(events),
        "tool_uses": tools,
        "failed_tool_uses": [
            tool for tool in tools if str(tool.get("status", "")).lower() in FAILED_TOOL_STATUSES
        ],
        "integrity_warnings": sorted(integrity_warnings),
        "actors": list(actor_runs.values()),
        "actor_actions": actor_actions,
        "parallel_overlap_detected": any(
            first.get("created") is not None
            and first.get("completed") is not None
            and second.get("created") is not None
            and second.get("completed") is not None
            and max(first["created"], second["created"]) < min(first["completed"], second["completed"])
            for index, first in enumerate(actor_runs.values())
            for second in list(actor_runs.values())[index + 1 :]
        ),
        "permission_event": permission_event,
        "stderr_tail": list(stderr_tail),
        "malformed_stdout_tail": list(malformed_tail),
        "handoff": handoff,
        "host_verification_required": permission_mode != "read-only" or bool(tools),
        "acceptance_status": "unverified_by_host",
        "cleanup": cleanup,
        "command": command[:-1] + ["<prompt>"],
    }
    exit_code = 0 if status == "success" else 3 if status == "permission_required" else 124 if status == "timeout" else 1
    return exit_code, result


def list_models(
    provider: str,
    mimo_bin: str | None = None,
    timeout: float = 30,
    refresh: bool = False,
    verbose: bool = False,
) -> tuple[int, dict[str, Any]]:
    try:
        binary = find_mimo(mimo_bin)
        command = [binary, "models", provider]
        if refresh:
            command.append("--refresh")
        if verbose:
            command.append("--verbose")
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return 1, {"status": "error", "provider": provider, "error": str(exc), "models": []}
    model_pattern = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.:-]+$")
    models = [line.strip() for line in completed.stdout.splitlines() if model_pattern.fullmatch(line.strip())]
    status = "success" if completed.returncode == 0 else "error"
    return completed.returncode, {
        "status": status,
        "provider": provider,
        "models": models,
        "stderr": completed.stderr.splitlines()[-20:],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely delegate work to the local MiMoCode CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    models_parser = subparsers.add_parser("models", help="List currently available models for a provider")
    models_parser.add_argument("--provider", default="mimo")
    models_parser.add_argument("--mimo-bin")
    models_parser.add_argument("--timeout", type=float, default=30)
    models_parser.add_argument("--refresh", action="store_true")
    models_parser.add_argument("--verbose", action="store_true")

    run_parser = subparsers.add_parser("run", help="Run one bounded MiMoCode delegation")
    prompt_group = run_parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt")
    prompt_group.add_argument("--prompt-file", type=Path)
    run_parser.add_argument("--cwd", type=Path, default=Path.cwd())
    run_parser.add_argument("--model")
    run_parser.add_argument("--agent")
    run_parser.add_argument(
        "--permission-mode",
        choices=["read-only", "workspace-write", "full"],
        default="read-only",
    )
    run_parser.add_argument("--timeout", type=float, default=600)
    run_parser.add_argument("--settle-seconds", type=float, default=2.0)
    run_parser.add_argument("--result-idle-seconds", type=float, default=15.0)
    run_parser.add_argument("--allow-freeform-result", action="store_true")
    run_parser.add_argument("--title", default="mimo-delegate")
    run_parser.add_argument("--mimo-bin")
    run_parser.add_argument("--allow-plugins", action="store_true")
    run_parser.add_argument("--keep-session", action="store_true")
    run_parser.add_argument("--keep-workspace-metadata", action="store_true")
    run_parser.add_argument("--raw-log", type=Path)
    run_parser.add_argument(
        "--write-path",
        action="append",
        type=Path,
        default=[],
        help="Restrict workspace-write to this cwd-relative path; repeat for multiple paths",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "models":
        code, result = list_models(
            args.provider,
            args.mimo_bin,
            args.timeout,
            refresh=args.refresh,
            verbose=args.verbose,
        )
    else:
        prompt = args.prompt
        if args.prompt_file:
            prompt = args.prompt_file.expanduser().read_text(encoding="utf-8")
        assert prompt is not None
        code, result = run_delegate(
            prompt=prompt,
            cwd=args.cwd,
            model=args.model,
            agent=args.agent,
            permission_mode=args.permission_mode,
            timeout=args.timeout,
            settle_seconds=args.settle_seconds,
            result_idle_seconds=args.result_idle_seconds,
            require_handoff=not args.allow_freeform_result,
            title=args.title,
            mimo_bin=args.mimo_bin,
            allow_plugins=args.allow_plugins,
            keep_session=args.keep_session,
            keep_workspace_metadata=args.keep_workspace_metadata,
            raw_log=args.raw_log,
            write_paths=args.write_path,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
