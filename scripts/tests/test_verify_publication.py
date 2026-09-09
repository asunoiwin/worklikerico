import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "verify_publication.py"
SPEC = importlib.util.spec_from_file_location("verify_publication", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PublicationCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text("node_modules/\n*.js.map\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, content="synthetic\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def errors(self):
        candidates = MODULE.publication_candidates(self.root)
        return MODULE.scan_publication(self.root, candidates)

    def test_ignored_dependency_is_excluded_but_tracked_dependency_is_rejected(self):
        dependency = self.write("plugins/example/node_modules/pkg/index.js")
        self.assertEqual(self.errors(), [])

        subprocess.run(["git", "add", "-f", str(dependency.relative_to(self.root))], cwd=self.root, check=True)
        self.assertIn(
            "generated/private path: plugins/example/node_modules/pkg/index.js",
            self.errors(),
        )

    def test_tracked_private_directory_is_rejected(self):
        private = self.write("plugins/example/state/private.txt")
        subprocess.run(["git", "add", str(private.relative_to(self.root))], cwd=self.root, check=True)
        self.assertIn(
            "generated/private path: plugins/example/state/private.txt",
            self.errors(),
        )

    def test_controlled_memory_dist_accepts_only_source_derived_runtime_files(self):
        self.write("plugins/claude/claude-memory-pro/src/mcp-server.ts")
        self.write("plugins/claude/claude-memory-pro/dist/mcp-server.js")
        self.write("plugins/claude/claude-memory-pro/dist/mcp-server.d.ts")
        self.write("plugins/claude/claude-memory-pro/dist/mcp-server.js.map")
        self.assertEqual(self.errors(), [])

        self.write("plugins/claude/claude-memory-pro/dist/extra.js")
        self.assertIn(
            "generated/private path: plugins/claude/claude-memory-pro/dist/extra.js",
            self.errors(),
        )

    def test_other_dist_is_rejected(self):
        self.write("plugins/claude/other/dist/runtime.js")
        self.assertIn(
            "generated/private path: plugins/claude/other/dist/runtime.js",
            self.errors(),
        )


if __name__ == "__main__":
    unittest.main()
