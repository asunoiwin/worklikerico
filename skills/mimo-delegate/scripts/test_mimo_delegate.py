#!/usr/bin/env python3

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from mimo_delegate import _check_handoff, _macos_write_sandbox, _runtime_config, list_models, run_delegate


FAKE_MIMO = r'''#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path

mode = os.environ.get("FAKE_MIMO_MODE", "success")
if len(sys.argv) > 1 and sys.argv[1] == "models":
    print("mimo/mimo-auto")
    print("xiaomi/mimo-v2.5-pro")
    print("custom/example-model")
    print("noise/path with spaces")
    raise SystemExit(0)
if len(sys.argv) > 1 and sys.argv[1:3] == ["session", "delete"]:
    raise SystemExit(0)

session = "ses_fake"
cwd = Path(sys.argv[sys.argv.index("--dir") + 1])
if mode == "metadata":
    metadata = cwd / ".mimocode"
    metadata.mkdir(exist_ok=True)
    (metadata / ".gitignore").write_text("node_modules\n.cron-lock\n", encoding="utf-8")
    (metadata / ".cron-lock").write_text("{}", encoding="utf-8")
if mode == "timeout":
    time.sleep(60)
if mode == "invalid":
    print("ProviderModelNotFoundError: fake/model", file=sys.stderr, flush=True)
    raise SystemExit(0)
if mode == "permission":
    print(json.dumps({"type": "permission.asked", "sessionID": session, "permission": "external_directory"}), flush=True)
    time.sleep(60)
if mode == "actor_incomplete":
    state = {
        "status": "completed",
        "input": {"operation": {"action": "spawn", "description": "fake actor"}},
        "metadata": {"actorId": "general-1", "model": {"providerID": "mimo", "modelID": "mimo-auto"}},
        "time": {"start": 10, "end": 11},
    }
    print(json.dumps({"type":"tool_use","sessionID":session,"part":{"tool":"actor","state":state}}), flush=True)
    print(json.dumps({"type":"text","sessionID":session,"part":{"text":"premature"}}), flush=True)
    print(json.dumps({"type":"step_finish","sessionID":session,"part":{"reason":"stop"}}), flush=True)
    raise SystemExit(0)
if mode == "actor_scheduling_violation":
    def actor_event(action, actor_id, start, completed=None):
        state = {
            "status": "completed",
            "input": {"operation": {"action": action, "actor_id": actor_id, "description": actor_id}},
            "metadata": {"actorId": actor_id, "model": {"providerID": "xiaomi", "modelID": "mimo-v2.5-pro"}},
            "time": {"start": start, "end": start + 1},
        }
        if action == "wait":
            state["output"] = json.dumps({
                "lastOutcome": "success",
                "reportedStatus": "completed",
                "time": {"completed": completed},
            })
        print(json.dumps({"type":"tool_use","sessionID":session,"part":{"tool":"actor","state":state}}), flush=True)
    actor_event("spawn", "actor-a", 10)
    actor_event("wait", "actor-a", 12, 20)
    actor_event("spawn", "actor-b", 13)
    actor_event("wait", "actor-b", 14, 21)
if mode == "integrity_warning":
    state = {
        "status": "completed",
        "input": {"command": "truncate -s 0 tests/integration.rs"},
        "metadata": {},
        "time": {"start": 10, "end": 11},
    }
    print(json.dumps({"type":"tool_use","sessionID":session,"part":{"tool":"bash","state":state}}), flush=True)
if mode == "actor_tool_error":
    state = {
        "status": "error",
        "input": {"operation": {"action": "spawn", "description": "bad actor"}},
        "metadata": {},
        "time": {"start": 10, "end": 11},
    }
    print(json.dumps({"type":"tool_use","sessionID":session,"part":{"tool":"actor","state":state}}), flush=True)
if mode == "orphan":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    (cwd / "orphan.pid").write_text(str(child.pid), encoding="utf-8")
    time.sleep(60)

message = "msg_root"
print(json.dumps({"type":"step_start","sessionID":session,"part":{"messageID":message,"type":"step-start"}}), flush=True)
handoff = """## Handoff
- Status: completed
- Summary: fake success
- Files changed: none
- Key findings: none
- Risks: none
- Verification: fake pass
- Next step: none"""
text = "ARGS=" + json.dumps(sys.argv[1:]) if mode == "args" else handoff
print(json.dumps({"type":"text","sessionID":session,"part":{"messageID":message,"type":"text","text":text}}), flush=True)
if mode == "text_no_finish":
    time.sleep(60)
print(json.dumps({"type":"step_finish","sessionID":session,"part":{"messageID":message,"type":"step-finish","reason":"stop"}}), flush=True)
if mode in {"hang", "metadata", "args"}:
    time.sleep(60)
'''


class DelegateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.binary = self.root / "mimo"
        self.binary.write_text(FAKE_MIMO, encoding="utf-8")
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_fake(self, mode: str, **overrides):
        import os

        old = os.environ.get("FAKE_MIMO_MODE")
        os.environ["FAKE_MIMO_MODE"] = mode
        try:
            params = dict(
                prompt="test",
                cwd=self.root,
                permission_mode="read-only",
                timeout=3,
                settle_seconds=0.1,
                mimo_bin=str(self.binary),
            )
            params.update(overrides)
            return run_delegate(**params)
        finally:
            if old is None:
                os.environ.pop("FAKE_MIMO_MODE", None)
            else:
                os.environ["FAKE_MIMO_MODE"] = old

    def test_successful_result_terminates_hanging_process(self) -> None:
        code, result = self.run_fake("hang")
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["handoff"]["valid"])
        self.assertTrue(result["terminated_after_result"])

    def test_text_without_step_finish_is_recovered_after_idle(self) -> None:
        code, result = self.run_fake("text_no_finish", result_idle_seconds=0.1)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["terminated_after_idle_result"])

    def test_permission_request_fails_fast(self) -> None:
        code, result = self.run_fake("permission")
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "permission_required")
        self.assertLess(result["elapsed_seconds"], 2)

    def test_timeout_terminates_process_group(self) -> None:
        code, result = self.run_fake("timeout", timeout=0.2)
        self.assertEqual(code, 124)
        self.assertEqual(result["status"], "timeout")

    def test_model_and_full_permission_flags_are_forwarded(self) -> None:
        code, result = self.run_fake(
            "args",
            permission_mode="full",
            agent="mimo-delegate-full",
            model="provider/model-x",
            require_handoff=False,
        )
        self.assertEqual(code, 0)
        args = json.loads(result["final_text"].removeprefix("ARGS="))
        self.assertIn("--dangerously-skip-permissions", args)
        self.assertEqual(args[args.index("--model") + 1], "provider/model-x")

    def test_read_only_rejects_unmanaged_agent(self) -> None:
        code, result = self.run_fake("success", agent="build")
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "unsafe_agent_selection")

    def test_new_workspace_metadata_is_removed(self) -> None:
        code, result = self.run_fake("metadata")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / ".mimocode").exists())
        self.assertTrue(result["cleanup"]["workspace_metadata"]["removed"])

    def test_existing_workspace_metadata_is_preserved(self) -> None:
        metadata = self.root / ".mimocode"
        metadata.mkdir()
        marker = metadata / "mimocode.jsonc"
        marker.write_text("{}", encoding="utf-8")
        code, _ = self.run_fake("metadata")
        self.assertEqual(code, 0)
        self.assertTrue(marker.exists())

    def test_models_are_dynamic(self) -> None:
        code, result = list_models("mimo", str(self.binary))
        self.assertEqual(code, 0)
        self.assertEqual(
            result["models"],
            ["mimo/mimo-auto", "xiaomi/mimo-v2.5-pro", "custom/example-model"],
        )

    def test_runtime_agents_are_fail_closed(self) -> None:
        read_config = json.loads(_runtime_config("read-only", "readonly"))["agent"]["readonly"]
        read_only = read_config["permission"]
        workspace = json.loads(_runtime_config("workspace-write", "workspace"))["agent"]["workspace"]["permission"]
        self.assertEqual(read_only["*"], "deny")
        self.assertNotIn("edit", read_only)
        self.assertNotIn("bash", read_only)
        self.assertEqual(workspace["edit"], "allow")
        self.assertEqual(workspace["external_directory"], "deny")
        self.assertIn("exactly one of: completed, blocked, failed", read_config["prompt"])

    @unittest.skipUnless(sys.platform == "darwin", "macOS sandbox test")
    def test_macos_sandbox_allows_workspace_and_blocks_sibling_write(self) -> None:
        workspace = self.root / "workspace"
        sibling = self.root / "sibling"
        scratch = self.root / "scratch"
        workspace.mkdir()
        sibling.mkdir()
        scratch.mkdir()
        (workspace / ".git").mkdir()
        (workspace / "escape-link").symlink_to(sibling / "via-link")
        command = [
            "/bin/sh",
            "-c",
            (
                f"printf ok > '{workspace / 'inside'}'; "
                f"printf escape > '{sibling / 'outside'}'; "
                f"printf escape > '{workspace / 'escape-link'}'; "
                f"printf git > '{workspace / '.git' / 'config'}'"
            ),
        ]
        sandboxed = _macos_write_sandbox(command, workspace, scratch)
        self.assertIsNotNone(sandboxed)
        subprocess.run(sandboxed, text=True, capture_output=True, check=False)
        self.assertEqual((workspace / "inside").read_text(encoding="utf-8"), "ok")
        self.assertFalse((sibling / "outside").exists())
        self.assertFalse((sibling / "via-link").exists())
        self.assertFalse((workspace / ".git" / "config").exists())

    def test_invalid_model_is_classified(self) -> None:
        code, result = self.run_fake("invalid")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "invalid_model")

    def test_incomplete_actor_cannot_be_reported_as_success(self) -> None:
        code, result = self.run_fake("actor_incomplete")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "incomplete_actors")
        self.assertEqual(result["actors"][0]["actor_id"], "general-1")

    def test_spawn_after_wait_is_actor_scheduling_violation(self) -> None:
        code, result = self.run_fake("actor_scheduling_violation")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "actor_scheduling_violation")
        self.assertEqual(result["actor_actions"], ["spawn", "wait", "spawn", "wait"])

    def test_failed_actor_tool_without_actor_id_is_not_success(self) -> None:
        code, result = self.run_fake("actor_tool_error")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "actor_tool_error")
        self.assertEqual(len(result["failed_tool_uses"]), 1)

    def test_destructive_test_command_is_reported_without_echoing_input(self) -> None:
        code, result = self.run_fake("integrity_warning")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "integrity_review_required")
        self.assertIn("zero_length_truncate", result["integrity_warnings"])
        self.assertNotIn("integration.rs", json.dumps(result["integrity_warnings"]))

    def test_freeform_result_is_rejected_by_default(self) -> None:
        code, result = self.run_fake("args")
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "invalid_handoff")
        self.assertFalse(result["handoff"]["valid"])

    def test_bold_markdown_handoff_fields_are_accepted(self) -> None:
        handoff = """## Handoff
- **Status**: completed
- **Summary**: ok
- **Files changed**: none
- **Key findings**: none
- **Risks**: none
- **Verification**: pass
- **Next step**: none"""
        result = _check_handoff(handoff)
        self.assertTrue(result["valid"])
        self.assertEqual(result["reported_status"], "completed")

    def test_bold_handoff_without_list_markers_is_accepted(self) -> None:
        handoff = """**Status**: completed
**Summary**: ok
**Files changed**: none
**Key findings**: none
**Risks**: none
**Verification**: pass
**Next step**: none"""
        result = _check_handoff(handoff)
        self.assertTrue(result["valid"])
        self.assertEqual(result["reported_status"], "completed")

    def test_handoff_rejects_unknown_status_and_empty_fields(self) -> None:
        invalid_status = """## Handoff
- Status: unknown
- Summary: ok
- Files changed: none
- Key findings: none
- Risks: none
- Verification: pass
- Next step: none"""
        empty_summary = invalid_status.replace("Status: unknown", "Status: completed").replace("Summary: ok", "Summary:")
        self.assertTrue(_check_handoff(invalid_status)["invalid_status"])
        self.assertFalse(_check_handoff(invalid_status)["valid"])
        self.assertIn("Summary", _check_handoff(empty_summary)["empty_fields"])
        self.assertFalse(_check_handoff(empty_summary)["valid"])

    def test_existing_raw_log_is_never_overwritten(self) -> None:
        raw_log = self.root / "existing.jsonl"
        raw_log.write_text("keep-me", encoding="utf-8")
        code, result = self.run_fake("success", raw_log=raw_log)
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "raw_log_exists")
        self.assertEqual(raw_log.read_text(encoding="utf-8"), "keep-me")

    def test_write_path_cannot_escape_cwd(self) -> None:
        code, result = self.run_fake(
            "success",
            permission_mode="workspace-write",
            write_paths=[Path("../outside")],
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "invalid_write_path")

    def test_detached_descendant_is_terminated_on_timeout(self) -> None:
        import os
        import time

        code, result = self.run_fake("orphan", timeout=0.3)
        self.assertEqual(code, 124)
        pid = int((self.root / "orphan.pid").read_text(encoding="utf-8"))
        self.assertIn(pid, result["terminated_descendant_pids"])
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            self.fail("detached descendant survived wrapper timeout")

    @unittest.skipUnless(sys.platform == "darwin", "macOS sandbox test")
    def test_macos_sandbox_write_path_allowlist_blocks_other_workspace_paths(self) -> None:
        workspace = self.root / "workspace-allowlist"
        allowed = workspace / "allowed"
        blocked = workspace / "blocked"
        scratch = self.root / "scratch-allowlist"
        allowed.mkdir(parents=True)
        blocked.mkdir()
        scratch.mkdir()
        command = [
            "/bin/sh",
            "-c",
            f"printf ok > '{allowed / 'inside'}'; printf no > '{blocked / 'outside'}'",
        ]
        sandboxed = _macos_write_sandbox(command, workspace, scratch, [allowed])
        self.assertIsNotNone(sandboxed)
        subprocess.run(sandboxed, text=True, capture_output=True, check=False)
        self.assertEqual((allowed / "inside").read_text(encoding="utf-8"), "ok")
        self.assertFalse((blocked / "outside").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
