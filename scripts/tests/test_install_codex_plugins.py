import importlib.util
import unittest
from pathlib import Path


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
