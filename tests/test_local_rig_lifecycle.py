"""Pinned source upgrade and real Linux helper lifecycle checks; no model dependencies."""

from __future__ import annotations

import ast
import ctypes
import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/local_rig/helper.py"
SPEC = """from dataclasses import dataclass
from typing import Optional
import os
from ..model.tokenrig import TokenRig

BPY_PORT = 59876
BPY_SERVER = f"http://localhost:{BPY_PORT}"

def get_model(
    ckpt_path: str,
    hf_path: Optional[str]=None,
    device='cuda',
) -> TokenRig:
    model = TokenRig.load_from_system_checkpoint(checkpoint_path=ckpt_path)
    return model
"""
SOURCES = {
    "src/server/bpy_server.py": "def run():\n    bottle.run(host='0.0.0.0')\n",
    "src/server/spec.py": SPEC,
}


def load_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "asset_auto_test_local_rig_bootstrap", ROOT / "scripts/bootstrap_local_rig.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourcePatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bootstrap = load_bootstrap()
        for relative, source in SOURCES.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")

    def patch_sources(self, sources=None):
        sources = SOURCES if sources is None else sources

        def git_show(command, **kwargs):
            self.assertEqual(command[:2], ["git", "show"])
            self.assertEqual(kwargs["cwd"], self.root)
            return sources[command[2].split(":", 1)[1]]

        with patch.object(self.bootstrap, "run", side_effect=git_show):
            return self.bootstrap.patch_source(self.root)

    def test_pristine_upgrade_is_idempotent_and_lazy(self):
        records = self.patch_sources()
        expected = {relative: (self.root / relative).read_bytes() for relative in SOURCES}
        self.assertEqual(records, self.patch_sources())
        for record in records:
            self.assertEqual(record["sha256"], self.bootstrap.digest(self.root / record["path"]))
            self.assertEqual((self.root / record["path"]).read_bytes(), expected[record["path"]])
        tree = ast.parse((self.root / "src/server/spec.py").read_text(encoding="utf-8"))
        self.assertEqual(tree.body[0].module, "__future__")
        self.assertFalse(any(
            isinstance(node, ast.ImportFrom) and node.module == "model.tokenrig"
            for node in tree.body
        ))
        get_model = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
        self.assertIsInstance(get_model.body[0], ast.ImportFrom)
        self.assertEqual(get_model.body[0].module, "model.tokenrig")

    def test_prior_loopback_only_upgrade_preserves_existing_safety(self):
        path = self.root / "src/server/spec.py"
        path.write_text(SPEC.replace(
            "BPY_PORT = 59876", 'BPY_PORT = int(os.environ.get("ASSET_AUTO_BPY_PORT", "59876"))',
        ).replace("http://localhost:{BPY_PORT}", "http://127.0.0.1:{BPY_PORT}"), encoding="utf-8")
        server = self.root / "src/server/bpy_server.py"
        server.write_text(SOURCES["src/server/bpy_server.py"].replace(
            "0.0.0.0", "127.0.0.1",
        ), encoding="utf-8")
        self.patch_sources()
        text = path.read_text(encoding="utf-8")
        self.assertIn("from __future__ import annotations", text)
        self.assertIn('os.environ.get("ASSET_AUTO_BPY_PORT"', text)
        self.assertIn("http://127.0.0.1:{BPY_PORT}", text)
        self.assertIn("host='127.0.0.1'", server.read_text(encoding="utf-8"))

    def test_unexpected_or_partial_edits_are_preserved_without_other_writes(self):
        path = self.root / "src/server/spec.py"
        server = self.root / "src/server/bpy_server.py"
        for content in (SPEC + "# private edit\n", "from __future__ import annotations\n" + SPEC):
            with self.subTest(content=content[:30]):
                path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "Preserving unexpected local changes"):
                    self.patch_sources()
                self.assertEqual(path.read_text(encoding="utf-8"), content)
                self.assertEqual(server.read_text(encoding="utf-8"), SOURCES["src/server/bpy_server.py"])

    def test_missing_pinned_pattern_is_refused_without_writes(self):
        sources = dict(SOURCES)
        sources["src/server/spec.py"] = SPEC.replace("from ..model.tokenrig import TokenRig\n", "")
        with self.assertRaisesRegex(RuntimeError, "Pinned source patch no longer matches"):
            self.patch_sources(sources)
        for relative, original in SOURCES.items():
            self.assertEqual((self.root / relative).read_text(encoding="utf-8"), original)

    def test_missing_worktree_file_is_refused_without_other_writes(self):
        (self.root / "src/server/spec.py").unlink()
        with self.assertRaises(FileNotFoundError):
            self.patch_sources()
        self.assertEqual(
            (self.root / "src/server/bpy_server.py").read_text(encoding="utf-8"),
            SOURCES["src/server/bpy_server.py"],
        )


