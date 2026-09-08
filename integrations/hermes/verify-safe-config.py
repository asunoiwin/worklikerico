#!/usr/bin/env python3
import argparse
import os
import sys

import yaml


ALLOW_ALL_ENV_KEYS = (
    "GATEWAY_ALLOW_ALL_USERS",
    "TELEGRAM_ALLOW_ALL_USERS",
    "WECOM_ALLOW_ALL_USERS",
)
ALLOWLIST_ENV_KEYS = (
    "GATEWAY_ALLOWED_USERS",
    "TELEGRAM_ALLOWED_USERS",
    "TELEGRAM_GROUP_ALLOWED_USERS",
    "TELEGRAM_GROUP_ALLOWED_CHATS",
    "WECOM_ALLOWED_USERS",
)
UNSUPPORTED_WECOM_GROUP_ENV_KEYS = (
    "WECOM_GROUP_ALLOWED_USERS",
    "WECOM_GROUP_ALLOWED_CHATS",
)


def items(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def read_env(path):
    result = {}
    if not os.path.exists(path):
        return result
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip().strip("'\"")
    return result


def main():
    parser = argparse.ArgumentParser(description="Fail closed before enabling Hermes messaging.")
    parser.add_argument("--home", default=os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
    args = parser.parse_args()
    config_path = os.path.join(args.home, "config.yaml")
    env_path = os.path.join(args.home, ".env")

    with open(config_path, encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    env = read_env(env_path)
    errors = []

    for key in ALLOW_ALL_ENV_KEYS:
        if env.get(key, "").lower() in {"1", "true", "yes"}:
            errors.append(f"{key} must not enable allow-all")
    for key in ALLOWLIST_ENV_KEYS:
        if "*" in items(env.get(key)):
            errors.append(f"{key} must not contain '*'")
    for key in UNSUPPORTED_WECOM_GROUP_ENV_KEYS:
        if items(env.get(key)):
            errors.append(f"{key} is not consumed by Hermes v0.21.1; use platforms.wecom.extra.group_allow_from")

    platforms = config.get("platforms") or {}
    telegram = platforms.get("telegram") or {}
    telegram_extra = telegram.get("extra") or {}
    for key in ("allow_from", "group_allow_from", "group_allowed_chats"):
        if "*" in items(telegram_extra.get(key)):
            errors.append(f"platforms.telegram.extra.{key} must not contain '*'")
    if telegram.get("enabled") and not (items(telegram_extra.get("allow_from")) or items(env.get("TELEGRAM_ALLOWED_USERS"))):
        errors.append("enabled Telegram requires a non-empty DM user allowlist")

    wecom = platforms.get("wecom") or {}
    wecom_extra = wecom.get("extra") or {}
    if wecom.get("enabled"):
        if str(wecom_extra.get("dm_policy", "")).lower() != "allowlist":
            errors.append("enabled WeCom requires dm_policy: allowlist")
        if str(wecom_extra.get("group_policy", "")).lower() != "allowlist":
            errors.append("enabled WeCom requires group_policy: allowlist")
        if not (items(wecom_extra.get("allow_from")) or items(env.get("WECOM_ALLOWED_USERS"))):
            errors.append("enabled WeCom requires a non-empty DM user allowlist")
    for key in ("allow_from", "group_allow_from"):
        if "*" in items(wecom_extra.get(key)):
            errors.append(f"platforms.wecom.extra.{key} must not contain '*'")
    wecom_groups = wecom_extra.get("groups") or {}
    if "*" in wecom_groups:
        errors.append("platforms.wecom.extra.groups must not use wildcard group rules")
    if isinstance(wecom_groups, dict):
        for group_id, group_config in wecom_groups.items():
            if isinstance(group_config, dict) and "*" in items(group_config.get("allow_from")):
                errors.append(f"platforms.wecom.extra.groups.{group_id}.allow_from must not contain '*'")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Hermes messaging preflight: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
