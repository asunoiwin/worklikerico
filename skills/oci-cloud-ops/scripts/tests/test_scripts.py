from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1]
RETRY = SCRIPTS / "oci_capacity_retry.py"
RENDER = SCRIPTS / "render_root_cloud_init.py"
INVENTORY = SCRIPTS / "oci_inventory.py"
LAUNCHAGENT = SCRIPTS / "render_macos_launchagent.py"
IDLE_GUARD = SCRIPTS / "oracle_idle_guard.py"
IDLE_INSTALLER = SCRIPTS / "install_linux_idle_guard.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FAKE_OCI = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

scenario = os.environ["FAKE_OCI_SCENARIO"]
counter_path = Path(os.environ["FAKE_OCI_COUNTER"])
log_path = Path(os.environ["FAKE_OCI_LOG"])
count = int(counter_path.read_text() or "0") if counter_path.exists() else 0
count += 1
counter_path.write_text(str(count))
with log_path.open("a") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\n")

if "get" in sys.argv:
    if scenario == "start_running":
        state = "RUNNING"
    elif scenario == "start_accept_then_running" and count >= 3:
        state = "RUNNING"
    else:
        state = "STOPPED"
    print(json.dumps({"data": {"lifecycle-state": state}}))
    raise SystemExit(0)

if scenario == "capacity_then_success" and count == 1:
    print('{"code":"InternalError","message":"Out of host capacity","opc-request-id":"req-cap"}', file=sys.stderr)
    raise SystemExit(1)
if scenario == "ambiguous_then_success" and count == 1:
    print('{"code":"InternalError","message":"Temporary service failure","opc-request-id":"req-amb"}', file=sys.stderr)
    raise SystemExit(1)
if scenario == "quota":
    print('{"code":"LimitExceeded","message":"No quota remains","opc-request-id":"req-quota"}', file=sys.stderr)
    raise SystemExit(1)

