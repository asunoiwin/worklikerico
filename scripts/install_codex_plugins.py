#!/usr/bin/env python3
"""Install the repository Codex marketplace and build MCP artifacts in its cache."""
from __future__ import annotations
import argparse, json, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKET = "worklikerico"
PLUGINS = ["codex-memory-pro", "codex-multi-agent", "design-test-loop"]

def run(args: list[str], env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, env=env, text=True, capture_output=True, check=check)

def marketplace_rows(text: str) -> dict[str, str]:
    rows = {}
    for line in text.splitlines()[1:]:
        columns = line.split(maxsplit=1)
        if len(columns) == 2:
            rows[columns[0]] = columns[1]
    return rows

def installed_identities(text: str) -> set[str]:
    return {
        line.split()[0]
        for line in text.splitlines()
        if "installed," in line and line.split()
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", type=Path, default=Path.home())
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()
    home = args.home.expanduser().resolve()
    codex_home = home / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(HOME=str(home), CODEX_HOME=str(codex_home))

    marketplaces = marketplace_rows(run(["codex", "plugin", "marketplace", "list"], env).stdout)
    listing = run(["codex", "plugin", "list"], env).stdout if MARKET in marketplaces else ""
    installed = installed_identities(listing)

    if args.remove:
        for name in reversed(PLUGINS):
            identity = f"{name}@{MARKET}"
            if identity in installed:
                run(["codex", "plugin", "remove", identity], env)
        if MARKET in marketplaces:
            run(["codex", "plugin", "marketplace", "remove", MARKET], env)
        print("removed worklikerico Codex plugins and marketplace")
        return 0

    if MARKET in marketplaces:
        if Path(marketplaces[MARKET]).resolve() != ROOT.resolve():
            raise RuntimeError(f"marketplace {MARKET} points to a different root: {marketplaces[MARKET]}")
    else:
        run(["codex", "plugin", "marketplace", "add", str(ROOT)], env)

    for name in PLUGINS:
        identity = f"{name}@{MARKET}"
        if identity in installed:
            run(["codex", "plugin", "remove", identity], env)
        run(["codex", "plugin", "add", identity], env)

    if not args.skip_build:
        manifest = json.loads((ROOT / "plugins/codex/codex-memory-pro/.codex-plugin/plugin.json").read_text())
        cache = codex_home / "plugins/cache" / MARKET / "codex-memory-pro" / manifest["version"]
        if not cache.is_dir():
            raise RuntimeError(f"Codex cache missing after install: {cache}")
        subprocess.run(["npm", "ci", "--legacy-peer-deps"], cwd=cache, env=env, check=True)
        subprocess.run(["npm", "run", "build"], cwd=cache, env=env, check=True)
        if not (cache / "dist/mcp-server.js").is_file():
            raise RuntimeError("MCP build did not create dist/mcp-server.js")
    print(run(["codex", "plugin", "list"], env).stdout, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
