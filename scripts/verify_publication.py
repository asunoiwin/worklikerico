#!/usr/bin/env python3
"""Fail closed when repository publication would include private or generated material."""
from __future__ import annotations
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [ROOT / p for p in ("plugins", "skills", "catalog", "scripts", "docs/migration", ".agents/plugins", ".claude-plugin")]
FORBIDDEN_PARTS = {".git", "node_modules", "dist", "state", "baselines", "backups", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = {"HANDOFF.md", ".DS_Store"}
TEXT_SUFFIXES = {".json", ".md", ".toml", ".yaml", ".yml", ".py", ".sh", ".js", ".mjs", ".cjs", ".ts", ".txt"}
PATTERNS = {
    "private absolute home": re.compile(r"/Users/rico(?:/|\\b)"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "private key block": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "provider key": re.compile(r"\b[0-9a-f]{32}\.[A-Za-z0-9]{8,}\b"),
    "sk-style token": re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{24,}"),
}
ALLOW = {
    ("private key block", "skills/oci-cloud-ops/scripts/tests/test_scripts.py"),
}

def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()

def main() -> int:
    errors: list[str] = []
    for base in SCAN_ROOTS:
        if not base.exists():
            errors.append(f"missing required publication root: {rel(base)}")
            continue
        for p in base.rglob("*"):
            if p.is_dir():
                continue
            rp = rel(p)
            if any(part in FORBIDDEN_PARTS for part in p.relative_to(ROOT).parts):
                errors.append(f"generated/private path: {rp}")
            if p.name in FORBIDDEN_NAMES or p.name.startswith("report-") or ".bak" in p.name:
                errors.append(f"forbidden artifact: {rp}")
            if p.suffix.lower() not in TEXT_SUFFIXES or p.stat().st_size > 2_000_000:
                continue
            text = p.read_text(errors="replace")
            for label, pattern in PATTERNS.items():
                if pattern.search(text) and (label, rp) not in ALLOW:
                    errors.append(f"{label}: {rp}")
    for p in ROOT.glob("plugins/codex/*/.codex-plugin/plugin.json"):
        data = json.loads(p.read_text())
        allowed = {"id","name","version","description","skills","apps","mcpServers","interface","author","homepage","repository","license","keywords"}
        extra = set(data) - allowed
        if extra:
            errors.append(f"unsupported Codex manifest fields {sorted(extra)}: {rel(p)}")
        if p.parent.parent.name != data.get("name"):
            errors.append(f"manifest/folder name mismatch: {rel(p)}")
        for key in ("name","version","description","interface"):
            if not data.get(key):
                errors.append(f"missing {key}: {rel(p)}")
    market = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    for item in market["plugins"]:
        source = ROOT / item["source"]["path"]
        if not source.is_dir():
            errors.append(f"missing marketplace source: {item['source']['path']}")
        if item["name"] != source.name:
            errors.append(f"marketplace/folder name mismatch: {item['name']}")
    if errors:
        print("\n".join(f"ERROR {e}" for e in errors), file=sys.stderr)
        return 1
    print("publication verification passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
