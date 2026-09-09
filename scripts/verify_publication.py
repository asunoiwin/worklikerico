#!/usr/bin/env python3
"""Fail closed when repository publication would include private or generated material."""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("plugins", "skills", "catalog", "scripts", "docs/migration", ".agents/plugins", ".claude-plugin")
FORBIDDEN_PARTS = {".git", "node_modules", "dist", "state", "baselines", "backups", "__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = {"HANDOFF.md", ".DS_Store"}
TEXT_SUFFIXES = {".json", ".md", ".toml", ".yaml", ".yml", ".py", ".sh", ".js", ".mjs", ".cjs", ".ts", ".txt"}
MEMORY_DIST = Path("plugins/claude/claude-memory-pro/dist")
MEMORY_SRC = Path("plugins/claude/claude-memory-pro/src")
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

def rel(p: Path, root: Path = ROOT) -> str:
    return p.relative_to(root).as_posix()


def publication_candidates(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode() for item in result.stdout.split(b"\0") if item]


def is_scanned_path(path: Path) -> bool:
    parts = path.parts
    return any(parts[: len(Path(base).parts)] == Path(base).parts for base in SCAN_ROOTS)


def is_memory_runtime_dist(path: Path, root: Path) -> bool:
    try:
        output = path.relative_to(MEMORY_DIST)
    except ValueError:
        return False
    if len(output.parts) != 1:
        return False
    if output.name.endswith(".d.ts"):
        stem = output.name[:-5]
    elif output.suffix == ".js":
        stem = output.stem
    else:
        return False
    return (root / MEMORY_SRC / f"{stem}.ts").is_file()


def scan_publication(root: Path, candidates: list[Path]) -> list[str]:
    errors: list[str] = []
    for p in candidates:
        if not p.is_file():
            continue
        relative = p.relative_to(root)
        if not is_scanned_path(relative):
            continue
        rp = relative.as_posix()
        forbidden = set(relative.parts) & FORBIDDEN_PARTS
        if forbidden and not is_memory_runtime_dist(relative, root):
            errors.append(f"generated/private path: {rp}")
        if p.name in FORBIDDEN_NAMES or p.name.startswith("report-") or ".bak" in p.name:
            errors.append(f"forbidden artifact: {rp}")
        if p.suffix.lower() not in TEXT_SUFFIXES or p.stat().st_size > 2_000_000:
            continue
        text = p.read_text(errors="replace")
        for label, pattern in PATTERNS.items():
            if pattern.search(text) and (label, rp) not in ALLOW:
                errors.append(f"{label}: {rp}")
    return errors

def main() -> int:
    errors: list[str] = []
    for name in SCAN_ROOTS:
        base = ROOT / name
        if not base.exists():
            errors.append(f"missing required publication root: {rel(base)}")
    errors.extend(scan_publication(ROOT, publication_candidates(ROOT)))
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
