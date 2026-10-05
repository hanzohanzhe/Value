"""P0-1 S1: per-port API session file, token comparison and the server factory."""

from __future__ import annotations

import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import api_session  # noqa: E402
from backend.api_session import (  # noqa: E402
    SESSION_HEADER,
    SessionUnavailable,
    authorized_headers,
    new_token,
    publish_session,
    read_session,
    session_path,
    token_matches,
    withdraw_session,
)


def _environment(**extra: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT), environment.get("PYTHONPATH", "")]))
    environment.update(extra)
    return environment


class SessionFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._folder = tempfile.TemporaryDirectory()
        self.state = Path(self._folder.name) / "state"
        self.addCleanup(self._folder.cleanup)

    def test_token_is_random_and_url_safe(self) -> None:
        tokens = {new_token() for _ in range(64)}
        self.assertEqual(len(tokens), 64)
        for token in tokens:
            self.assertGreaterEqual(len(token), 43)
            self.assertRegex(token, r"^[A-Za-z0-9_-]+$")

    def test_session_path_is_named_by_port(self) -> None:
        self.assertEqual(session_path(self.state, 8766), self.state / "runtime" / "api-session-8766.json")
        for bad in (0, 65536, -1):
            with self.assertRaises(ValueError):
                session_path(self.state, bad)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_publish_is_private_and_atomic(self) -> None:
        token = new_token()
        path = publish_session(self.state, 18766, token)
        self.assertEqual(path, session_path(self.state, 18766))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        payload = json.loads(path.read_text("utf-8"))
        self.assertEqual(payload["schema_version"], "value.api-session/v1")
        self.assertEqual(payload["port"], 18766)
        self.assertEqual(payload["pid"], os.getpid())
        self.assertEqual(payload["token"], token)
        # No temporary file is left behind and republishing replaces in place.
        second = new_token()
        publish_session(self.state, 18766, second)
        self.assertEqual(sorted(item.name for item in path.parent.iterdir()), ["api-session-18766.json"])
        self.assertEqual(read_session(self.state, 18766)["token"], second)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_publish_tightens_a_preexisting_runtime_directory(self) -> None:
        (self.state / "runtime").mkdir(parents=True, mode=0o755)
        os.chmod(self.state / "runtime", 0o755)
        publish_session(self.state, 18766, new_token())
        self.assertEqual(stat.S_IMODE((self.state / "runtime").stat().st_mode), 0o700)

    def test_temporary_file_is_created_exclusively_with_mode_0600(self) -> None:
        calls = []
        real_open = os.open

        def recording_open(path, flags, mode=0o777, *args, **kwargs):
            calls.append((Path(path).name, flags, mode))
            return real_open(path, flags, mode, *args, **kwargs)

        with patch.object(api_session.os, "open", recording_open):
            publish_session(self.state, 18766, new_token())
        self.assertEqual(len(calls), 1)
        name, flags, mode = calls[0]
        self.assertTrue(name.endswith(".tmp"))
        self.assertTrue(flags & os.O_EXCL and flags & os.O_CREAT)
        self.assertEqual(mode, 0o600)

    def test_a_failed_write_leaves_no_partial_file(self) -> None:
        with patch.object(api_session.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                publish_session(self.state, 18766, new_token())
        self.assertEqual(list((self.state / "runtime").iterdir()), [])

    def test_two_ports_coexist_and_withdraw_only_their_own_token(self) -> None:
        first, second = new_token(), new_token()
        publish_session(self.state, 8766, first)
        publish_session(self.state, 18766, second)
        self.assertEqual(read_session(self.state, 8766)["token"], first)
        self.assertEqual(read_session(self.state, 18766)["token"], second)
        # A stale backend (different token) never deletes its successor's file.
        self.assertFalse(withdraw_session(self.state, 8766, second))
        self.assertFalse(withdraw_session(self.state, 8766, ""))
        self.assertTrue(session_path(self.state, 8766).is_file())
        self.assertTrue(withdraw_session(self.state, 8766, first))
        self.assertFalse(session_path(self.state, 8766).exists())
        self.assertFalse(withdraw_session(self.state, 8766, first))
        self.assertEqual(read_session(self.state, 18766)["token"], second)

    def test_read_rejects_missing_corrupt_and_foreign_files(self) -> None:
        with self.assertRaises(SessionUnavailable) as caught:
            read_session(self.state, 8766)
        self.assertEqual(caught.exception.path, session_path(self.state, 8766))
        path = session_path(self.state, 8766)
        path.parent.mkdir(parents=True)
        for content in (b"\xff\xfe", b"{not json", b"[]", json.dumps({"schema_version": "x", "token": "t", "port": 8766}).encode(),
                        json.dumps({"schema_version": "value.api-session/v1", "token": "", "port": 8766}).encode(),
                        json.dumps({"schema_version": "value.api-session/v1", "token": "t", "port": 18766}).encode()):
            path.write_bytes(content)
            with self.assertRaises(SessionUnavailable):
                read_session(self.state, 8766)

    def test_token_matches_truth_table(self) -> None:
        token = new_token()
        rows = [
            (token, token, True),
            (token, token + "x", False),
            (token, token[:-1], False),
            (token, "", False),
            ("", "", False),
            (token, None, False),
            (None, token, False),
            (None, None, False),
            (token, token.encode(), False),
            (token, " " + token, False),
            ("é", "é", True),
            ("é", "e", False),
        ]
        for expected, presented, result in rows:
            with self.subTest(expected=expected, presented=presented):
                self.assertIs(token_matches(expected, presented), result)

    def test_authorized_headers_reads_the_published_token(self) -> None:
        token = new_token()
        publish_session(self.state, 18766, token)
        self.assertEqual(authorized_headers(self.state, 18766), {SESSION_HEADER: token})
        self.assertEqual(
            authorized_headers(self.state, 18766, json_body=True),
            {SESSION_HEADER: token, "Content-Type": "application/json"},
        )
        with patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.state)}):
            self.assertEqual(authorized_headers(port=18766)[SESSION_HEADER], token)
        with self.assertRaises(SessionUnavailable):
            authorized_headers(self.state, 8766)

    def test_module_is_standard_library_only(self) -> None:
        import ast

        tree = ast.parse((ROOT / "backend" / "api_session.py").read_text("utf-8"))
        top_level = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                top_level.add(str(node.module).split(".")[0])
        self.assertTrue(top_level <= {"__future__", "hmac", "json", "os", "secrets", "datetime", "pathlib", "typing"}, top_level)


