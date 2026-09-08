#!/usr/bin/env python3
"""Install, inspect, or remove the bounded Oracle idle guard on Linux."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Optional, Tuple


SERVICE_NAME = "oracle-idle-guard.service"
TIMER_NAME = "oracle-idle-guard.timer"
DAEMON_RELATIVE = Path("usr/local/lib/oracle-idle-guard/oracle_idle_guard.py")
UNIT_RELATIVE = Path("etc/systemd/system") / SERVICE_NAME
TIMER_RELATIVE = Path("etc/systemd/system") / TIMER_NAME
SOURCE_DAEMON = Path(__file__).resolve().with_name("oracle_idle_guard.py")
MANAGED_MARKER = "# Managed by oracle-cloud-ops skill"
E2_CPU_TARGET = 25.0
E2_RUN_SECONDS = 900
E2_INTERVAL = "2h"
A1_CPU_TARGET = 0.0
A1_MEMORY_TARGET = 25.0


def target_percent(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 30:
        raise argparse.ArgumentTypeError("target must be between 0 and 30 percent")
    return parsed


def unit_text(shape: str, cpu_target: float, memory_target: float) -> str:
    run_limit = f" --run-seconds {E2_RUN_SECONDS}" if shape == "e2" else ""
    restart = "no" if shape == "e2" else "on-failure"
    cpu_quota = "50%" if shape == "e2" else "100%"
    install_section = "" if shape == "e2" else "\n[Install]\nWantedBy=multi-user.target\n"
    return f"""{MANAGED_MARKER}
# Shape: {shape}
[Unit]
Description=Bounded Oracle Always Free idle guard
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/lib/oracle-idle-guard/oracle_idle_guard.py --cpu-target-percent {cpu_target:g} --memory-target-percent {memory_target:g}{run_limit}
Restart={restart}
RestartSec=10s
Nice=19
OOMScoreAdjust=1000
CPUWeight=1
CPUQuota={cpu_quota}
MemoryHigh=30%
MemoryMax=35%
IOWeight=1
DynamicUser=yes
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
PrivateNetwork=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
RestrictRealtime=yes
RestrictAddressFamilies=AF_UNIX
{install_section}
"""


def timer_text() -> str:
    return f"""{MANAGED_MARKER}
# Shape: e2
[Unit]
Description=Schedule sparse Oracle E2 idle-guard pulses

[Timer]
OnBootSec=15min
OnUnitActiveSec={E2_INTERVAL}
RandomizedDelaySec=5min
AccuracySec=1min
Persistent=true
Unit={SERVICE_NAME}

