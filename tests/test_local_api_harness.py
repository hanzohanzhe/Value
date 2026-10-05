"""P0-1 S2: the shared HTTP test harness (C14) carries the API session."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import server  # noqa: E402
from backend.api_session import authorized_headers, session_path  # noqa: E402
from tests.local_api_harness import start_local_api  # noqa: E402


class _Echo(server.Handler):
    """Answers every GET with the request headers it received."""

    def _route_get(self) -> None:  # type: ignore[override]
        self._json({name.lower(): value for name, value in self.headers.items()})


class HarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.home = Path(self._folder.name) / "state"

    def test_context_yields_token_publishes_session_and_restores_everything(self) -> None:
        previous_opener = urllib.request._opener  # type: ignore[attr-defined]
        original_runs = server.RUNS_ROOT
        with start_local_api(data_home=self.home) as (httpd, origin, token):
            port = httpd.server_address[1]
            self.assertEqual(origin, f"http://127.0.0.1:{port}")
            self.assertNotIn(port, (8766, 8800))
            self.assertIsInstance(token, str)
            self.assertGreaterEqual(len(token), 43)
            self.assertEqual(httpd.session_token, token)
            self.assertEqual(server.RUNS_ROOT, self.home / "runs")
            self.assertEqual(authorized_headers(self.home, port), {"X-VALUE-Session": token})
            self.assertTrue(hasattr(httpd, "data_workbench_api"))
        self.assertIs(urllib.request._opener, previous_opener)  # type: ignore[attr-defined]
        self.assertEqual(server.RUNS_ROOT, original_runs)
        self.assertFalse(session_path(self.home, port).exists())

    def test_opener_adds_only_the_session_header_for_its_own_server(self) -> None:
        with start_local_api(data_home=self.home) as (httpd, origin, token):
            httpd.RequestHandlerClass = _Echo
            seen = json.loads(urllib.request.urlopen(origin + "/api/echo", timeout=10).read())
            self.assertEqual(seen.get("x-value-session"), token)
            self.assertNotIn("origin", seen)
            self.assertNotIn("sec-fetch-site", seen)
            explicit = urllib.request.Request(origin + "/api/echo", headers={"X-VALUE-Session": "mine"})
            seen = json.loads(urllib.request.urlopen(explicit, timeout=10).read())
            self.assertEqual(seen.get("x-value-session"), "mine")
            with start_local_api(data_home=Path(self._folder.name) / "other") as (other, other_origin, other_token):
                other.RequestHandlerClass = _Echo
                # The innermost opener serves only its own origin (once the
                # guard is on, the untagged request is refused before routing).
                try:
                    seen = json.loads(urllib.request.urlopen(origin + "/api/echo", timeout=10).read())
                except urllib.error.HTTPError as exc:
                    self.assertEqual(exc.code, 403)
                    seen = {}
                self.assertNotIn("x-value-session", seen)
                seen = json.loads(urllib.request.urlopen(other_origin + "/api/echo", timeout=10).read())
                self.assertEqual(seen.get("x-value-session"), other_token)

    def test_legacy_mode_leaves_state_roots_and_files_alone(self) -> None:
        original = {name: getattr(server, name) for name in ("STATE_ROOT", "PACKS_ROOT", "RUNS_ROOT")}
        api = start_local_api(data_home=self.home, patch_state_roots=False)
        httpd, origin, token = api.start()
        try:
            self.assertTrue(origin.startswith("http://127.0.0.1:"))
            self.assertEqual({name: getattr(server, name) for name in original}, original)
            self.assertFalse(hasattr(httpd, "data_workbench_api"))
            self.assertFalse(self.home.exists())
        finally:
            api.stop()
        self.assertFalse(self.home.exists())

    def test_harness_never_touches_the_default_user_directory(self) -> None:
        home = Path(self._folder.name) / "home"
        script = (
            "import sys, tempfile, urllib.request\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from pathlib import Path\n"
            "from tests.local_api_harness import start_local_api\n"
            f"with start_local_api(data_home=Path({str(self.home)!r})) as (httpd, origin, token):\n"
            "    urllib.request.urlopen(origin + '/api/data-packs', timeout=30).read()\n"
            "print('ok')\n"
        )
        environment = dict(os.environ, HOME=str(home), XDG_DATA_HOME="", LOCALAPPDATA="",
                           VALUE_DATA_HOME=str(Path(self._folder.name) / "default-never-created"),
                           PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, env=environment,
                                   capture_output=True, text=True, timeout=180)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip().splitlines()[-1], "ok")
        self.assertFalse((Path(self._folder.name) / "default-never-created").exists())
        self.assertFalse((home / ".local" / "share" / "value").exists())

    def test_no_test_starts_the_api_without_the_harness(self) -> None:
        pattern = 'ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)'
        offenders = []
        for path in sorted([*(ROOT / "tests").glob("test_*.py"), *(ROOT / "scripts").glob("*.py")]):
            if path.name in {"test_p0_gate.py", "test_local_api_harness.py", "p0_gate.py"}:
                continue  # the gate's own fixtures quote the forbidden pattern
            if pattern in path.read_text(encoding="utf-8", errors="replace"):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
