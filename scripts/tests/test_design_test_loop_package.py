import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex/design-test-loop"
GATE_HOOK = PLUGIN / "hooks/02-gate-check.sh"
SUPPORT_SKILLS = {"spec-first", "remove-ai-slop", "doubt-review"}
EXPECTED_SKILLS = SUPPORT_SKILLS | {
    "design-gate",
    "strict-prod-audit",
    "audit-verify",
}


class DesignTestLoopPackageTests(unittest.TestCase):
    def run_gate(
        self,
        state,
        transcript,
        tool_name="functions.apply_patch",
        tool_input=None,
    ):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            state_dir = temp_path / "state"
            state_dir.mkdir()
            (state_dir / "test.state").write_text(state, encoding="utf-8")
            transcript_path = temp_path / "transcript.txt"
            transcript_path.write_text(transcript, encoding="utf-8")
            payload = {
                "tool_name": tool_name,
                "session_id": "test",
                "transcript_path": str(transcript_path),
                "tool_input": tool_input or {},
            }
            env = os.environ.copy()
            env["HOME"] = temp
            env["WORKLIKERICO_DTL_STATE_DIR"] = str(state_dir)
            env["DTL_FORCE_RISK"] = "MEDIUM"
            return subprocess.run(
                ["bash", str(GATE_HOOK)],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

    def test_standalone_package_contains_every_gate_skill(self):
        bundled = {
            path.parent.name
            for path in (PLUGIN / "skills").glob("*/SKILL.md")
        }
        self.assertEqual(bundled, EXPECTED_SKILLS)

        hook = GATE_HOOK.read_text(encoding="utf-8")
        for skill in SUPPORT_SKILLS:
            self.assertIn(skill, hook)

    def test_spec_gate_names_a_bundled_skill_and_accepts_its_marker(self):
        blocked = self.run_gate("DESIGN_DONE\n", "")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("spec-first", blocked.stderr)

        passed = self.run_gate("DESIGN_DONE\n", "spec-first：实现前对齐\n")
        self.assertEqual(passed.returncode, 0, passed.stderr)

    def test_commit_gate_names_bundled_support_skills(self):
        commit = {"cmd": "git commit -m test"}
        blocked_slop = self.run_gate(
            "IMPL_IN_PROGRESS\n", "", "functions.exec_command", commit
        )
        self.assertEqual(blocked_slop.returncode, 2)
        self.assertIn("remove-ai-slop", blocked_slop.stderr)

        blocked_doubt = self.run_gate(
            "IMPL_IN_PROGRESS\n",
            "remove-ai-slop：本次改动无 slop 可清\n",
            "functions.exec_command",
            commit,
        )
        self.assertEqual(blocked_doubt.returncode, 2)
        self.assertIn("doubt-review", blocked_doubt.stderr)

        passed = self.run_gate(
            "IMPL_IN_PROGRESS\n",
            "remove-ai-slop：本次改动无 slop 可清\n"
            "doubt-review：提交前自审\n",
            "functions.exec_command",
            commit,
        )
        self.assertEqual(passed.returncode, 0, passed.stderr)

    def test_manifest_declares_bundled_skill_directory(self):
        manifest = json.loads(
            (PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["skills"], "./skills/")


if __name__ == "__main__":
    unittest.main()
