"""P0-1 S7: the installed-instance probe judges real boundaries, not itself.

PASS against the real backend (tests/local_api_harness) behind the real UI
gateway (node); FAIL against a stub without any guard and against a stub that
only checks Host; exit 2 when nothing listens.  The probe never sends the
session token.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import verify_local_security_boundary as probe  # noqa: E402
from tests.local_api_harness import start_local_api  # noqa: E402
from tests.test_ui_gateway_session_path import node_executable  # noqa: E402


class _OpenHandler(BaseHTTPRequestHandler):
    """The pre-P0-1 behaviour: everything is answered, with a permissive CORS grant."""

    host_check = False

    def log_message(self, *_args: object) -> None:
        return

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.host_check and self.headers.get("Host") not in {f"127.0.0.1:{self.server.server_address[1]}"}:
            status = 421
        else:
            status = 200
        body = b'{"ok": true}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_OPTIONS = _answer  # noqa: N815


class _HostOnlyHandler(_OpenHandler):
    host_check = True


def _serve(handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class ProbeVerdictTests(unittest.TestCase):
    def test_open_stub_fails_every_probe(self) -> None:
        server = _serve(_OpenHandler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        report = probe.verify(origin, origin)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertFalse(report["passed"])
        self.assertTrue(all(not row["passed"] for row in report["probes"]))
        self.assertTrue(report["page_problems"])

    def test_host_check_alone_is_not_enough(self) -> None:
        server = _serve(_HostOnlyHandler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_address[1]}"
        report = probe.verify(origin, origin)
        self.assertEqual(report["verdict"], "FAIL")
        passed = {row["name"] for row in report["probes"] if row["passed"]}
        self.assertEqual(passed, set())  # the permissive CORS grant fails even the 421 rows
        failed_on_status = {row["name"] for row in report["probes"] if row["status"] == 200}
        self.assertIn("api-cross-site-text-plain-post", failed_on_status)
        self.assertIn("api-no-session-read", failed_on_status)

    def test_nothing_listening_is_unreachable(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        self.assertEqual(probe.verify(origin, origin)["verdict"], "UNREACHABLE")
        self.assertEqual(probe.main(["--api-origin", origin, "--ui-origin", origin]), 2)

    def test_probe_never_sends_a_session_token_or_destructive_route(self) -> None:
        rows = probe._probes("http://127.0.0.1:18766", "http://127.0.0.1:18800")
        for row, headers, _body in rows:
            self.assertNotIn(row.path, {"/api/tutorials/value-101/reset", "/api/data-packs", "/api/projects"})
            self.assertFalse(row.path.endswith(("/delete", "/archive", "/cancel")))
            if "X-VALUE-Session" in headers:
                self.assertEqual(row.name, "api-forged-session")
        names = {row.name for row, _h, _b in rows}
        self.assertTrue({"api-no-session-module-rescan", "api-no-session-mark-lost"} <= names)


@unittest.skipIf(os.name == "nt", "POSIX node child")
class RealBoundaryProbeTests(unittest.TestCase):
    def test_real_backend_behind_real_gateway_passes(self) -> None:
        node = node_executable()
        if node is None:
            self.skipTest("node is not available (set VALUE_NODE)")
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / "state"
            with start_local_api(data_home=home) as (httpd, api_origin, _token):
                script = (
                    "import http from 'node:http';\n"
                    f"import {{ createGateway, wrapServer }} from {json.dumps((ROOT / 'scripts' / 'value-ui-gateway.mjs').as_uri())};\n"
                    f"const gateway = createGateway({{ upstreamOrigin: {json.dumps(api_origin)}, dataHome: {json.dumps(str(home))}, log: () => {{}} }});\n"
                    "const server = wrapServer(http.createServer((req, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end('<p>VALUE</p>'); }), gateway);\n"
                    "server.listen(0, '127.0.0.1', () => console.log('PORT ' + server.address().port));\n"
                    "process.stdin.on('end', () => process.exit(0)); process.stdin.resume();\n"
                )
                gateway = subprocess.Popen([node, "--input-type=module", "-e", script], cwd=ROOT,
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    line = gateway.stdout.readline()
                    self.assertTrue(line.startswith("PORT "), gateway.stderr.read() if gateway.poll() is not None else line)
                    ui_origin = f"http://127.0.0.1:{int(line.split()[1])}"
                    report = probe.verify(api_origin, ui_origin)
                    failures = [row for row in report["probes"] if not row["passed"]]
                    self.assertEqual(failures, [], json.dumps(failures, indent=2))
                    self.assertEqual(report["page_problems"], [])
                    self.assertEqual(report["verdict"], "PASS")
                    self.assertEqual(probe.main(["--api-origin", api_origin, "--ui-origin", ui_origin]), 0)
                finally:
                    gateway.stdin.close()
                    try:
                        gateway.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        gateway.kill()
                        gateway.wait(timeout=30)
                    gateway.stdout.close()
                    gateway.stderr.close()


if __name__ == "__main__":
    unittest.main()
