#!/usr/bin/env python3
"""Run bounded OCI START or LAUNCH retries without duplicate launch requests."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import uuid


CAPACITY_PATTERNS = ("out of host capacity", "outofhostcapacity")
FATAL_PATTERNS = (
    "quotaexceeded",
    "limitexceeded",
    "notauthorized",
    "not authorized",
    "notauthenticated",
    "invalidparameter",
    "invalid parameter",
    "invalid image",
    "incompatible image",
    "shape is not compatible",
    "cannotparse",
    "404 not found",
)
AMBIGUOUS_PATTERNS = (
    "toomanyrequests",
    "too many requests",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection refused",
    "temporary failure",
    "serviceunavailable",
    "internalerror",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
)
TERMINAL_STATUSES = {"success", "fatal", "exhausted"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(status: str, **fields: Any) -> None:
    payload = {"time": utc_now(), "status": status, **fields}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--region")
    parser.add_argument("--config-file", type=Path, default=Path("~/.oci/config"))
    parser.add_argument("--oci-bin", default="oci")
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, required=True)
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bounded OCI capacity retry for one START or one LAUNCH job."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)
    launch = subparsers.add_parser("launch", parents=[common_parser()])
    launch.add_argument("--request-file", type=Path, required=True)
    start = subparsers.add_parser("start", parents=[common_parser()])
    start.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1")
    if args.interval_seconds < 60:
        parser.error("--interval-seconds cannot be lower than 60")
    if args.mode == "start" and not args.instance_id.startswith("ocid1.instance."):
        parser.error("--instance-id is not an OCI instance OCID")
    return args


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_launch_file(path: Path) -> str:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"launch request file does not exist: {path}")
    raw = path.read_bytes()
    if b"-----BEGIN " in raw and b"PRIVATE KEY-----" in raw:
        raise ValueError("launch request contains a PEM private key")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"launch request is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("launch request must be a JSON object")
    return hashlib.sha256(raw).hexdigest()


def job_fingerprint(args: argparse.Namespace) -> str:
    if args.mode == "launch":
        target = validate_launch_file(args.request_file)
    else:
        target = hashlib.sha256(args.instance_id.encode()).hexdigest()
    config_hash = file_sha256(args.config_file) if args.config_file.is_file() else None
    identity = {
        "mode": args.mode,
        "target": target,
        "profile": args.profile,
        "region": args.region,
        "config_file": str(args.config_file),
        "config_hash": config_hash,
        "max_attempts": args.max_attempts,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def initial_state(args: argparse.Namespace, fingerprint: str) -> dict[str, Any]:
    return {
        "version": 2,
        "mode": args.mode,
        "job_fingerprint": fingerprint,
        "status": "pending",
        "attempts": 0,
        "pending_retry_token": None,
        "instance_id": args.instance_id if args.mode == "start" else None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "last_classification": None,
        "last_error": None,
        "last_request_id": None,
    }


def load_state(path: Path, args: argparse.Namespace, fingerprint: str) -> dict[str, Any]:
    if not path.exists():
        return initial_state(args, fingerprint)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read state file: {exc}") from exc
    if state.get("version") != 2 or state.get("mode") != args.mode:
        raise ValueError("state file belongs to another job or unsupported version")
    if state.get("job_fingerprint") != fingerprint:
        raise ValueError("target, profile, region, or OCI config changed; use a new state file")
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp, path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists():
            temp.unlink()


def cli_base(args: argparse.Namespace) -> list[str]:
    command = [
        args.oci_bin,
        "--config-file",
        str(args.config_file.expanduser().resolve()),
        "--profile",
        args.profile,
    ]
    if args.region:
        command.extend(["--region", args.region])
    return command


def run_cli(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout="",
            stderr="OCI CLI timed out after 120 seconds; request result is unknown",
        )


def parse_json_output(output: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def response_data(parsed: dict[str, Any] | None) -> dict[str, Any]:
    if not parsed:
        return {}
    data = parsed.get("data", parsed)
    return data if isinstance(data, dict) else {}


def extract_error(stderr: str) -> tuple[str, str | None]:
    code = re.search(r'["\']code["\']\s*:\s*["\']([^"\']+)', stderr, re.I)
    message = re.search(r'["\']message["\']\s*:\s*["\']([^"\']+)', stderr, re.I)
    request_id = re.search(
        r'(?:opc-request-id|request[_ -]?id)["\']?\s*[:=]\s*["\']?([^\s,"\']+)',
        stderr,
        re.I,
    )
    if code or message:
        summary = ": ".join(
            item.group(1).strip() for item in (code, message) if item is not None
        )
    else:
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        summary = lines[-1] if lines else "OCI CLI returned an error without details"
    summary = re.sub(r"-----BEGIN .*?PRIVATE KEY-----", "[REDACTED]", summary, flags=re.I)
    return summary[:500], request_id.group(1)[:200] if request_id else None


def classify_failure(stderr: str) -> str:
    lowered = stderr.lower()
    if any(pattern in lowered for pattern in CAPACITY_PATTERNS):
        return "capacity"
    if any(pattern in lowered for pattern in FATAL_PATTERNS):
        return "fatal"
    if any(pattern in lowered for pattern in AMBIGUOUS_PATTERNS):
        return "ambiguous"
    return "fatal"


def instance_state(args: argparse.Namespace) -> tuple[str | None, str | None, str | None]:
    command = cli_base(args) + [
        "compute",
        "instance",
        "get",
        "--instance-id",
        args.instance_id,
    ]
    completed = run_cli(command)
    if completed.returncode != 0:
        summary, request_id = extract_error(completed.stderr)
        return None, summary, request_id
    data = response_data(parse_json_output(completed.stdout))
    state = data.get("lifecycle-state") or data.get("lifecycle_state")
    return str(state).upper() if state else None, None, None


def launch_once(
    args: argparse.Namespace, state: dict[str, Any]
) -> tuple[str, str | None, str | None, str | None]:
    token = state.get("pending_retry_token")
    if not token:
        raise ValueError("launch retry token was not persisted before the request")
    command = cli_base(args) + [
        "compute",
        "instance",
        "launch",
        "--from-json",
        f"file://{args.request_file.expanduser().resolve()}",
        "--opc-retry-token",
        token,
    ]
    completed = run_cli(command)
    if completed.returncode == 0:
        data = response_data(parse_json_output(completed.stdout))
        instance_id = data.get("id")
        if isinstance(instance_id, str) and instance_id.startswith("ocid1.instance."):
            return "success", None, None, instance_id
        return "ambiguous", "launch was accepted but no instance OCID was returned", None, None
    summary, request_id = extract_error(completed.stderr)
    return classify_failure(completed.stderr), summary, request_id, None


def start_once(
    args: argparse.Namespace,
) -> tuple[str, str | None, str | None, str | None]:
    lifecycle, error, request_id = instance_state(args)
    if error:
        return classify_failure(error), error, request_id, None
    if lifecycle == "RUNNING":
        return "success", None, None, args.instance_id
    if lifecycle in {"STARTING", "STOPPING"}:
        return "observe", f"instance is {lifecycle}", None, None
    if lifecycle != "STOPPED":
        return "fatal", f"instance state {lifecycle or 'UNKNOWN'} is not startable", None, None
    command = cli_base(args) + [
        "compute",
        "instance",
        "action",
        "--instance-id",
        args.instance_id,
        "--action",
        "START",
    ]
    completed = run_cli(command)
    if completed.returncode == 0:
        lifecycle, error, request_id = instance_state(args)
        if error:
            return classify_failure(error), error, request_id, None
        if lifecycle == "RUNNING":
            return "success", None, None, args.instance_id
        if lifecycle in {"STARTING", "STOPPED"}:
            return "observe", f"START accepted; instance is {lifecycle}", None, None
        return "fatal", f"START accepted but instance state is {lifecycle or 'UNKNOWN'}", None, None
    summary, request_id = extract_error(completed.stderr)
    return classify_failure(completed.stderr), summary, request_id, None


def run_tick(args: argparse.Namespace, state: dict[str, Any], state_path: Path) -> int:
    if state.get("status") in TERMINAL_STATUSES:
        emit(
            str(state["status"]),
            attempts=state.get("attempts"),
            instance_id=state.get("instance_id"),
            message="job already reached a terminal state",
        )
        return 0 if state["status"] == "success" else 2
    if int(state.get("attempts", 0)) >= args.max_attempts:
        state["status"] = "exhausted"
        save_state(state_path, state)
        emit("exhausted", attempts=state["attempts"])
        return 2

    state["attempts"] = int(state.get("attempts", 0)) + 1
    state["last_error"] = None
    state["last_request_id"] = None
    if args.mode == "launch" and not state.get("pending_retry_token"):
        state["pending_retry_token"] = str(uuid.uuid4())
    save_state(state_path, state)

    if args.mode == "launch":
        classification, error, request_id, instance_id = launch_once(args, state)
    else:
        classification, error, request_id, instance_id = start_once(args)

    state["last_classification"] = classification
    state["last_error"] = error
    state["last_request_id"] = request_id

    if classification == "success":
        state["status"] = "success"
        state["instance_id"] = instance_id
        state["pending_retry_token"] = None
        save_state(state_path, state)
        emit("success", attempts=state["attempts"], instance_id=instance_id)
        return 0

    if classification == "fatal":
        state["status"] = "fatal"
        save_state(state_path, state)
        emit("fatal", attempts=state["attempts"], error=error, request_id=request_id)
        return 2

    if classification == "capacity":
        state["pending_retry_token"] = None
    save_state(state_path, state)
    emit(
        "pending",
        attempts=state["attempts"],
        classification=classification,
        error=error,
        request_id=request_id,
    )
    return 75


def dry_run(args: argparse.Namespace, fingerprint: str) -> int:
    details: dict[str, Any] = {
        "mode": args.mode,
        "profile": args.profile,
        "region": args.region,
        "state_file": str(args.state_file.expanduser().resolve()),
        "job_fingerprint": fingerprint,
        "max_attempts": args.max_attempts,
        "interval_seconds": args.interval_seconds,
        "once": args.once,
    }
    if args.mode == "launch":
        details["request_file"] = str(args.request_file.expanduser().resolve())
    else:
        details["instance_id_suffix"] = args.instance_id[-12:]
    emit("dry-run", **details)
    return 0


def main() -> int:
    args = parse_args()
    args.config_file = args.config_file.expanduser().resolve()
    args.state_file = args.state_file.expanduser().resolve()
    if args.mode == "launch":
        args.request_file = args.request_file.expanduser().resolve()
    try:
        if args.config_file.is_file():
            if args.config_file.stat().st_mode & 0o077 and not args.dry_run:
                raise ValueError("OCI config file must not be group/world accessible")
        elif not args.dry_run:
            raise ValueError(f"OCI config file does not exist: {args.config_file}")
        fingerprint = job_fingerprint(args)
        if args.dry_run:
            return dry_run(args, fingerprint)

        lock_path = args.state_file.with_suffix(args.state_file.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_handle:
            os.chmod(lock_path, 0o600)
            try:
                fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                emit("locked", message="another retry process owns this job")
                return 75

            while True:
                state = load_state(args.state_file, args, fingerprint)
                result = run_tick(args, state, args.state_file)
                if result != 75 or args.once:
                    return 0 if result == 75 and args.once else result
                time.sleep(args.interval_seconds)
    except (ValueError, OSError) as exc:
        emit("fatal", error=str(exc))
        return 2
    except KeyboardInterrupt:
        emit("stopped", message="interrupted by operator")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
