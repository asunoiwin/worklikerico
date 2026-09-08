#!/usr/bin/env python3
"""Render a macOS LaunchAgent for one bounded OCI capacity retry job."""

from __future__ import annotations

import argparse
from pathlib import Path
import plistlib
import re


LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


def absolute(path: Path, label: str) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return str(resolved)


def build_arguments(args: argparse.Namespace) -> list[str]:
    command = [
        absolute(args.python_bin, "Python"),
        absolute(args.retry_script, "retry script"),
        args.mode,
        "--oci-bin",
        absolute(args.oci_bin, "OCI binary"),
        "--config-file",
        absolute(args.config_file, "OCI config"),
        "--profile",
        args.profile,
        "--state-file",
        absolute(args.state_file, "state file"),
        "--max-attempts",
        str(args.max_attempts),
        "--once",
    ]
    if args.region:
        command.extend(["--region", args.region])
    if args.mode == "start":
        command.extend(["--instance-id", args.instance_id])
    else:
        command.extend(["--request-file", absolute(args.request_file, "request file")])
    return command


def build_plist(args: argparse.Namespace) -> dict:
    if not LABEL_PATTERN.fullmatch(args.label):
        raise ValueError("label contains unsupported characters")
    return {
        "Label": args.label,
        "ProgramArguments": build_arguments(args),
        "RunAtLoad": True,
        "StartInterval": args.interval,
        "ProcessType": "Background",
        "StandardOutPath": absolute(args.stdout, "stdout log"),
        "StandardErrorPath": absolute(args.stderr, "stderr log"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("start", "launch"))
    parser.add_argument("--label", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region")
    parser.add_argument("--config-file", type=Path, default=Path("~/.oci/config"))
    parser.add_argument("--oci-bin", type=Path, default=Path("/usr/local/bin/oci"))
    parser.add_argument("--python-bin", type=Path, default=Path("/usr/bin/python3"))
    parser.add_argument(
        "--retry-script",
        type=Path,
        default=Path(__file__).resolve().with_name("oci_capacity_retry.py"),
    )
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--max-attempts", type=int, default=1440)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--instance-id")
    target.add_argument("--request-file", type=Path)
    args = parser.parse_args()
    if args.interval < 60:
        parser.error("--interval must be at least 60 seconds")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be positive")
    if args.mode == "start" and not args.instance_id:
        parser.error("start mode requires --instance-id")
    if args.mode == "launch" and not args.request_file:
        parser.error("launch mode requires --request-file")
    return args


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        plistlib.dump(build_plist(args), handle, sort_keys=False)
    output.chmod(0o600)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
