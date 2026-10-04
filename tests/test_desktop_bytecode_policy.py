"""P0-3 S9 (R1-07): launchers never read bytecode from app/ or runtime/.

Two independent oracles show what ``pycache_prefix`` changes: the target
interpreter's own ``-v`` import trace, and a tampered-.pyc experiment.  The
desktop controller then tolerates (and quarantines) stray ``__pycache__``
bytecode instead of refusing to start or diagnose, while every other unknown
file, including a .pyc outside ``__pycache__``, is still refused.
"""

from __future__ import annotations

import importlib.util
import io
import json
import marshal
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib.util import MAGIC_NUMBER
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from backend.lifecycle import python_argv

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


desktop = _load("desktop_value_bytecode_policy", "packaging/desktop-local/desktop_value.py")
local = _load("local_value_bytecode_policy", "packaging/linux-local/local_value.py")


def _pyc_for(source_text: str, *, mtime: int, size: int) -> bytes:
    code = compile(source_text, "probe_mod.py", "exec")
    header = MAGIC_NUMBER + (0).to_bytes(4, "little") + mtime.to_bytes(4, "little") + size.to_bytes(4, "little")
    return header + marshal.dumps(code)


def _make_bundle(root: Path) -> dict:
    paths = ["app/backend/server.py", "app/dist/server/index.js", "app/gridform_core/application.py",
             "app/scripts/serve-value-ui.mjs", "app/scripts/install_synthetic_pack.py"]
    runtimes = ({"python": "runtime/python/python.exe", "node": "runtime/node/node.exe"} if sys.platform == "win32"
                else {"python": "runtime/python/bin/python3.10", "node": "runtime/node/bin/node"})
    paths += list(runtimes.values())
    for name in paths:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("fixture")
    manifest = {
        "schema_version": desktop.SCHEMA, "target_platform": sys.platform,
        "architectures": [desktop.architecture(platform.machine())], "teaching_packs": desktop.PACKS,
        "bundled_runtimes": runtimes,
        "files": [{"path": name, "bytes": (root / name).stat().st_size, "sha256": desktop.digest(root / name)}
                  for name in paths],
    }
    (root / "release-manifest.json").write_text(json.dumps(manifest))
    return manifest


def _inject_stray(prefix: Path) -> list[str]:
    names = [f"app/gridform_core/__pycache__/m{index}.cpython-312.pyc" for index in range(39)]
    names += [f"runtime/python/lib/python3.10/pkg{index % 30}/__pycache__/m{index}.cpython-310.pyc" for index in range(660)]
    for name in names:
        path = prefix / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not trusted")
    return names


class ArgvContractTests(unittest.TestCase):
    def test_all_launchers_share_one_isolated_argv(self) -> None:
        expected = ["py", "-B", "-s", "-X", "pycache_prefix=/p"]
        self.assertEqual(python_argv.isolated_python_argv("py", "/p"), expected)
        self.assertEqual(desktop.isolated_python_argv("py", "/p"), expected)
        self.assertEqual(local.isolated_python_argv("py", "/p"), expected)

    def test_every_launcher_interpreter_command_starts_with_the_isolated_argv(self) -> None:
        source = (ROOT / "packaging/desktop-local/desktop_value.py").read_text("utf-8")
        self.assertNotRegex(source, r'\[(?:python|runtime\["python"\]\["path"\]), "-B"')
        self.assertIn('*isolated_python_argv(runtime["python"]["path"], new_pycache_prefix()), "-m", "backend.server"', source)
        self.assertIn('*isolated_python_argv(python, new_pycache_prefix()), "-c", probe', source)
        self.assertIn('*isolated_python_argv(runtime["python"]["path"], new_pycache_prefix()), str(temporary / "app/scripts/install_synthetic_pack.py")', source)
        linux = (ROOT / "packaging/linux-local/local_value.py").read_text("utf-8")
        self.assertIn('"api": [*isolated_python_argv(rt["python"]["path"], pycache), "-m", "backend.server"', linux)
        server = (ROOT / "backend/run_supervisor.py").read_text("utf-8")
        self.assertIn("*worker_python_argv(python, prefix, match_parent_user_site=True)", server)
        self.assertNotIn("unused-bytecode-cache", (ROOT / "backend/server.py").read_text("utf-8"))

    def test_check_runtimes_probe_uses_the_isolated_argv(self) -> None:
        calls = []

        def run(command, **_kwargs):
            calls.append(command)
            if "-p" in command:
                return SimpleNamespace(stdout=json.dumps({"version": "22.20.0", "platform": sys.platform, "arch": "x64"}))
            return SimpleNamespace(stdout=json.dumps({"version": [3, 10, 18], "platform": sys.platform,
                                                      "arch": platform.machine(), "dependencies": {}}))

        manifest = {"target_platform": sys.platform, "architectures": [desktop.architecture(platform.machine())]}
        with mock.patch.object(desktop.subprocess, "run", side_effect=run), \
                mock.patch.object(desktop, "digest", return_value="0" * 64):
            desktop.check_runtimes(sys.executable, sys.executable, manifest)
        prefix = str(desktop.new_pycache_prefix())
        self.assertEqual(calls[0][:5], [sys.executable, "-B", "-s", "-X", f"pycache_prefix={prefix}"])

    def test_clean_environment_sets_a_fresh_empty_prefix(self) -> None:
        with mock.patch.dict(desktop.os.environ, {"PYTHONPYCACHEPREFIX": "/untrusted"}):
            environment = desktop.clean_environment()
        prefix = Path(environment["PYTHONPYCACHEPREFIX"])
        self.assertNotEqual(str(prefix), "/untrusted")
        self.assertTrue(prefix.is_dir())
        self.assertEqual(list(prefix.iterdir()), [])
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")

    def test_full_local_scripts_set_a_fresh_prefix(self) -> None:
        for path in [*(ROOT / "packaging/full-local/linux").glob("*-value"),
                     *(ROOT / "packaging/full-local/macos").glob("*.command")]:
            text = path.read_text("utf-8")
            self.assertIn('PYTHONPYCACHEPREFIX="$(mktemp -d', text, path.name)
            self.assertIn("export PYTHONPYCACHEPREFIX", text, path.name)
            self.assertIn('-B -s "$BUNDLE/installer/desktop_value.py"', text, path.name)
        for path in (ROOT / "packaging/full-local/windows").glob("*.cmd"):
            text = path.read_text("utf-8")
            self.assertRegex(text, r'set "PYTHONPYCACHEPREFIX=%TEMP%\\value-pycache-', path.name)


