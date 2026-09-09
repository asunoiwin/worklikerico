import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/install_claude_plugins.py"


class InstallClaudePluginsTests(unittest.TestCase):
    def run_install(self, home, *args):
        return subprocess.run(
            ["python3", str(SCRIPT), "--home", str(home), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_selected_plugin_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            args = ("--plugin", "claude-autoagent", "--skip-build")
            result = self.run_install(home, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            link = home / ".claude/plugins/local/claude-autoagent"
            self.assertTrue(link.is_symlink())
            self.assertFalse((home / ".claude/plugins/local/design-test-loop").exists())
            self.assertFalse((home / ".claude/plugins/local/claude-memory-pro").exists())

            repeated = self.run_install(home, *args)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertTrue(link.is_symlink())

    def test_selected_remove_keeps_unselected_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            local = home / ".claude/plugins/local"
            local.mkdir(parents=True)
            foreign = local / "foreign-plugin"
            foreign.mkdir()

            installed = self.run_install(
                home, "--plugin", "claude-autoagent", "--skip-build"
            )
            self.assertEqual(installed.returncode, 0, installed.stderr)
            removed = self.run_install(
                home, "--plugin", "claude-autoagent", "--remove"
            )

            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse((local / "claude-autoagent").exists())
            self.assertTrue(foreign.is_dir())
