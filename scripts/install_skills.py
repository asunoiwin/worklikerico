#!/usr/bin/env python3
"""Install repository skills as safe, reversible symlinks."""
from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "agents": ".agents/skills",
    "claude": ".claude/skills",
    "codex": ".codex/skills",
    "hermes": ".config/worklikerico/hermes/skills",
}


def same_file(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return False


def link(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        if same_file(dest, src):
            return "unchanged"
        raise RuntimeError(f"refusing to replace foreign symlink: {dest}")
    if dest.exists():
        raise RuntimeError(f"refusing to replace existing path: {dest}")
    dest.symlink_to(src, target_is_directory=True)
    return "linked"

def unlink(src: Path, dest: Path) -> str:
    if not dest.is_symlink():
        return "absent"
    if not same_file(dest, src):
        raise RuntimeError(f"refusing to remove foreign symlink: {dest}")
    dest.unlink()
    return "removed"


def preflight_link(src: Path, dest: Path) -> None:
    if dest.is_symlink():
        if same_file(dest, src):
            return
        raise RuntimeError(f"refusing to replace foreign symlink: {dest}")
    if dest.exists():
        raise RuntimeError(f"refusing to replace existing path: {dest}")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", type=Path, default=Path.home())
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--skill", action="append", dest="skills")
    ap.add_argument("--target", action="append", choices=TARGETS, dest="targets")
    args = ap.parse_args()
    assets = json.loads((ROOT / "catalog/assets.json").read_text())
    selected_skills = set(args.skills or ())
    known_skills = {item["name"] for item in assets["skills"]}
    unknown_skills = selected_skills - known_skills
    if unknown_skills:
        raise RuntimeError(f"unknown skill(s): {', '.join(sorted(unknown_skills))}")
    selected_targets = set(args.targets or ())
    if selected_skills and selected_targets:
        unsupported = {
            item["name"]
            for item in assets["skills"]
            if item["name"] in selected_skills
            and not (set(item["installTargets"]) & selected_targets)
        }
        if unsupported:
            raise RuntimeError(
                "skill(s) do not support selected target(s): "
                f"{', '.join(sorted(unsupported))}"
            )
    operations = []
    for item in assets["skills"]:
        if selected_skills and item["name"] not in selected_skills:
            continue
        src = ROOT / item["path"]
        if not (src / "SKILL.md").is_file():
            raise RuntimeError(f"missing SKILL.md: {src}")
        for target in item["installTargets"]:
            if selected_targets and target not in selected_targets:
                continue
            dest = args.home.expanduser().resolve() / TARGETS[target] / item["name"]
            operations.append((src, dest))

    if not args.remove:
        for src, dest in operations:
            preflight_link(src, dest)

    changed = 0
    for src, dest in operations:
        result = unlink(src, dest) if args.remove else link(src, dest)
        changed += result in {"linked", "removed"}
        print(f"{result:9} {dest}")
    print(f"completed: {changed} path(s) changed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
