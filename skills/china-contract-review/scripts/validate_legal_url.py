#!/usr/bin/env python3
"""Offline HTTPS and hostname guard for initial and redirected legal-source URLs."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


VALIDATOR = Path(__file__).resolve().with_name("validate_config.py")


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("china_contract_validate_config", VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("configuration validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_url(url: str, allowed_domains: set[str]) -> str | None:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        port = parsed.port
    except (UnicodeError, ValueError):
        return "URL cannot be parsed safely"
    if parsed.scheme != "https":
        return "URL scheme must be https"
    if parsed.username or parsed.password:
        return "URL credentials are forbidden"
    if port not in (None, 443):
        return "URL port must be 443"
    if host not in allowed_domains:
        return "URL host is not an exact allowed domain"
    if not parsed.path.startswith("/"):
        return "URL path must be absolute"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate initial and final legal-source URLs without making network requests.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("urls", nargs="+", help="initial URL followed by every redirect/final URL")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"status": "fail", "errors": ["configuration unreadable"]}))
        return 2
    config_errors = _load_validator().validate(config)
    if config_errors:
        print(json.dumps({"status": "fail", "errors": ["configuration rejected"]}))
        return 2
    allowed = {item.lower().rstrip(".") for item in config["legal_sources"]["allowed_domains"]}
    errors = [f"url[{index}]: {error}" for index, url in enumerate(args.urls) if (error := validate_url(url, allowed))]
    print(json.dumps({"status": "pass" if not errors else "fail", "url_count": len(args.urls), "errors": errors}, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
