import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/install_skills.py"


class InstallSkillsTests(unittest.TestCase):
    def run_install(self, home, *args):
        return subprocess.run(
            ["python3", str(SCRIPT), "--home", str(home), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_selects_only_xmind_for_hermes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            args = ("--skill", "xmind", "--target", "hermes")
            result = self.run_install(home, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            link = home / ".config/worklikerico/hermes/skills/xmind"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), (ROOT / "skills/xmind").resolve())
            self.assertFalse((home / ".agents/skills/xmind").exists())
            self.assertEqual(list(link.parent.iterdir()), [link])

            repeated = self.run_install(home, *args)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertIn("unchanged", repeated.stdout)

    def test_original_codex_target_remains_selectable(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            result = self.run_install(
                home, "--skill", "xmind", "--target", "codex"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            link = home / ".codex/skills/xmind"
            self.assertTrue(link.is_symlink())
            self.assertFalse(
                (home / ".config/worklikerico/hermes/skills/xmind").exists()
            )

    def test_unknown_skill_fails_clearly(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_install(
                Path(temp), "--skill", "missing-synthetic-skill", "--target", "hermes"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown skill(s): missing-synthetic-skill", result.stderr)

    def test_unsupported_skill_target_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            result = self.run_install(
                home, "--skill", "work-like-rico", "--target", "hermes"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "skill(s) do not support selected target(s): work-like-rico",
                result.stderr,
            )
            self.assertFalse((home / ".config").exists())


if __name__ == "__main__":
    unittest.main()
