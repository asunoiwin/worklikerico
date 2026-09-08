#!/usr/bin/env python3
"""Install repository skills as safe, reversible symlinks."""
from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"agents": ".agents/skills", "claude": ".claude/skills", "codex": ".codex/skills"}

def link(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        if dest.resolve() == src.resolve():
            return "unchanged"
        raise RuntimeError(f"refusing to replace foreign symlink: {dest}")
    if dest.exists():
        raise RuntimeError(f"refusing to replace existing path: {dest}")
    dest.symlink_to(src, target_is_directory=True)
    return "linked"

def unlink(src: Path, dest: Path) -> str:
    if not dest.is_symlink():
        return "absent"
    if dest.resolve() != src.resolve():
        raise RuntimeError(f"refusing to remove foreign symlink: {dest}")
    dest.unlink()
    return "removed"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", type=Path, default=Path.home())
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    assets = json.loads((ROOT / "catalog/assets.json").read_text())
    changed = 0
    for item in assets["skills"]:
        src = ROOT / item["path"]
        if not (src / "SKILL.md").is_file():
            raise RuntimeError(f"missing SKILL.md: {src}")
        for target in item["installTargets"]:
            dest = args.home.expanduser().resolve() / TARGETS[target] / item["name"]
            result = unlink(src, dest) if args.remove else link(src, dest)
            changed += result in {"linked", "removed"}
            print(f"{result:9} {dest}")
    print(f"completed: {changed} path(s) changed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
