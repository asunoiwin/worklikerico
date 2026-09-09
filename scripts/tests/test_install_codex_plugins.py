import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "install_codex_plugins.py"
SPEC = importlib.util.spec_from_file_location("install_codex_plugins", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class InstalledIdentityTests(unittest.TestCase):
    def test_enabled_and_disabled_plugins_are_both_installed(self):
        listing = """PLUGIN STATUS VERSION PATH
active@worklikerico installed, enabled 1.0.0 /tmp/active
paused@worklikerico installed, disabled 1.0.0 /tmp/paused
missing@worklikerico not installed /tmp/missing
"""
        self.assertEqual(
            MODULE.installed_identities(listing),
            {"active@worklikerico", "paused@worklikerico"},
        )

    def fake_run(self, calls):
        def run(args, env, check=True):
            calls.append(args)
            if args[-3:] == ["plugin", "marketplace", "list"]:
                stdout = f"NAME PATH\nworklikerico {MODULE.ROOT}\n"
            elif args[-2:] == ["plugin", "list"]:
                stdout = """PLUGIN STATUS VERSION PATH
codex-memory-pro@worklikerico installed, enabled 2.0.0 /tmp/memory
codex-multi-agent@worklikerico installed, enabled 1.0.0 /tmp/agents
design-test-loop@worklikerico installed, enabled 2.1.0 /tmp/design
foreign@other installed, enabled 1.0.0 /tmp/foreign
"""
            else:
                stdout = ""
            return subprocess.CompletedProcess(args, 0, stdout, "")

        return run

    def test_selected_plugin_does_not_touch_other_packages(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            MODULE, "run", side_effect=self.fake_run(calls)
        ):
            result = MODULE.main(
                ["--home", temp, "--plugin", "codex-multi-agent", "--skip-build"]
            )

        self.assertEqual(result, 0)
        flat = "\n".join(" ".join(args) for args in calls)
        self.assertIn("plugin remove codex-multi-agent@worklikerico", flat)
        self.assertIn("plugin add codex-multi-agent@worklikerico", flat)
        self.assertNotIn("plugin remove codex-memory-pro@worklikerico", flat)
        self.assertNotIn("plugin add design-test-loop@worklikerico", flat)
        self.assertNotIn("marketplace remove", flat)
        self.assertNotIn("foreign@other", "\n".join(" ".join(args) for args in calls[2:]))

    def test_selected_remove_keeps_marketplace_and_other_plugins(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            MODULE, "run", side_effect=self.fake_run(calls)
        ):
            result = MODULE.main(
                ["--home", temp, "--plugin", "codex-multi-agent", "--remove"]
            )

        self.assertEqual(result, 0)
        flat = "\n".join(" ".join(args) for args in calls)
        self.assertIn("plugin remove codex-multi-agent@worklikerico", flat)
        self.assertNotIn("plugin remove codex-memory-pro@worklikerico", flat)
        self.assertNotIn("marketplace remove", flat)