class ServerFactoryTests(unittest.TestCase):
    def test_factory_binds_loopback_without_touching_any_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / "home"
            data_home = Path(folder) / "never-created"
            script = (
                "import json, backend.server as s\n"
                "srv = s.make_api_server('127.0.0.1', 0, session_token='t')\n"
                "print(json.dumps({'port': srv.server_address[1], 'token': srv.session_token,"
                " 'workbench': hasattr(srv, 'data_workbench_api')}))\n"
                "srv.server_close()\n"
                "try:\n"
                "    s.make_api_server('0.0.0.0', 0, session_token='t')\n"
                "except ValueError as exc:\n"
                "    print('rejected', exc)\n"
            )
            completed = subprocess.run(
                [sys.executable, "-B", "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=180,
                env=_environment(HOME=str(home), VALUE_DATA_HOME=str(data_home), XDG_DATA_HOME="", LOCALAPPDATA=""),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            first, second = completed.stdout.strip().splitlines()[-2:]
            payload = json.loads(first)
            self.assertGreater(payload["port"], 0)
            self.assertEqual(payload["token"], "t")
            self.assertFalse(payload["workbench"])
            self.assertIn("rejected", second)
            self.assertFalse(data_home.exists())
            self.assertFalse((home / ".local" / "share" / "value").exists())


class SessionFileIsNeverCopiedTests(unittest.TestCase):
    """The session file is transient process state: no export, archived
    workspace, diagnostic or installer path may carry it (P0-1 identity
    section).  Only the backend module and the UI gateway know its name, and
    no code copies a whole data directory."""

    KNOWN = {"backend/api_session.py", "scripts/value-ui-gateway.mjs", "scripts/serve-value-ui.mjs"}

    def test_only_the_backend_and_the_gateway_name_the_session_file(self) -> None:
        found = set()
        for folder in ("backend", "gridform_core", "scripts", "packaging", "app", "e2e"):
            for path in (ROOT / folder).rglob("*"):
                if path.is_file() and path.suffix in {".py", ".mjs", ".ts", ".tsx", ".ps1", ".sh", ".cmd", ".js"}:
                    if "api-session-" in path.read_text(encoding="utf-8", errors="replace"):
                        found.add(path.relative_to(ROOT).as_posix())
        self.assertEqual(found - self.KNOWN, set())

    def test_archived_workspace_copies_only_named_run_evidence(self) -> None:
        source = (ROOT / "scripts" / "prepare_archived_workspace.py").read_text(encoding="utf-8")
        copies = sorted(set(re.findall(r"copy_tree\(([^,]+),", source)))
        self.assertEqual(copies, ["REPO/'dist'", "REPO/'node_modules'/package", "modules", "source", "source_run/'input-snapshot'"])
        self.assertNotIn("'runtime'", source)


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX signals")
class BackendSessionLifecycleTests(unittest.TestCase):
    def test_backend_publishes_a_private_session_and_withdraws_it_on_exit(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / "state"
            backend = subprocess.Popen(
                [sys.executable, "-B", "-m", "backend.server", "--port", "0"],
                cwd=ROOT, env=_environment(VALUE_DATA_HOME=str(state)),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                line = ""
                for _ in range(50):  # the ready line may follow reconciliation notes
                    line = backend.stdout.readline()
                    if not line or "VALUE modular API" in line:
                        break
                self.assertIn("VALUE modular API: http://127.0.0.1:", line,
                              backend.stderr.read() if backend.poll() is not None else "")
                port = int(line.split("http://127.0.0.1:", 1)[1].split()[0])
                path = session_path(state, port)
                self.assertTrue(path.is_file())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                token = read_session(state, port)["token"]
                self.assertEqual(read_session(state, port)["pid"], backend.pid)
                command_line = Path(f"/proc/{backend.pid}/cmdline").read_bytes()
                self.assertNotIn(token.encode(), command_line)
                self.assertNotIn(token.encode(), Path(f"/proc/{backend.pid}/environ").read_bytes())
            finally:
                backend.send_signal(signal.SIGTERM)
                try:
                    stdout, stderr = backend.communicate(timeout=180)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    stdout, stderr = backend.communicate(timeout=30)
                    self.fail(f"backend did not stop within 180 s after SIGTERM: {stderr[-2000:]}")
            self.assertEqual(backend.returncode, 0, stderr)
            self.assertNotIn(token, line + stdout + stderr)
            deadline = time.monotonic() + 5
            while path.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