print(json.dumps({"data": {"id": "ocid1.instance.oc1.test.success"}}))
'''


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("oci_inventory", INVENTORY)

    def test_ocid_is_reduced_to_suffix(self):
        self.assertEqual(self.module.suffix("ocid1.instance.oc1.test.abcdefghijkl"), "abcdefghijkl")
        self.assertIsNone(self.module.suffix(None))

    def test_relevant_limits_exclude_reserved_capacity(self):
        self.assertTrue(self.module.relevant_compute_limit("standard-a1-core-count"))
        self.assertTrue(self.module.relevant_compute_limit("standard-a1-memory-regional-count"))
        self.assertTrue(self.module.relevant_compute_limit("vm-standard-e2-1-micro-count"))
        self.assertFalse(self.module.relevant_compute_limit("standard-a1-core-reserved-count"))
        self.assertFalse(self.module.relevant_compute_limit("gpu-a10-count"))

    def test_private_file_permissions_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config"
            path.write_text("test")
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                self.module.check_private_file(path, "test config")
            path.chmod(0o600)
            self.module.check_private_file(path, "test config")


class LaunchAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("render_macos_launchagent", LAUNCHAGENT)

    def test_plist_is_one_minute_bounded_tick(self):
        args = SimpleNamespace(
            label="com.example.oci-capacity-test",
            python_bin=Path("/usr/bin/python3"),
            retry_script=RETRY,
            mode="start",
            oci_bin=Path("/usr/local/bin/oci"),
            config_file=Path("/tmp/config"),
            profile="TEST",
            state_file=Path("/tmp/state.json"),
            max_attempts=5,
            region=None,
            instance_id="ocid1.instance.oc1.test.existing",
            request_file=None,
            interval=60,
            stdout=Path("/tmp/stdout.log"),
            stderr=Path("/tmp/stderr.log"),
        )
        rendered = self.module.build_plist(args)
        self.assertEqual(rendered["StartInterval"], 60)
        self.assertTrue(rendered["RunAtLoad"])
        self.assertIn("--once", rendered["ProgramArguments"])
        self.assertEqual(rendered["ProgramArguments"].count("--instance-id"), 1)


class IdleGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("oracle_idle_guard", IDLE_GUARD)

    def test_cpu_utilization_from_proc_samples(self):
        self.assertEqual(self.module.cpu_utilization((100, 80), (200, 130)), 50.0)

    def test_cpu_controller_relinquishes_to_real_workload(self):
        duty = self.module.next_cpu_duty(0.5, 45.0, 25.0, 2)
        self.assertLess(duty, 0.5)
        self.assertEqual(self.module.next_cpu_duty(0.5, 50.0, 25.0, 2), 0.0)
        self.assertEqual(self.module.next_cpu_duty(0.1, 40.0, 0.0, 2), 0.0)

    def test_cpu_controller_never_exceeds_one_core(self):
        duty = self.module.next_cpu_duty(0.9, 0.0, 30.0, 8)
        self.assertGreaterEqual(duty, 0.9)
        self.assertLessEqual(duty, 1.0)

    def test_memory_target_subtracts_non_guard_usage(self):
        desired = self.module.desired_guard_memory(
            total=1000,
            available=600,
            current_guard=200,
            target_percent=25.0,
            max_bytes=1000,
        )
        self.assertEqual(desired, 50)
        self.assertEqual(
            self.module.desired_guard_memory(1000, 600, 0, 25.0, 1000), 0
        )

    def test_memory_releases_immediately_for_real_workload(self):
        buffer = bytearray(1024)
        self.module.resize_buffer(buffer, 128, 16)
        self.assertEqual(len(buffer), 128)

    def test_memory_default_has_no_hidden_four_gib_cap(self):
        total = 24 * 1024 * 1024 * 1024
        self.assertEqual(self.module.memory_guard_limit(total, 0), total)
        self.assertEqual(
            self.module.desired_guard_memory(total, total, 0, 25.0, total),
            6 * 1024 * 1024 * 1024,
        )

    def test_targets_are_hard_capped_at_thirty_percent(self):
        with self.assertRaises(Exception):
            self.module.percent("30.1")


class IdleGuardInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("install_linux_idle_guard", IDLE_INSTALLER)

    def args(self, root: Path, action: str = "install") -> SimpleNamespace:
        return SimpleNamespace(
            action=action,
            root=root,
            shape="a1",
            cpu_target=None,
            memory_target=None,
            dry_run=False,
            no_systemctl=True,
        )

    def test_unit_disables_network_and_caps_resources(self):
        unit = self.module.unit_text("a1", 0.0, 25.0)
        self.assertIn("PrivateNetwork=yes", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
        self.assertIn("CPUQuota=100%", unit)
        self.assertIn("MemoryMax=35%", unit)
        self.assertIn("Nice=19", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertNotIn("--run-seconds", unit)
        self.assertIn("--cpu-target-percent 0", unit)
        self.assertIn("--memory-target-percent 25", unit)
        self.assertNotIn("curl", unit)
        self.assertNotIn("wget", unit)
        self.assertNotIn("http://", unit)
        self.assertNotIn("https://", unit)

    def test_live_dry_run_is_platform_independent(self):
        args = self.args(Path("/"))
        args.dry_run = True
        self.module.install(args)

    def test_live_status_rejects_no_systemctl_bypass(self):
        args = self.args(Path("/"), action="status")
        with self.assertRaises(RuntimeError):
            self.module.status(args)

    def test_e2_uses_sparse_local_cpu_pulses(self):
        unit = self.module.unit_text("e2", 25.0, 0.0)
        timer = self.module.timer_text()
        self.assertIn("--cpu-target-percent 25", unit)
        self.assertIn("--memory-target-percent 0", unit)
        self.assertIn("--run-seconds 900", unit)
        self.assertIn("CPUQuota=50%", unit)
        self.assertIn("Restart=no", unit)
        self.assertIn("OnUnitActiveSec=2h", timer)
        self.assertIn("RandomizedDelaySec=5min", timer)
        self.assertGreater(self.module.E2_RUN_SECONDS / (7200 + 300), 0.05)
        self.assertGreaterEqual(self.module.E2_RUN_SECONDS / 7200, 0.125)
        self.assertLess(self.module.E2_RUN_SECONDS / 7200, 0.15)
        self.assertNotIn("curl", unit + timer)
        self.assertNotIn("wget", unit + timer)

    def test_sandbox_install_status_and_exact_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            self.module.install(args)
            daemon, unit, timer = self.module.paths(root.resolve())
            self.assertTrue(daemon.is_file())
            self.assertTrue(unit.is_file())
            self.assertFalse(timer.exists())
            self.assertEqual(stat.S_IMODE(daemon.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(unit.stat().st_mode), 0o644)
            self.assertEqual(self.module.status(args), 0)
            self.module.uninstall(args)
            self.assertFalse(daemon.exists())
            self.assertFalse(unit.exists())

    def test_install_refuses_to_overwrite_different_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            self.module.install(args)
            _, unit, _ = self.module.paths(root.resolve())
            unit.write_text("unrelated service")
            with self.assertRaises(RuntimeError):
                self.module.install(args)

    def test_install_conflict_leaves_no_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            daemon, unit, _ = self.module.paths(root.resolve())
            unit.parent.mkdir(parents=True)
            unit.write_text("unrelated service")
            with self.assertRaises(RuntimeError):
                self.module.install(args)
            self.assertFalse(daemon.exists())

    def test_status_rejects_tampered_managed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            self.module.install(args)
            daemon, _, _ = self.module.paths(root.resolve())
            daemon.write_text("tampered")
            self.assertEqual(self.module.status(args), 3)

    def test_status_rejects_tampered_managed_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            self.module.install(args)
            _, unit, _ = self.module.paths(root.resolve())
            unit.write_text(unit.read_text().replace("CPUWeight=1", "CPUWeight=100"))
            self.assertEqual(self.module.status(args), 3)

    def test_e2_status_rejects_target_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            args.shape = "e2"
            self.module.install(args)
            _, unit, _ = self.module.paths(root.resolve())
            unit.write_text(unit.read_text().replace("percent 25", "percent 29"))
            self.assertEqual(self.module.status(args), 3)

    def test_e2_install_rejects_custom_cpu_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            args.shape = "e2"
            args.cpu_target = 29.0
            with self.assertRaises(RuntimeError):
                self.module.install(args)
            daemon, unit, timer = self.module.paths(root.resolve())
            self.assertFalse(daemon.exists() or unit.exists() or timer.exists())

    def test_e2_internal_install_rejects_memory_occupancy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            args.shape = "e2"
            args.memory_target = 5.0
            with self.assertRaises(RuntimeError):
                self.module.install(args)
            daemon, unit, timer = self.module.paths(root.resolve())
            self.assertFalse(daemon.exists() or unit.exists() or timer.exists())

    def test_a1_install_rejects_cpu_occupancy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            args.cpu_target = 25.0
            with self.assertRaises(RuntimeError):
                self.module.install(args)

    def test_e2_install_requires_managed_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            args.shape = "e2"
            self.module.install(args)
            daemon, unit, timer = self.module.paths(root.resolve())
            self.assertTrue(daemon.is_file())
            self.assertTrue(unit.is_file())
            self.assertTrue(timer.is_file())
            self.assertEqual(self.module.status(args), 0)
            timer.unlink()
            self.assertEqual(self.module.status(args), 3)

    def test_uninstall_stop_failure_retains_managed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            setup_args = self.args(sandbox)
            self.module.install(setup_args)
            managed_paths = self.module.paths(sandbox.resolve())
            live_args = self.args(Path("/"), action="uninstall")
            live_args.no_systemctl = False
            with mock.patch.object(self.module, "paths", return_value=managed_paths), mock.patch.object(
                self.module.os, "geteuid", return_value=0
            ), mock.patch.object(
                self.module,
                "systemctl",
                side_effect=subprocess.CalledProcessError(1, ["systemctl"]),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.module.uninstall(live_args)
            self.assertTrue(managed_paths[0].exists())
            self.assertTrue(managed_paths[1].exists())

    def test_e2_uninstall_disables_timer_even_if_timer_file_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            setup_args = self.args(sandbox)
            setup_args.shape = "e2"
            self.module.install(setup_args)
            managed_paths = self.module.paths(sandbox.resolve())
            managed_paths[2].unlink()
            live_args = self.args(Path("/"), action="uninstall")
            live_args.shape = "e2"
            live_args.no_systemctl = False
            with mock.patch.object(self.module, "paths", return_value=managed_paths), mock.patch.object(
                self.module.os, "geteuid", return_value=0
            ), mock.patch.object(self.module, "systemctl") as systemctl_mock:
                self.module.uninstall(live_args)
            first_call = systemctl_mock.call_args_list[0]
            self.assertEqual(
                first_call.args,
                ("disable", "--now", self.module.TIMER_NAME, self.module.SERVICE_NAME),
            )
            self.assertFalse(any(path.exists() for path in managed_paths))

    def test_uninstall_stops_service_when_unit_file_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            setup_args = self.args(sandbox)
            self.module.install(setup_args)
            managed_paths = self.module.paths(sandbox.resolve())
            managed_paths[1].unlink()
            live_args = self.args(Path("/"), action="uninstall")
            live_args.no_systemctl = False
            with mock.patch.object(self.module, "paths", return_value=managed_paths), mock.patch.object(
                self.module.os, "geteuid", return_value=0
            ), mock.patch.object(self.module, "systemctl") as systemctl_mock:
                self.module.uninstall(live_args)
            self.assertEqual(
                systemctl_mock.call_args_list[0].args,
                ("disable", "--now", self.module.SERVICE_NAME),
            )
            self.assertFalse(any(path.exists() for path in managed_paths))

    def test_install_activation_failure_rolls_back_created_files(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            managed_paths = self.module.paths(sandbox.resolve())
            live_args = self.args(Path("/"))
            live_args.shape = "e2"
            live_args.no_systemctl = False
            with mock.patch.object(self.module, "paths", return_value=managed_paths), mock.patch.object(
                self.module.os, "geteuid", return_value=0
            ), mock.patch.object(
                self.module,
                "systemctl",
                side_effect=[None, subprocess.CalledProcessError(1, ["systemctl"])],
            ), mock.patch.object(self.module, "systemctl_try", return_value=0):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.module.install(live_args)
            self.assertFalse(any(path.exists() for path in managed_paths))

    def test_install_failed_activation_and_rollback_retains_files(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            managed_paths = self.module.paths(sandbox.resolve())
            live_args = self.args(Path("/"))
            live_args.shape = "e2"
            live_args.no_systemctl = False
            with mock.patch.object(self.module, "paths", return_value=managed_paths), mock.patch.object(
                self.module.os, "geteuid", return_value=0
            ), mock.patch.object(
                self.module,
                "systemctl",
                side_effect=[None, subprocess.CalledProcessError(1, ["systemctl"])],
            ), mock.patch.object(self.module, "systemctl_try", return_value=1):
                with self.assertRaisesRegex(RuntimeError, "managed files were retained"):
                    self.module.install(live_args)
            self.assertTrue(all(path.exists() for path in managed_paths))

    def test_uninstall_refuses_unmanaged_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = self.args(root)
            _, unit, _ = self.module.paths(root.resolve())
            unit.parent.mkdir(parents=True)
            unit.write_text("[Unit]\nDescription=unrelated\n")
            with self.assertRaises(RuntimeError):
                self.module.uninstall(args)


class CapacityRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config"
        self.config.write_text("[DEFAULT]\nregion=test\n")
        self.config.chmod(0o600)
        self.request = self.root / "launch.json"
        self.request.write_text(json.dumps({"availabilityDomain": "AD-1"}))
        self.request.chmod(0o600)
        self.fake = self.root / "fake-oci"
        self.fake.write_text(FAKE_OCI)
        self.fake.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_job(
        self,
        scenario: str,
        state: Path,
        mode: str = "launch",
        profile: str = "DEFAULT",
        region: str | None = None,
        max_attempts: int = 5,
    ):
        env = os.environ.copy()
        env.update(
            {
                "FAKE_OCI_SCENARIO": scenario,
                "FAKE_OCI_COUNTER": str(self.root / f"{scenario}.count"),
                "FAKE_OCI_LOG": str(self.root / f"{scenario}.log"),
            }
        )
        common = [
            sys.executable,
            str(RETRY),
            mode,
            "--oci-bin",
            str(self.fake),
            "--config-file",
            str(self.config),
            "--profile",
            profile,
            "--state-file",
            str(state),
            "--max-attempts",
            str(max_attempts),
            "--once",
        ]
        if region:
            common.extend(["--region", region])
        if mode == "launch":
            common.extend(["--request-file", str(self.request)])
        else:
            common.extend(["--instance-id", "ocid1.instance.oc1.test.existing"])
        return subprocess.run(common, env=env, text=True, capture_output=True, check=False)

    def tokens(self, scenario: str) -> list[str]:
        lines = (self.root / f"{scenario}.log").read_text().splitlines()
        tokens = []
        for line in lines:
            args = json.loads(line)
            if "--opc-retry-token" in args:
                tokens.append(args[args.index("--opc-retry-token") + 1])
        return tokens

    def test_capacity_rotates_token_then_succeeds(self):
        state = self.root / "capacity-state.json"
        first = self.run_job("capacity_then_success", state)
        second = self.run_job("capacity_then_success", state)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(state.read_text())["status"], "success")
        tokens = self.tokens("capacity_then_success")
        self.assertEqual(len(tokens), 2)
        self.assertNotEqual(tokens[0], tokens[1])

    def test_ambiguous_failure_reuses_token(self):
        state = self.root / "ambiguous-state.json"
        self.run_job("ambiguous_then_success", state)
        self.run_job("ambiguous_then_success", state)
        tokens = self.tokens("ambiguous_then_success")
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0], tokens[1])
        self.assertEqual(json.loads(state.read_text())["status"], "success")

    def test_quota_is_terminal(self):
        state = self.root / "quota-state.json"
        result = self.run_job("quota", state)
        self.assertEqual(result.returncode, 2)
        saved = json.loads(state.read_text())
        self.assertEqual(saved["status"], "fatal")
        self.assertEqual(saved["attempts"], 1)

    def test_running_instance_sends_no_start_action(self):
        state = self.root / "start-state.json"
        result = self.run_job("start_running", state, mode="start")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in (self.root / "start_running.log").read_text().splitlines()]
        self.assertEqual(len(calls), 1)
        self.assertIn("get", calls[0])
        self.assertNotIn("action", calls[0])

    def test_start_acceptance_is_verified_as_running(self):
        state = self.root / "start-verify-state.json"
        result = self.run_job("start_accept_then_running", state, mode="start")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [
            json.loads(line)
            for line in (self.root / "start_accept_then_running.log").read_text().splitlines()
        ]
        self.assertEqual(len(calls), 3)
        self.assertIn("get", calls[0])
        self.assertIn("action", calls[1])
        self.assertIn("get", calls[2])
        self.assertEqual(json.loads(state.read_text())["status"], "success")

    def test_private_key_in_launch_json_is_rejected(self):
        self.request.write_text(json.dumps({"x": "-----BEGIN PRIVATE KEY-----"}))
        state = self.root / "bad-state.json"
        result = self.run_job("capacity_then_success", state)
        self.assertEqual(result.returncode, 2)
        self.assertIn("PEM private key", result.stdout)

    def test_request_change_refuses_existing_state(self):
        state = self.root / "changed-state.json"
        self.run_job("capacity_then_success", state)
        self.request.write_text(json.dumps({"availabilityDomain": "AD-2"}))
        result = self.run_job("capacity_then_success", state)
        self.assertEqual(result.returncode, 2)
        self.assertIn("use a new state file", result.stdout)

    def test_profile_or_region_change_refuses_existing_state(self):
        state = self.root / "identity-state.json"
        self.run_job("capacity_then_success", state, profile="ACCOUNT_A", region="r1")
        result = self.run_job(
            "capacity_then_success", state, profile="ACCOUNT_B", region="r1"
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("profile, region, or OCI config changed", result.stdout)

    def test_max_attempts_cannot_be_increased_mid_job(self):
        state = self.root / "budget-state.json"
        self.run_job("capacity_then_success", state, max_attempts=5)
        result = self.run_job("capacity_then_success", state, max_attempts=6)
        self.assertEqual(result.returncode, 2)
        self.assertIn("use a new state file", result.stdout)

    def test_retry_token_is_saved_before_launch_call(self):
        module = load_module("oci_capacity_retry_crash", RETRY)
        state_path = self.root / "crash-state.json"
        state = {
            "version": 2,
            "mode": "launch",
            "job_fingerprint": "fingerprint",
            "status": "pending",
            "attempts": 0,
            "pending_retry_token": None,
            "instance_id": None,
            "created_at": "now",
            "updated_at": "now",
            "last_classification": None,
            "last_error": None,
            "last_request_id": None,
        }
        args = SimpleNamespace(mode="launch", max_attempts=5)
        original = module.launch_once

        def crash_after_persist(*_args, **_kwargs):
            raise RuntimeError("simulated process crash")

        module.launch_once = crash_after_persist
        try:
            with self.assertRaises(RuntimeError):
                module.run_tick(args, state, state_path)
        finally:
            module.launch_once = original
        saved = json.loads(state_path.read_text())
        self.assertTrue(saved["pending_retry_token"])

    def test_process_timeout_is_ambiguous(self):
        module = load_module("oci_capacity_retry_timeout", RETRY)
        self.assertEqual(
            module.classify_failure("OCI CLI timed out after 120 seconds"),
            "ambiguous",
        )


class RootCloudInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("render_root_cloud_init", RENDER)

    def test_hash_and_template_do_not_contain_plaintext(self):
        password = "Correct-Horse-1234"
        password_hash = self.module.hash_password(password)
        rendered = self.module.TEMPLATE.format(password_hash=password_hash)
        self.assertTrue(password_hash.startswith("$6$"))
        self.assertNotIn(password, rendered)
        self.assertIn("PermitRootLogin yes", rendered)
        self.assertIn("PasswordAuthentication yes", rendered)

    def test_private_output_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cloud-init.yaml"
            self.module.write_private(path, "test")
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_error_path_reports_without_traceback(self):
        original_parse = self.module.parse_args
        original_read = self.module.read_password
        self.module.parse_args = lambda: SimpleNamespace(output=Path("unused"), min_length=14)

        def reject(_minimum):
            raise ValueError("simulated input error")

        self.module.read_password = reject
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                result = self.module.main()
        finally:
            self.module.parse_args = original_parse
            self.module.read_password = original_read
        self.assertEqual(result, 2)
        self.assertIn("simulated input error", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