@unittest.skipUnless(sys.platform == "linux", "Linux kernel parent-death behavior")
class HelperLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="local-rig-helper-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        package = self.root / "src/server"
        package.mkdir(parents=True)
        (package.parent / "__init__.py").write_text("", encoding="utf-8")
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "bpy_server.py").write_text(
            "import os, time\nfrom pathlib import Path\n"
            "Path('imported').write_text(str(os.getpid()))\n"
            "def run():\n    Path('ready').write_text(str(os.getpid()))\n    time.sleep(60)\n",
            encoding="utf-8",
        )

    def test_wrong_parent_is_refused_before_upstream_import(self):
        result = subprocess.run(
            [sys.executable, str(HELPER), "--source-root", str(self.root),
             "--parent-pid", str(os.getpid() + 1000000)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Inference parent exited or changed", result.stderr)
        self.assertFalse((self.root / "imported").exists())

    def test_parent_sigkill_terminates_running_helper(self):
        # Adopt the deliberately orphaned grandchild so this test can reap it even
        # when the host's init does not reap promptly (including some WSL installs).
        libc = ctypes.CDLL(None, use_errno=True)
        prior = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(prior), 0, 0, 0), 0)  # GET_CHILD_SUBREAPER
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)  # SET_CHILD_SUBREAPER
        parent = None
        child_pid = None
        reaped = False
        try:
            parent = subprocess.Popen([
                sys.executable, "-c",
                ("import os, subprocess, sys, time\nfrom pathlib import Path\n"
                "child=subprocess.Popen([sys.executable, sys.argv[1], '--source-root', sys.argv[2], "
                "'--parent-pid', str(os.getpid())])\n"
                "Path(sys.argv[2], 'child-pid').write_text(str(child.pid))\n"
                 "time.sleep(60)\n"),
                str(HELPER), str(self.root),
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 10
            while not (self.root / "ready").is_file():
                self.assertIsNone(parent.poll())
                self.assertLess(time.monotonic(), deadline, "helper did not start")
                time.sleep(0.02)
            child_pid = int((self.root / "child-pid").read_text())
            self.assertEqual(int((self.root / "ready").read_text()), child_pid)
            os.kill(child_pid, 0)
            parent.kill()
            parent.wait(timeout=5)
            deadline = time.monotonic() + 5
            while True:
                pid, status = os.waitpid(child_pid, os.WNOHANG)
                if pid:
                    reaped = True
                    self.assertTrue(os.WIFSIGNALED(status))
                    self.assertEqual(os.WTERMSIG(status), signal.SIGTERM)
                    break
                self.assertLess(time.monotonic(), deadline, "orphaned helper survived parent SIGKILL")
                time.sleep(0.02)
        finally:
            if parent is not None and parent.poll() is None:
                parent.kill()
                parent.wait(timeout=5)
            pid_file = self.root / "child-pid"
            if child_pid is None and pid_file.exists():
                child_pid = int(pid_file.read_text())
            if child_pid is not None and not reaped:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(child_pid, 0)
                except ChildProcessError:
                    pass
            libc.prctl(36, prior.value, 0, 0, 0)


if __name__ == "__main__":
    unittest.main()
