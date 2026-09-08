from __future__ import annotations

import json
import importlib.util
import platform
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_isolated.py"
CONFIG = ROOT / "assets" / "default-config.json"
SPEC = importlib.util.spec_from_file_location("run_isolated", RUNNER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@unittest.skipUnless(platform.system() == "Darwin" and Path("/usr/bin/sandbox-exec").is_file(), "approved macOS sandbox is unavailable")
class IsolatedRunnerTests(unittest.TestCase):
    def test_minimal_docx_runs_inside_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", b"<Types/>")
                archive.writestr("_rels/.rels", b"<Relationships/>")
                archive.writestr("word/document.xml", b"<document><body/></document>")
            completed = subprocess.run(
                [sys.executable, str(RUNNER), "--config", str(CONFIG), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["format"], "docx")
            self.assertFalse(report["privacy"]["content_included"])

    def test_sandbox_denies_neighbor_reads_and_all_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed_input = root / "input.docx"
            neighbor = root / "neighbor.secret"
            output = root / "forbidden-output"
            allowed_input.write_bytes(b"allowed")
            neighbor.write_bytes(b"secret")
            runtime = MODULE._runtime_executable()
            profile = MODULE._sandbox_profile(allowed_input.resolve(), runtime)
            probe = """from pathlib import Path
import sys
results=[]
for operation in (lambda: Path(sys.argv[1]).read_bytes(), lambda: Path(sys.argv[2]).write_bytes(b'x')):
    try: operation(); results.append('allowed')
    except PermissionError: results.append('denied')
print(','.join(results))
"""
            completed = subprocess.run(
                ["/usr/bin/sandbox-exec", "-p", profile, str(runtime), "-I", "-c", probe, str(neighbor), str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "denied,denied")
            self.assertFalse(output.exists())

    def test_sandbox_denies_network_socket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            allowed_input = (Path(tmp) / "input.docx")
            allowed_input.write_bytes(b"allowed")
            runtime = MODULE._runtime_executable()
            profile = MODULE._sandbox_profile(allowed_input.resolve(), runtime)
            probe = """import socket
try:
    sock=socket.socket(); sock.bind(('127.0.0.1', 0)); print('allowed')
except PermissionError:
    print('denied')
"""
            completed = subprocess.run(
                ["/usr/bin/sandbox-exec", "-p", profile, str(runtime), "-I", "-c", probe],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "denied")

    def test_runner_applies_configured_zip_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "contract.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", b"<Types/>")
                archive.writestr("_rels/.rels", b"<Relationships/>")
                archive.writestr("word/document.xml", b"<document/>")
            config = json.loads(CONFIG.read_text(encoding="utf-8"))
            config["document_limits"]["max_zip_entries"] = 1
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(RUNNER), "--config", str(config_path), str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            report = json.loads(completed.stdout)
            self.assertIn("DOCX_ZIP_ENTRY_LIMIT", {item["code"] for item in report["issues"]})

    def test_runner_rejects_input_inside_skill_directory(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(RUNNER), "--config", str(CONFIG), str(ROOT / "SKILL.md")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        report = json.loads(completed.stdout)
        self.assertIn("INPUT_LOCATION_UNSUPPORTED", {item["code"] for item in report["issues"]})


if __name__ == "__main__":
    unittest.main()
