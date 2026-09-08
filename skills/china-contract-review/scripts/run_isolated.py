#!/usr/bin/env python3
"""Fail-closed macOS sandbox launcher for the local contract inspector."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = SKILL_ROOT / "scripts" / "inspect_contract.py"
VALIDATOR = SKILL_ROOT / "scripts" / "validate_config.py"
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("china_contract_validate_config", VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("configuration validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scheme_string(value: Path | str) -> str:
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{escaped}"'


def _runtime_executable() -> Path:
    framework_binary = Path(sys.prefix) / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    if framework_binary.is_file():
        return framework_binary.resolve()
    return Path(sys.executable).resolve()


def _protected_data_roots() -> list[Path]:
    return [Path.home().resolve(), Path("/Volumes"), Path("/private/tmp"), Path("/private/var/tmp"), Path("/private/var/folders")]


def _sandbox_profile(input_path: Path, python_path: Path) -> str:
    runtime_root = Path(sys.prefix).resolve()
    protected_roots = _protected_data_roots()
    deny_rules = "\n".join(f"(deny file-read* (subpath {_scheme_string(path)}))" for path in protected_roots)
    return f"""(version 1)
(deny default)
(deny network*)
(allow process-exec (literal {_scheme_string(python_path)}))
(allow file-map-executable)
(allow sysctl-read)
(allow mach-lookup)
(allow file-read*)
{deny_rules}
(allow file-read*
  (subpath {_scheme_string(runtime_root)})
  (subpath {_scheme_string(SKILL_ROOT)})
  (literal {_scheme_string(input_path)})
  (literal \"/dev/null\"))
"""


def _read_config(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot read configuration: {type(exc).__name__}"]
    errors = _load_validator().validate(config)
    return config, errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the contract inspector inside a fail-closed local macOS sandbox.")
    parser.add_argument("input", type=Path, help="local .docx or .pdf file")
    parser.add_argument("--config", required=True, type=Path, help="validated local security configuration")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config, errors = _read_config(args.config.resolve())
    if errors or config is None:
        print(json.dumps({"status": "fail", "issues": [{"code": "CONFIG_REJECTED", "message": "Security configuration was rejected.", "count": len(errors)}]}))
        return 2
    if platform.system() != "Darwin" or not SANDBOX_EXEC.is_file():
        print(json.dumps({"status": "fail", "issues": [{"code": "ISOLATION_UNAVAILABLE", "message": "Approved macOS sandbox launcher is unavailable.", "count": 1}]}))
        return 2
    input_path = args.input.resolve()
    if not input_path.is_file():
        print(json.dumps({"status": "fail", "issues": [{"code": "FILE_UNREADABLE", "message": "Input file cannot be read.", "count": 1}]}))
        return 2
    runtime_root = Path(sys.prefix).resolve()
    if (
        not any(input_path.is_relative_to(root) for root in _protected_data_roots())
        or input_path.is_relative_to(SKILL_ROOT)
        or input_path.is_relative_to(runtime_root)
    ):
        print(json.dumps({"status": "fail", "issues": [{"code": "INPUT_LOCATION_UNSUPPORTED", "message": "Input must be inside a protected user, volume, or temporary-data root and outside the Skill/runtime directories.", "count": 1}]}))
        return 2

    limits = config["document_limits"]
    python_path = _runtime_executable()
    command = [
        str(SANDBOX_EXEC),
        "-p",
        _sandbox_profile(input_path, python_path),
        str(python_path),
        "-I",
        str(INSPECTOR),
        str(input_path),
        "--max-file-bytes", str(limits["max_file_bytes"]),
        "--max-zip-entries", str(limits["max_zip_entries"]),
        "--max-zip-uncompressed-bytes", str(limits["max_zip_uncompressed_bytes"]),
        "--max-pdf-pages", str(limits["max_pdf_pages"]),
        "--low-text-chars-per-page", str(limits["low_text_chars_per_page"]),
    ]
    clean_environment = {
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    try:
        completed = subprocess.run(command, env=clean_environment, check=False, capture_output=True, text=True)
    except OSError:
        print(json.dumps({"status": "fail", "issues": [{"code": "ISOLATION_LAUNCH_ERROR", "message": "Approved sandbox could not be launched.", "count": 1}]}))
        return 2
    if completed.returncode not in {0, 2, 3} or not completed.stdout.strip():
        print(json.dumps({"status": "fail", "issues": [{"code": "ISOLATION_RUNTIME_ERROR", "message": "Sandboxed inspector did not return a valid status.", "count": 1}]}))
        return 2
    print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
