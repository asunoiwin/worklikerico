#!/usr/bin/env python3
"""List, install, and update WorkLikeRico capabilities by platform."""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog/assets.json"
PLATFORMS = ("codex", "claude", "agents", "hermes")
PLUGIN_INSTALLERS = {
    "codex": ROOT / "scripts/install_codex_plugins.py",
    "claude": ROOT / "scripts/install_claude_plugins.py",
}
SKILL_DESCRIPTIONS = {
    "repository-core": "Rico 核心工作协议",
    "self-built": "自研独立技能",
    "claude-workflow-candidate": "Claude 工作流",
}


class ManageError(RuntimeError):
    pass


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text())


def unique(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys(values or ()))


def describe(item: dict, kind: str) -> str:
    if item.get("description"):
        return item["description"]
    if kind == "skill":
        return SKILL_DESCRIPTIONS.get(item.get("classification"), "技能")
    return f"{item.get('family', '平台')} 插件"


def list_capabilities(catalog: dict, platform: str | None) -> None:
    rows = []
    for item in catalog["skills"]:
        platforms = item["installTargets"]
        if platform and platform not in platforms:
            continue
        rows.append((item["name"], "skill", ",".join(platforms), describe(item, "skill")))
    for item in catalog["plugins"]:
        if platform and platform != item["platform"]:
            continue
        rows.append((item["name"], "plugin", item["platform"], describe(item, "plugin")))

    print("NAME\tTYPE\tPLATFORMS\tDESCRIPTION")
    for row in rows:
        print("\t".join(row))
    skill_count = sum(row[1] == "skill" for row in rows)
    plugin_count = sum(row[1] == "plugin" for row in rows)
    print(
        f"TOTAL\t{len(rows)} repository entries\t"
        f"{skill_count} skills\t{plugin_count} plugins"
    )


def select_modules(catalog: dict, platform: str, skills: list[str], plugins: list[str]) -> tuple[list[str], list[str]]:
    known_skills = {item["name"] for item in catalog["skills"]}
    known_plugins = {item["name"] for item in catalog["plugins"]}
    compatible_skills = {
        item["name"] for item in catalog["skills"] if platform in item["installTargets"]
    }
    compatible_plugins = {
        item["name"] for item in catalog["plugins"] if platform == item["platform"]
    }

    unknown_skills = set(skills) - known_skills
    unknown_plugins = set(plugins) - known_plugins
    if unknown_skills:
        raise ManageError(f"unknown skill(s): {', '.join(sorted(unknown_skills))}")
    if unknown_plugins:
        raise ManageError(f"unknown plugin(s): {', '.join(sorted(unknown_plugins))}")

    incompatible_skills = set(skills) - compatible_skills
    incompatible_plugins = set(plugins) - compatible_plugins
    if incompatible_skills:
        raise ManageError(
            f"skill(s) do not support {platform}: {', '.join(sorted(incompatible_skills))}"
        )
    if incompatible_plugins:
        raise ManageError(
            f"plugin(s) do not support {platform}: {', '.join(sorted(incompatible_plugins))}"
        )

    filtered = bool(skills or plugins)
    if filtered:
        return skills, plugins
    return sorted(compatible_skills), sorted(compatible_plugins)


def install_commands(
    platform: str,
    skills: list[str],
    plugins: list[str],
    home: Path | None,
) -> list[list[str]]:
    commands = []
    if skills:
        command = [sys.executable, str(ROOT / "scripts/install_skills.py"), "--target", platform]
        for name in skills:
            command.extend(("--skill", name))
        if home:
            command.extend(("--home", str(home)))
        commands.append(command)

    if plugins:
        installer = PLUGIN_INSTALLERS.get(platform)
        if not installer:
            raise ManageError(f"platform {platform} does not support plugins")
        command = [sys.executable, str(installer)]
        for name in plugins:
            command.extend(("--plugin", name))
        if home:
            command.extend(("--home", str(home)))
        commands.append(command)
    return commands


def run_command(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=capture,
        check=False,
    )


def execute_install(commands: list[list[str]]) -> int:
    for command in commands:
        print(f"install: {shlex.join(command)}")
        result = run_command(command)
        if result.returncode:
            print(f"install: failed ({result.returncode})", file=sys.stderr)
            return result.returncode
    print("install: completed")
    return 0


def update_source() -> int:
    status = run_command(["git", "status", "--porcelain"], capture=True)
    if status.returncode:
        print("source-sync: unable to inspect worktree", file=sys.stderr)
        return status.returncode
    if status.stdout.strip():
        print("source-sync: worktree is not clean; update stopped", file=sys.stderr)
        return 2

    print("source-sync: git pull --ff-only")
    pulled = run_command(["git", "pull", "--ff-only"])
    if pulled.returncode:
        print(f"source-sync: failed ({pulled.returncode}); install not started", file=sys.stderr)
        return pulled.returncode
    print("source-sync: completed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list capability names and summaries")
    list_parser.add_argument("--platform", choices=PLATFORMS)

    for name in ("install", "update"):
        command = subparsers.add_parser(name)
        command.add_argument("--platform", choices=PLATFORMS, required=True)
        command.add_argument("--skill", action="append", dest="skills")
        command.add_argument("--plugin", action="append", dest="plugins")
        command.add_argument("--home", type=Path)
        command.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = load_catalog()
    if args.command == "list":
        list_capabilities(catalog, args.platform)
        return 0

    skills = unique(args.skills)
    plugins = unique(args.plugins)
    try:
        skills, plugins = select_modules(catalog, args.platform, skills, plugins)
        commands = install_commands(args.platform, skills, plugins, args.home)
    except ManageError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.dry_run:
        if args.command == "update":
            print("source-sync: git pull --ff-only")
        for command in commands:
            print(f"install: {shlex.join(command)}")
        print("dry-run: no commands executed")
        return 0

    if args.command == "update":
        result = update_source()
        if result:
            return result
        try:
            catalog = load_catalog()
            skills, plugins = select_modules(
                catalog,
                args.platform,
                unique(args.skills),
                unique(args.plugins),
            )
            commands = install_commands(args.platform, skills, plugins, args.home)
        except ManageError as exc:
            print(f"source-sync: completed; install plan invalid: {exc}", file=sys.stderr)
            return 2
    return execute_install(commands)


if __name__ == "__main__":
    raise SystemExit(main())
