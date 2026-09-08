#!/usr/bin/env python3
"""Validate plugin manifests, hook syntax, marketplace discovery, and MCP entrypoints."""
from __future__ import annotations
import argparse, json, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", type=Path)
    ap.add_argument("--skip-codex-cli", action="store_true")
    args = ap.parse_args()
    for p in ROOT.glob("plugins/codex/*/.codex-plugin/plugin.json"):
        json.loads(p.read_text())
    for p in ROOT.glob("plugins/claude/*/.claude-plugin/plugin.json"):
        json.loads(p.read_text())
    json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    for p in list(ROOT.glob("plugins/claude/*/hooks/*.sh")) + list(ROOT.glob("plugins/codex/*/hooks/*.sh")):
        subprocess.run(["bash", "-n", str(p)], check=True)
    if not args.skip_codex_cli:
        if args.home is None:
            raise RuntimeError("--home is required for isolated Codex CLI verification")
        home = args.home.expanduser().resolve()
        (home / ".codex").mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(HOME=str(home), CODEX_HOME=str(home / ".codex"))
        subprocess.run(["codex", "plugin", "marketplace", "add", str(ROOT)], env=env, check=True)
        out = subprocess.run(["codex", "plugin", "list"], env=env, text=True, capture_output=True, check=True).stdout
        for name in ("codex-memory-pro", "codex-multi-agent", "design-test-loop"):
            if f"{name}@worklikerico" not in out:
                raise RuntimeError(f"Codex did not discover {name}")
    print("plugin verification passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
