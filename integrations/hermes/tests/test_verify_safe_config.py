import copy
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "verify-safe-config.py"
ENV_TEMPLATE = SCRIPT.parent / "env.template"
VALIDATOR = runpy.run_path(str(SCRIPT))


def base_config():
    return {
        "platforms": {
            "telegram": {
                "enabled": False,
                "extra": {
                    "allow_from": [],
                    "group_allow_from": [],
                    "group_allowed_chats": [],
                },
            },
            "wecom": {
                "enabled": False,
                "extra": {
                    "dm_policy": "allowlist",
                    "group_policy": "allowlist",
                    "allow_from": [],
                    "group_allow_from": [],
                    "groups": {},
                },
            },
        }
    }


def run_case(config, env_lines=()):
    with tempfile.TemporaryDirectory() as home:
        home_path = Path(home)
        (home_path / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
        (home_path / ".env").write_text("\n".join(env_lines) + "\n")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--home", home],
            capture_output=True,
            text=True,
            check=False,
        )


class SafeConfigTests(unittest.TestCase):
    def test_template_scope_fields_are_registered(self):
        template_keys = {
            line.split("=", 1)[0]
            for line in ENV_TEMPLATE.read_text().splitlines()
            if line and not line.startswith("#") and "=" in line
        }
        template_scope_keys = {
            key for key in template_keys if key.endswith(("_ALLOWED_USERS", "_ALLOWED_CHATS"))
        }
        registered_scope_keys = set(VALIDATOR["ALLOWLIST_ENV_KEYS"]) | set(
            VALIDATOR["UNSUPPORTED_WECOM_GROUP_ENV_KEYS"]
        )
        self.assertLessEqual(template_scope_keys, registered_scope_keys)
        template_allow_all_keys = {
            key for key in template_keys if key.endswith("_ALLOW_ALL_USERS")
        }
        self.assertLessEqual(template_allow_all_keys, set(VALIDATOR["ALLOW_ALL_ENV_KEYS"]))

    def test_disabled_template_is_fail_closed(self):
        result = run_case(base_config())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_user_and_group_scopes_pass(self):
        config = base_config()
        telegram = config["platforms"]["telegram"]
        telegram["enabled"] = True
        telegram["extra"].update(
            allow_from=["tg-user"],
            group_allow_from=["tg-group-user"],
            group_allowed_chats=["-1001"],
        )
        wecom = config["platforms"]["wecom"]
        wecom["enabled"] = True
        wecom["extra"].update(
            allow_from=["wx-user"],
            group_allow_from=["wx-group"],
            groups={"wx-group": {"allow_from": ["wx-user"]}},
        )
        result = run_case(config)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_allow_all_env_is_rejected(self):
        for key in ("GATEWAY_ALLOW_ALL_USERS", "TELEGRAM_ALLOW_ALL_USERS", "WECOM_ALLOW_ALL_USERS"):
            with self.subTest(key=key):
                result = run_case(base_config(), [f"{key}=true"])
                self.assertEqual(result.returncode, 1)
                self.assertIn(key, result.stderr)

    def test_every_supported_allowlist_env_rejects_wildcard(self):
        keys = (
            "GATEWAY_ALLOWED_USERS",
            "TELEGRAM_ALLOWED_USERS",
            "TELEGRAM_GROUP_ALLOWED_USERS",
            "TELEGRAM_GROUP_ALLOWED_CHATS",
            "WECOM_ALLOWED_USERS",
        )
        for key in keys:
            with self.subTest(key=key):
                result = run_case(base_config(), [f"{key}=*"])
                self.assertEqual(result.returncode, 1)
                self.assertIn(key, result.stderr)

    def test_phantom_wecom_group_envs_are_rejected(self):
        for key in ("WECOM_GROUP_ALLOWED_USERS", "WECOM_GROUP_ALLOWED_CHATS"):
            with self.subTest(key=key):
                result = run_case(base_config(), [f"{key}=*"])
                self.assertEqual(result.returncode, 1)
                self.assertIn("not consumed by Hermes v0.21.1", result.stderr)

    def test_explicit_env_scopes_pass(self):
        result = run_case(
            base_config(),
            [
                "GATEWAY_ALLOWED_USERS=operator-1",
                "TELEGRAM_ALLOWED_USERS=12345",
                "TELEGRAM_GROUP_ALLOWED_USERS=23456",
                "TELEGRAM_GROUP_ALLOWED_CHATS=-10012345",
                "WECOM_ALLOWED_USERS=wecom-user-1",
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_yaml_identity_or_group_wildcard_is_rejected(self):
        mutations = (
            ("telegram allow_from", lambda c: c["platforms"]["telegram"]["extra"].update(allow_from=["*"])),
            ("telegram group_allow_from", lambda c: c["platforms"]["telegram"]["extra"].update(group_allow_from=["*"])),
            ("telegram group_allowed_chats", lambda c: c["platforms"]["telegram"]["extra"].update(group_allowed_chats=["*"])),
            ("wecom allow_from", lambda c: c["platforms"]["wecom"]["extra"].update(allow_from=["*"])),
            ("wecom group_allow_from", lambda c: c["platforms"]["wecom"]["extra"].update(group_allow_from=["*"])),
            ("wecom wildcard group", lambda c: c["platforms"]["wecom"]["extra"].update(groups={"*": {"allow_from": ["user"]}})),
            ("wecom group sender wildcard", lambda c: c["platforms"]["wecom"]["extra"].update(groups={"group-1": {"allow_from": ["*"]}})),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                config = copy.deepcopy(base_config())
                mutate(config)
                result = run_case(config)
                self.assertEqual(result.returncode, 1)

    def test_enabled_platforms_require_dm_identity_scope(self):
        for platform in ("telegram", "wecom"):
            with self.subTest(platform=platform):
                config = base_config()
                config["platforms"][platform]["enabled"] = True
                result = run_case(config)
                self.assertEqual(result.returncode, 1)
                self.assertIn("non-empty DM user allowlist", result.stderr)

    def test_wecom_policy_env_cannot_open_an_enabled_platform(self):
        for yaml_key, env_key in (
            ("dm_policy", "WECOM_DM_POLICY"),
            ("group_policy", "WECOM_GROUP_POLICY"),
        ):
            with self.subTest(env_key=env_key):
                config = base_config()
                config["platforms"]["wecom"]["enabled"] = True
                config["platforms"]["wecom"]["extra"]["allow_from"] = ["wx-user"]
                del config["platforms"]["wecom"]["extra"][yaml_key]
                result = run_case(config, [f"{env_key}=open"])
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"{yaml_key}: allowlist", result.stderr)


if __name__ == "__main__":
    unittest.main()
