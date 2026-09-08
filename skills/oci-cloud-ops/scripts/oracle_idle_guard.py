#!/usr/bin/env python3
"""Maintain bounded CPU and memory targets while yielding to real workloads."""

from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any


MAX_TARGET_PERCENT = 30.0
PAGE_SIZE = 4096


def percent(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= MAX_TARGET_PERCENT:
        raise argparse.ArgumentTypeError(
            f"target must be between 0 and {MAX_TARGET_PERCENT:g} percent"
        )
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def read_cpu_times(path: Path = Path("/proc/stat")) -> tuple[int, int]:
    fields = path.read_text(encoding="utf-8").splitlines()[0].split()
    if not fields or fields[0] != "cpu" or len(fields) < 6:
        raise RuntimeError(f"unexpected {path} format")
    values = [int(value) for value in fields[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def cpu_utilization(before: tuple[int, int], after: tuple[int, int]) -> float:
    total_delta = after[0] - before[0]
    idle_delta = after[1] - before[1]
    if total_delta <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / total_delta))


def next_cpu_duty(
    current_duty: float,
    observed_percent: float,
    target_percent: float,
    cpu_count: int,
) -> float:
    if target_percent <= 0:
        return 0.0
    processors = max(cpu_count, 1)
    estimated_guard_percent = current_duty * 100.0 / processors
    estimated_real_percent = max(0.0, observed_percent - estimated_guard_percent)
    desired_duty = max(
        0.0,
        min(1.0, (target_percent - estimated_real_percent) * processors / 100.0),
    )
    if desired_duty < current_duty:
        return desired_duty
    return min(1.0, current_duty + (desired_duty - current_duty) * 0.5)


def read_memory(path: Path = Path("/proc/meminfo")) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0]) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        raise RuntimeError(f"unexpected {path} format")
    return values["MemTotal"], values["MemAvailable"]


def desired_guard_memory(
    total: int,
    available: int,
    current_guard: int,
    target_percent: float,
    max_bytes: int,
) -> int:
    if target_percent <= 0:
        return 0
    used = max(0, total - available)
    non_guard_used = max(0, used - current_guard)
    target_used = int(total * target_percent / 100.0)
    return max(0, min(max_bytes, target_used - non_guard_used))


def memory_guard_limit(total: int, configured_mib: int) -> int:
    if configured_mib == 0:
        return total
    return min(total, configured_mib * 1024 * 1024)


def resize_buffer(buffer: bytearray, desired: int, max_step: int) -> None:
    desired = max(0, desired)
    if desired > len(buffer):
        grow = min(desired - len(buffer), max_step)
        old_size = len(buffer)
        buffer.extend(bytearray(grow))
        for offset in range(old_size, len(buffer), PAGE_SIZE):
            buffer[offset] = 1
    elif desired < len(buffer):
        del buffer[desired:]
        gc.collect()


def busy_wait(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    value = 0x12345678
    while time.monotonic() < deadline:
        value = ((value << 5) - value + 1) & 0xFFFFFFFF


def emit(event: str, **details: Any) -> None:
    print(json.dumps({"event": event, **details}, sort_keys=True), flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-target-percent", type=percent, default=25.0)
    parser.add_argument("--memory-target-percent", type=percent, default=0.0)
    parser.add_argument(
        "--memory-max-mib",
        type=int,
        default=0,
        help="additional memory ceiling in MiB; 0 uses the percentage target only",
    )
    parser.add_argument("--memory-adjust-mib", type=int, default=64)
    parser.add_argument("--cycle-seconds", type=positive_float, default=2.0)
    parser.add_argument("--report-interval", type=positive_float, default=60.0)
    parser.add_argument(
        "--run-seconds",
        type=positive_float,
        help="exit after this many seconds; intended for timer-driven E2 pulses",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.memory_max_mib < 0 or args.memory_adjust_mib < 1:
        parser.error("memory limits must be non-negative and adjustment must be positive")
    return args


def main() -> int:
    if sys.platform != "linux" or not Path("/proc/stat").exists():
        print("error: this guard requires Linux procfs", file=sys.stderr)
        return 2
    args = parse_args()
    stop = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    cpu_count = os.cpu_count() or 1
    duty = min(1.0, args.cpu_target_percent * cpu_count / 100.0)
    memory = bytearray()
    last_report = 0.0
    deadline = time.monotonic() + args.run_seconds if args.run_seconds else None
    try:
        while not stop:
            cycle_seconds = args.cycle_seconds
            if deadline is not None:
                remaining_runtime = deadline - time.monotonic()
                if remaining_runtime <= 0:
                    break
                cycle_seconds = min(cycle_seconds, remaining_runtime)
            total, available = read_memory()
            desired = desired_guard_memory(
                total,
                available,
                len(memory),
                args.memory_target_percent,
                memory_guard_limit(total, args.memory_max_mib),
            )
            try:
                resize_buffer(memory, desired, args.memory_adjust_mib * 1024 * 1024)
            except MemoryError:
                memory.clear()
                gc.collect()
                emit("memory_allocation_failed")

            before = read_cpu_times()
            busy_wait(cycle_seconds * duty)
            remaining = cycle_seconds * (1.0 - duty)
            if remaining > 0:
                time.sleep(remaining)
            observed = cpu_utilization(before, read_cpu_times())
            duty = next_cpu_duty(
                duty, observed, args.cpu_target_percent, cpu_count
            )
            now = time.monotonic()
            if args.once or now - last_report >= args.report_interval:
                emit(
                    "sample",
                    cpu_observed_percent=round(observed, 2),
                    cpu_target_percent=args.cpu_target_percent,
                    cpu_duty_percent=round(duty * 100, 2),
                    memory_guard_mib=round(len(memory) / 1024 / 1024, 2),
                    memory_target_percent=args.memory_target_percent,
                    network_activity="disabled",
                    run_seconds=args.run_seconds,
                )
                last_report = now
            if args.once:
                break
    finally:
        memory.clear()
        gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
