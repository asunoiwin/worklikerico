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

    def test_work_like_rico_is_available_for_hermes(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            result = self.run_install(
                home, "--skill", "work-like-rico", "--target", "hermes"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (home / ".config/worklikerico/hermes/skills/work-like-rico").resolve(),
                (ROOT / "skill/work-like-rico").resolve(),
            )

    def test_foreign_target_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            target = home / ".config/worklikerico/hermes/skills/work-like-rico"
            target.mkdir(parents=True)
            marker = target / "foreign.txt"
            marker.write_text("keep")

            result = self.run_install(
                home, "--skill", "work-like-rico", "--target", "hermes"
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to replace existing path", result.stderr)
            self.assertEqual(marker.read_text(), "keep")

    def test_alias_to_same_target_is_unchanged_and_removable(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            alias = home / "repository-alias"
            alias.symlink_to(ROOT, target_is_directory=True)
            target = home / ".config/worklikerico/hermes/skills/work-like-rico"
            target.parent.mkdir(parents=True)
            target.symlink_to(
                alias / "skill/work-like-rico", target_is_directory=True
            )

            result = self.run_install(
                home, "--skill", "work-like-rico", "--target", "hermes"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unchanged", result.stdout)

            removed = self.run_install(
                home,
                "--skill",
                "work-like-rico",
                "--target",
                "hermes",
                "--remove",
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse(target.exists())

    def test_foreign_symlink_is_preserved_for_install_and_remove(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            foreign = home / "foreign-skill"
            foreign.mkdir()
            (foreign / "SKILL.md").write_text("foreign")
            target = home / ".config/worklikerico/hermes/skills/work-like-rico"
            target.parent.mkdir(parents=True)
            target.symlink_to(foreign, target_is_directory=True)

            installed = self.run_install(
                home, "--skill", "work-like-rico", "--target", "hermes"
            )
            removed = self.run_install(
                home,
                "--skill",
                "work-like-rico",
                "--target",
                "hermes",
                "--remove",
            )

            self.assertNotEqual(installed.returncode, 0)
            self.assertIn("refusing to replace foreign symlink", installed.stderr)
            self.assertNotEqual(removed.returncode, 0)
            self.assertIn("refusing to remove foreign symlink", removed.stderr)
            self.assertTrue(target.is_symlink())
            self.assertTrue(target.samefile(foreign))


if __name__ == "__main__":
    unittest.main()