class BytecodeOracleTests(unittest.TestCase):
    """Run the actual target interpreter (always with -B: it never writes)."""

    def _run(self, argv: list[str], code: str, cwd: Path) -> subprocess.CompletedProcess:
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPYCACHEPREFIX"}
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([*argv, "-c", code], cwd=cwd, env=environment,
                              capture_output=True, text=True, timeout=120)

    def test_verbose_import_trace_never_matches_tree_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            prefix = Path(folder) / "prefix"
            prefix.mkdir()
            code = "import json, decimal, csv, argparse"
            isolated = self._run([*python_argv.isolated_python_argv(sys.executable, prefix), "-v"], code, Path(folder))
            self.assertEqual(isolated.returncode, 0, isolated.stderr[-2000:])
            tree_matches = [line for line in isolated.stderr.splitlines()
                            if "matches" in line and "__pycache__" in line]
            self.assertEqual(tree_matches, [])
            self.assertEqual(list(prefix.iterdir()), [], "-B: nothing is written under the prefix")
            control = self._run([sys.executable, "-B", "-s", "-v"], code, Path(folder))
            runtime_pycache = Path(sys.base_prefix) / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "json" / "__pycache__"
            if runtime_pycache.is_dir() and any(runtime_pycache.glob("*.pyc")):
                self.assertTrue(any("matches" in line and "__pycache__" in line for line in control.stderr.splitlines()),
                                "positive control: without the prefix the runtime's bytecode is read")

    def test_tampered_pyc_is_executed_only_without_the_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_text = "print('SOURCE')\n"
            source = root / "probe_mod.py"
            source.write_text(source_text, encoding="utf-8")
            info = source.stat()
            cache = root / "__pycache__"
            cache.mkdir()
            tag = sys.implementation.cache_tag
            (cache / f"probe_mod.{tag}.pyc").write_bytes(
                _pyc_for("print('TAMPER')\n", mtime=int(info.st_mtime), size=info.st_size)
            )
            without = self._run([sys.executable, "-B", "-s"], "import probe_mod", root)
            self.assertEqual(without.stdout.strip(), "TAMPER", without.stderr)
            prefix = root / "prefix"
            prefix.mkdir()
            isolated = self._run(python_argv.isolated_python_argv(sys.executable, prefix), "import probe_mod", root)
            self.assertEqual(isolated.stdout.strip(), "SOURCE", isolated.stderr)


class StrayBytecodeInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        _make_bundle(self.bundle)
        self.prefix = self.root / "installed"

        def probe(python, node, manifest):
            return {name: {"path": path, "sha256": desktop.digest(path)} for name, path in (("python", python), ("node", node))}

        self.probe = probe
        with mock.patch.object(desktop, "check_runtimes", side_effect=probe), \
                mock.patch.object(desktop.subprocess, "run"), redirect_stdout(io.StringIO()):
            desktop.install(SimpleNamespace(bundle=str(self.bundle), prefix=str(self.prefix), python=None, node=None))
        (self.prefix / "state").mkdir(exist_ok=True)

    def _main(self, *arguments: str) -> tuple[int, str]:
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["desktop_value.py", *arguments]), \
                mock.patch.object(desktop, "check_runtimes", side_effect=self.probe), redirect_stdout(output):
            code = desktop.main()
        return code, output.getvalue()

    def test_699_stray_pyc_are_tolerated_in_installed_mode_only(self) -> None:
        names = _inject_stray(self.prefix)
        stray: list[str] = []
        desktop.verify_inventory(self.prefix, installed=True, stray=stray)
        self.assertEqual(sorted(stray), sorted(names))
        self.assertEqual(len(stray), 699)
        for name in names[:3]:
            (self.bundle / name).parent.mkdir(parents=True, exist_ok=True)
            (self.bundle / name).write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "Inventory differs"):
            desktop.verify_inventory(self.bundle)

    def test_bytecode_outside_pycache_and_other_files_inside_it_are_refused(self) -> None:
        for name in ("app/gridform_core/loose.pyc", "app/gridform_core/__pycache__/evil.py"):
            path = self.prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "Inventory differs"):
                desktop.verify_inventory(self.prefix, installed=True, stray=[])
            path.unlink()

    def test_diagnose_reports_and_repairs_then_start_exits_zero(self) -> None:
        _inject_stray(self.prefix)
        code, output = self._main("diagnose", "--prefix", str(self.prefix))
        self.assertEqual(code, 0)
        report = json.loads(output[: output.index("\n}\n") + 3])
        self.assertEqual(report["bytecode"]["stray_bytecode_files"], 699)
        self.assertIn("--repair-bytecode", report["bytecode"]["hint"])
        code, output = self._main("diagnose", "--prefix", str(self.prefix), "--repair-bytecode")
        self.assertEqual(code, 0)
        report = json.loads(output[: output.index("\n}\n") + 3])
        self.assertEqual(report["bytecode"]["quarantined"], 699)
        self.assertEqual(len(list((self.prefix / "state" / "quarantine").rglob("*.pyc"))), 699)
        code, output = self._main("diagnose", "--prefix", str(self.prefix))
        self.assertEqual(json.loads(output[: output.index("\n}\n") + 3])["bytecode"]["stray_bytecode_files"], 0)

        _inject_stray(self.prefix)
        popen_calls = []

        def popen(command, **_kwargs):
            popen_calls.append(command)
            return SimpleNamespace(poll=lambda: None, terminate=lambda: None, wait=lambda timeout=None: 0, pid=1)

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch.object(desktop, "check_ports"), \
                mock.patch.object(desktop.subprocess, "Popen", side_effect=popen), \
                mock.patch.object(desktop.urllib.request, "urlopen",
                                  side_effect=lambda *_a, **_k: Response(b'{"service": "value-modular-local"}')), \
                mock.patch.object(desktop.time, "sleep", side_effect=[None, KeyboardInterrupt]):
            code, output = self._main("start", "--prefix", str(self.prefix))
        self.assertEqual(code, 0, output)
        self.assertIn("699 stray __pycache__ bytecode file(s) are never read", output)
        backend = popen_calls[0]
        self.assertEqual(backend[1:4], ["-B", "-s", "-X"])
        self.assertTrue(backend[4].startswith("pycache_prefix="))
        self.assertEqual(backend[5:7], ["-m", "backend.server"])

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "POSIX permissions")
    def test_read_only_install_keeps_files_and_still_starts(self) -> None:
        names = _inject_stray(self.prefix)[:39]
        directory = self.prefix / "app" / "gridform_core" / "__pycache__"
        mode = directory.stat().st_mode
        directory.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            moved, failed = desktop.quarantine_bytecode(self.prefix, names)
        finally:
            directory.chmod(mode)
        self.assertEqual(moved, [])
        self.assertEqual(len(failed), 39)
        self.assertTrue(all((self.prefix / name).is_file() for name in names))


class BackgroundRunNoticeTests(unittest.TestCase):
    def test_lists_only_runs_whose_worker_holds_the_lease(self) -> None:
        from backend.lifecycle.file_locks import FileLock

        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            for name in ("running", "finished"):
                (state / "runs" / name).mkdir(parents=True)
                (state / "runs" / name / "worker.lock").write_bytes(b"")
            held = FileLock(state / "runs" / "running" / "worker.lock").acquire()
            try:
                self.assertEqual(desktop.background_runs(state), ["running"])
                if sys.platform.startswith("linux"):
                    self.assertEqual(local.background_runs(state), ["running"])
            finally:
                held.release()
            self.assertEqual(desktop.background_runs(state), [])


if __name__ == "__main__":
    unittest.main()