[Install]
WantedBy=timers.target
"""


def refuse_symlink(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError(f"refusing symlink target: {path}")


def write_if_absent_or_equal(path: Path, content: bytes, mode: int) -> None:
    refuse_symlink(path)
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError(f"refusing to overwrite different existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    refuse_symlink(path.parent)
    path.write_bytes(content)
    path.chmod(mode)


def validate_target(path: Path, content: bytes) -> None:
    refuse_symlink(path)
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError(f"refusing to overwrite different existing file: {path}")


def managed_unit_config(path: Path) -> Optional[Tuple[str, float, float]]:
    if not path.is_file() or path.is_symlink():
        return None
    body = path.read_text(encoding="utf-8")
    shape_match = re.search(r"^# Shape: (a1|e2)$", body, re.MULTILINE)
    command_match = re.search(
        r"^ExecStart=/usr/bin/python3 /usr/local/lib/oracle-idle-guard/"
        r"oracle_idle_guard\.py --cpu-target-percent ([0-9]+(?:\.[0-9]+)?) "
        r"--memory-target-percent ([0-9]+(?:\.[0-9]+)?)"
        r"(?: --run-seconds [0-9]+)?$",
        body,
        re.MULTILINE,
    )
    if not shape_match or not command_match:
        return None
    shape = shape_match.group(1)
    cpu_target = float(command_match.group(1))
    memory_target = float(command_match.group(2))
    expected = {
        "e2": (E2_CPU_TARGET, 0.0),
        "a1": (A1_CPU_TARGET, A1_MEMORY_TARGET),
    }[shape]
    if (cpu_target, memory_target) != expected:
        return None
    if body != unit_text(shape, cpu_target, memory_target):
        return None
    return shape, cpu_target, memory_target


def managed_timer_valid(path: Path) -> bool:
    return (
        path.is_file()
        and not path.is_symlink()
        and path.read_text(encoding="utf-8") == timer_text()
    )


def systemctl(*args: str) -> None:
    subprocess.run(["systemctl", *args], check=True)


def systemctl_try(*args: str) -> int:
    return subprocess.run(["systemctl", *args], check=False).returncode


def require_systemctl_for_live(args: argparse.Namespace, root: Path) -> None:
    if root == Path("/") and args.no_systemctl:
        raise RuntimeError("--no-systemctl is only allowed with a sandbox --root")


def paths(root: Path) -> tuple[Path, Path, Path]:
    return root / DAEMON_RELATIVE, root / UNIT_RELATIVE, root / TIMER_RELATIVE


def install(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    if not args.dry_run:
        require_systemctl_for_live(args, root)
    daemon, unit, timer = paths(root)
    memory_target = args.memory_target
    if memory_target is None:
        memory_target = A1_MEMORY_TARGET if args.shape == "a1" else 0.0
    cpu_target = args.cpu_target
    if cpu_target is None:
        cpu_target = E2_CPU_TARGET if args.shape == "e2" else A1_CPU_TARGET
    if args.shape == "e2" and (
        cpu_target != E2_CPU_TARGET or memory_target != 0.0
    ):
        raise RuntimeError(
            f"E2 mode uses fixed {E2_CPU_TARGET:g}% CPU and 0% memory targets"
        )
    if args.shape == "a1" and (
        cpu_target != A1_CPU_TARGET or memory_target != A1_MEMORY_TARGET
    ):
        raise RuntimeError(
            "A1 mode uses fixed 0% CPU and 25% total-memory targets"
        )
    plan = {
        "action": "install",
        "shape": args.shape,
        "cpu_target_percent": cpu_target,
        "memory_target_percent": memory_target,
        "daemon": str(daemon),
        "unit": str(unit),
        "timer": str(timer) if args.shape == "e2" else None,
        "e2_pulse_seconds": E2_RUN_SECONDS if args.shape == "e2" else None,
        "e2_interval": E2_INTERVAL if args.shape == "e2" else None,
        "network_activity": "disabled",
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    if args.dry_run:
        return
    if root == Path("/") and os.geteuid() != 0:
        raise RuntimeError("install to / requires root")
    daemon_content = SOURCE_DAEMON.read_bytes()
    unit_content = unit_text(args.shape, cpu_target, memory_target).encode()
    planned = [(daemon, daemon_content, 0o755), (unit, unit_content, 0o644)]
    if args.shape == "e2":
        planned.append((timer, timer_text().encode(), 0o644))
    elif timer.exists():
        raise RuntimeError(f"remove the existing E2 timer before installing A1 mode: {timer}")
    for path, content, _mode in planned:
        validate_target(path, content)
    created: list[Path] = []
    activation_target = TIMER_NAME if args.shape == "e2" else SERVICE_NAME
    activation_started = False
    try:
        for path, content, mode in planned:
            if not path.exists():
                created.append(path)
            write_if_absent_or_equal(path, content, mode)
        if root == Path("/") and not args.no_systemctl:
            systemctl("daemon-reload")
            activation_started = True
            systemctl("enable", "--now", activation_target)
    except Exception as exc:
        if activation_started and systemctl_try(
            "disable", "--now", activation_target
        ) != 0:
            raise RuntimeError(
                "activation failed and rollback failed; managed files were retained"
            ) from exc
        for path in reversed(created):
            path.unlink(missing_ok=True)
        if root == Path("/") and activation_started:
            systemctl_try("daemon-reload")
        raise


def uninstall(args: argparse.Namespace) -> None:
    root = args.root.resolve()
    if not args.dry_run:
        require_systemctl_for_live(args, root)
    daemon, unit, timer = paths(root)
    print(json.dumps({"action": "uninstall", "daemon": str(daemon), "unit": str(unit), "timer": str(timer)}))
    if args.dry_run:
        return
    if root == Path("/") and os.geteuid() != 0:
        raise RuntimeError("uninstall from / requires root")
    refuse_symlink(daemon)
    refuse_symlink(unit)
    refuse_symlink(timer)
    unit_config = managed_unit_config(unit) if unit.exists() else None
    if unit.exists() and unit_config is None:
        raise RuntimeError(f"refusing to remove modified or unmanaged unit: {unit}")
    if daemon.exists() and daemon.read_bytes() != SOURCE_DAEMON.read_bytes():
        raise RuntimeError(f"refusing to remove modified daemon: {daemon}")
    if timer.exists() and not managed_timer_valid(timer):
        raise RuntimeError(f"refusing to remove modified or unmanaged timer: {timer}")
    if root == Path("/") and not args.no_systemctl:
        installed_units = []
        if timer.exists() or (unit_config is not None and unit_config[0] == "e2"):
            installed_units.append(TIMER_NAME)
        if daemon.exists() or unit.exists() or timer.exists():
            installed_units.append(SERVICE_NAME)
        if installed_units:
            systemctl("disable", "--now", *installed_units)
    timer.unlink(missing_ok=True)
    unit.unlink(missing_ok=True)
    daemon.unlink(missing_ok=True)
    try:
        daemon.parent.rmdir()
    except OSError:
        pass
    if root == Path("/") and not args.no_systemctl:
        systemctl("daemon-reload")


def status(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    require_systemctl_for_live(args, root)
    daemon, unit, timer = paths(root)
    daemon_valid = (
        daemon.is_file()
        and not daemon.is_symlink()
        and daemon.read_bytes() == SOURCE_DAEMON.read_bytes()
    )
    unit_config = managed_unit_config(unit)
    unit_valid = unit_config is not None
    shape = unit_config[0] if unit_config else None
    timer_valid = managed_timer_valid(timer)
    complete = daemon_valid and unit_valid and shape in ("a1", "e2")
    if shape == "e2":
        complete = complete and timer_valid
    elif timer.exists():
        complete = False
    print(json.dumps({"daemon_valid": daemon_valid, "unit_valid": unit_valid, "timer_valid": timer_valid, "shape": shape}))
    if not complete:
        return 3
    if root == Path("/") and not args.no_systemctl:
        return subprocess.run(
            ["systemctl", "is-active", TIMER_NAME if shape == "e2" else SERVICE_NAME],
            check=False,
        ).returncode
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "status", "uninstall"))
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--shape", choices=("a1", "e2"))
    parser.add_argument("--cpu-target", type=target_percent)
    parser.add_argument("--memory-target", type=target_percent)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-systemctl", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.action == "install" and not args.shape:
        parser.error("install requires --shape a1 or --shape e2")
    if args.shape == "e2" and args.memory_target not in (None, 0.0):
        parser.error("memory occupancy is not used for E2 idle classification")
    return args


def main() -> int:
    args = parse_args()
    if (
        sys.platform != "linux"
        and args.root.resolve() == Path("/")
        and not args.dry_run
    ):
        print("error: live installation requires Linux", file=sys.stderr)
        return 2
    try:
        if args.action == "install":
            install(args)
            return 0
        if args.action == "uninstall":
            uninstall(args)
            return 0
        return status(args)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
