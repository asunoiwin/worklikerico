#!/usr/bin/env python3
"""Install Claude plugin sources into an isolated per-user runtime tree."""
from __future__ import annotations
import argparse, os, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ["claude-memory-pro", "claude-autoagent", "design-test-loop"]
SKIP = {".git", "node_modules", "dist", "state", "baselines", "backups", ".DS_Store"}
MARKER = ".worklikerico-managed"

def copy_source(src: Path, dest: Path) -> None:
    if dest.exists():
        if not (dest / MARKER).is_file():
            raise RuntimeError(f"refusing to replace unmanaged directory: {dest}")
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*SKIP))
    (dest / MARKER).write_text("managed by worklikerico installer\n")

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", type=Path, default=Path.home())
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--plugin", action="append", dest="plugins")
    args = ap.parse_args(argv)
    selected = list(dict.fromkeys(args.plugins or PLUGINS))
    unknown = set(selected) - set(PLUGINS)
    if unknown:
        raise RuntimeError(f"unknown plugin(s): {', '.join(sorted(unknown))}")
    home = args.home.expanduser().resolve()
    stage = home / ".local/share/worklikerico/claude"
    local = home / ".claude/plugins/local"
    env = os.environ.copy()
    env["HOME"] = str(home)

    if args.remove:
        for name in selected:
            dest = local / name
            managed = stage / name
            if dest.is_symlink() and dest.resolve() == managed.resolve():
                dest.unlink()
            if managed.is_dir() and (managed / MARKER).is_file():
                shutil.rmtree(managed)
        print("removed worklikerico Claude plugin links and managed copies")
        return 0

    local.mkdir(parents=True, exist_ok=True)
    stage.mkdir(parents=True, exist_ok=True)
    for name in selected:
        src = ROOT / "plugins/claude" / name
        managed = stage / name
        copy_source(src, managed)
        if name == "claude-memory-pro" and not args.skip_build:
            subprocess.run(["npm", "ci", "--legacy-peer-deps"], cwd=managed, env=env, check=True)
            subprocess.run(["npm", "run", "build"], cwd=managed, env=env, check=True)
            if not (managed / "dist/mcp-server.js").is_file():
                raise RuntimeError("MCP build did not create dist/mcp-server.js")
        dest = local / name
        if dest.is_symlink() and dest.resolve() == managed.resolve():
            pass
        elif dest.exists() or dest.is_symlink():
            raise RuntimeError(f"refusing to replace existing path: {dest}")
        else:
            dest.symlink_to(managed, target_is_directory=True)
        print(f"installed {name} -> {dest}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
