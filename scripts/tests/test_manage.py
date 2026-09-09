import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/manage.py"
SPEC = importlib.util.spec_from_file_location("manage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ManageTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_list_filters_platform_without_skill_bodies(self):
        result = self.run_cli("list", "--platform", "hermes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("work-like-rico\tskill", result.stdout)
        self.assertIn("xmind\tskill", result.stdout)
        self.assertNotIn("codex-memory-pro", result.stdout)
        self.assertNotIn("将 Rico 的项目无关工作方法", result.stdout)
        self.assertIn("创建、读取和校验 XMind 思维导图", result.stdout)
        self.assertNotIn("自研独立技能", result.stdout)
        self.assertIn("TOTAL\t2 repository entries\t2 skills\t0 plugins", result.stdout)

    def test_hermes_default_installs_core_and_xmind_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            args = ("install", "--platform", "hermes", "--home", str(home))
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            skills = home / ".config/worklikerico/hermes/skills"
            self.assertEqual(
                {path.name for path in skills.iterdir()}, {"work-like-rico", "xmind"}
            )
            self.assertEqual(
                (skills / "work-like-rico").resolve(),
                (ROOT / "skill/work-like-rico").resolve(),
            )

            repeated = self.run_cli(*args)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertIn("unchanged", repeated.stdout)

    def test_foreign_skill_conflict_is_nonzero_and_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            target = home / ".config/worklikerico/hermes/skills/work-like-rico"
            target.mkdir(parents=True)
            marker = target / "foreign.txt"
            marker.write_text("keep")

            result = self.run_cli(
                "install", "--platform", "hermes", "--home", str(home)
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("install: completed", result.stdout)
            self.assertEqual(marker.read_text(), "keep")
            self.assertFalse((target.parent / "xmind").exists())

    def test_late_skill_conflict_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            skills = home / ".config/worklikerico/hermes/skills"
            foreign = skills / "xmind"
            foreign.mkdir(parents=True)
            marker = foreign / "foreign.txt"
            marker.write_text("keep")

            result = self.run_cli(
                "install", "--platform", "hermes", "--home", str(home)
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((skills / "work-like-rico").exists())
            self.assertEqual(marker.read_text(), "keep")

    def test_skill_filter_does_not_install_plugins(self):
        result = self.run_cli(
            "install", "--platform", "codex", "--skill", "xmind", "--dry-run"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("install_skills.py", result.stdout)
        self.assertNotIn("install_codex_plugins.py", result.stdout)

    def test_plugin_filter_does_not_install_other_modules(self):
        result = self.run_cli(
            "install",
            "--platform",
            "codex",
            "--plugin",
            "codex-multi-agent",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("install_skills.py", result.stdout)
        self.assertIn("--plugin codex-multi-agent", result.stdout)
        self.assertNotIn("codex-memory-pro", result.stdout)
        self.assertNotIn("design-test-loop", result.stdout)

    def test_invalid_combination_fails_before_subprocess(self):
        with mock.patch.object(MODULE, "run_command") as run:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = MODULE.main(
                    [
                        "install",
                        "--platform",
                        "hermes",
                        "--plugin",
                        "codex-memory-pro",
                    ]
                )
        self.assertEqual(result, 2)
        self.assertIn("do not support hermes", stderr.getvalue())
        run.assert_not_called()

    def test_dry_run_executes_no_subprocess(self):
        with mock.patch.object(MODULE, "run_command") as run:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = MODULE.main(["update", "--platform", "codex", "--dry-run"])
        self.assertEqual(result, 0)
        self.assertIn("git pull --ff-only", stdout.getvalue())
        run.assert_not_called()

    def test_dirty_update_stops_before_pull_and_install(self):
        dirty = subprocess.CompletedProcess([], 0, " M README.md\n", "")
        with mock.patch.object(MODULE, "run_command", return_value=dirty) as run:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = MODULE.main(
                    ["update", "--platform", "hermes", "--skill", "xmind"]
                )
        self.assertEqual(result, 2)
        self.assertIn("worktree is not clean", stderr.getvalue())
        self.assertEqual(run.call_count, 1)

    def test_update_pull_failure_does_not_install(self):
        clean = subprocess.CompletedProcess([], 0, "", "")
        failed = subprocess.CompletedProcess([], 9, "", "failed")
        with mock.patch.object(MODULE, "run_command", side_effect=[clean, failed]) as run:
            result = MODULE.main(
                ["update", "--platform", "hermes", "--skill", "xmind"]
            )
        self.assertEqual(result, 9)
        self.assertEqual(run.call_count, 2)

    def test_update_runs_pull_before_selected_install(self):
        succeeded = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(
            MODULE, "run_command", side_effect=[succeeded, succeeded, succeeded]
        ) as run:
            result = MODULE.main(
                ["update", "--platform", "hermes", "--skill", "xmind"]
            )
        self.assertEqual(result, 0)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0], ["git", "status", "--porcelain"])
        self.assertEqual(commands[1], ["git", "pull", "--ff-only"])
        self.assertIn("install_skills.py", commands[2][1])
        self.assertEqual(commands[2][-2:], ["--skill", "xmind"])

    def test_update_reloads_default_set_after_pull(self):
        before = MODULE.load_catalog()
        after = {
            **before,
            "skills": [
                item for item in before["skills"] if item["name"] != "xmind"
            ]
            + [
                {
                    "name": "synthetic-new-skill",
                    "path": "skills/synthetic-new-skill",
                    "installTargets": ["hermes"],
                    "classification": "self-built",
                }
            ],
        }
        succeeded = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(
            MODULE, "load_catalog", side_effect=[before, after]
        ), mock.patch.object(
            MODULE, "run_command", side_effect=[succeeded, succeeded, succeeded]
        ) as run:
            result = MODULE.main(["update", "--platform", "hermes"])

        self.assertEqual(result, 0)
        install = run.call_args_list[2].args[0]
        self.assertIn("synthetic-new-skill", install)
        self.assertNotIn("xmind", install)

    def test_update_reports_post_pull_incompatible_selection(self):
        before = MODULE.load_catalog()
        after = {
            **before,
            "skills": [
                {
                    **item,
                    "installTargets": [
                        target
                        for target in item["installTargets"]
                        if target != "hermes"
                    ],
                }
                if item["name"] == "xmind"
                else item
                for item in before["skills"]
            ],
        }
        succeeded = subprocess.CompletedProcess([], 0, "", "")
        stderr = io.StringIO()
        with mock.patch.object(
            MODULE, "load_catalog", side_effect=[before, after]
        ), mock.patch.object(
            MODULE, "run_command", side_effect=[succeeded, succeeded]
        ) as run, contextlib.redirect_stderr(stderr):
            result = MODULE.main(
                ["update", "--platform", "hermes", "--skill", "xmind"]
            )

        self.assertEqual(result, 2)
        self.assertEqual(run.call_count, 2)
        self.assertIn("source-sync: completed; install plan invalid", stderr.getvalue())

    def test_install_failure_stops_following_steps(self):
        failed = subprocess.CompletedProcess([], 7, "", "failed")
        with mock.patch.object(MODULE, "run_command", return_value=failed) as run:
            result = MODULE.main(["install", "--platform", "codex"])
        self.assertEqual(result, 7)
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
