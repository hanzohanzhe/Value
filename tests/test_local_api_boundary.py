"""P0-1 S6: the local API's own security boundary (F5-01, F4-01, R1-01, R1-02, R1-15).

Every attack of the review is replayed against a real ``backend.server`` (bound
through tests/local_api_harness) with raw ``http.client`` requests, so no test
helper adds a header the attacker would not have.  The two side-effect tests
pair each refused attack with a positive control proving that the same request,
sent the legitimate way, really does change state.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import server  # noqa: E402
from backend.api_security import SECURITY_RESPONSE_HEADERS, evaluate  # noqa: E402
from gridform_core import frontend_contract  # noqa: E402
from tests.local_api_harness import start_local_api  # noqa: E402

PORT = 18766
TOKEN = "s" * 43
REDUCED_HEALTH_KEYS = {
    "ok", "service", "version", "frontend_contract_version", "python", "authoritative_runtime_compatible",
    "session_required", "status", "degraded_reasons",
}


def _headers(**values: str) -> Message:
    message = Message()
    for name, value in values.items():
        message[name.replace("_", "-")] = value
    return message


def _message(pairs: list[tuple[str, str]]) -> Message:
    message = Message()
    for name, value in pairs:
        message[name] = value
    return message


class EvaluateTruthTableTests(unittest.TestCase):
    """The pure decision function: every row is (method, path, headers) -> outcome."""

    def test_truth_table(self) -> None:
        host = ("Host", f"127.0.0.1:{PORT}")
        session = ("X-VALUE-Session", TOKEN)
        json_type = ("Content-Type", "application/json")
        rows = [
            ("GET", "/api/workspace", [host, session], None, True),
            ("GET", "/api/workspace", [("Host", f"localhost:{PORT}"), session], None, True),
            ("GET", "/api/workspace", [("Host", f"LOCALHOST:{PORT}"), session], None, True),
            ("GET", "/api/workspace", [("Host", f"attacker.example:{PORT}"), session], 421, False),
            ("GET", "/api/health", [("Host", "127.0.0.1")], 421, False),
            ("GET", "/api/health", [("Host", f"[::1]:{PORT}")], 421, False),
            ("GET", "/api/health", [("Host", f"127.0.0.1:{PORT + 1}")], 421, False),
            ("GET", "/api/health", [], 421, False),
            ("GET", "/api/health", [host, ("Host", f"attacker.example:{PORT}")], 421, False),
            ("GET", "/api/workspace", [host, session, ("Origin", "https://evil.example")], 403, False),
            ("GET", "/api/workspace", [host, session, ("Origin", "null")], 403, False),
            ("POST", "/api/projects", [host, session, json_type, ("Origin", "http://127.0.0.1:8800")], 403, False),
            ("GET", "/api/workspace", [host, session, ("Sec-Fetch-Site", "cross-site")], 403, False),
            ("GET", "/api/workspace", [host, session, ("Sec-Fetch-Site", "same-origin")], 403, False),
            ("GET", "/api/workspace", [host, session, ("Sec-Fetch-Site", "none")], None, True),
            ("GET", "/api/workspace", [host], 403, False),
            ("GET", "/api/workspace", [host, ("X-VALUE-Session", "s" * 42)], 403, False),
            ("GET", "/api/workspace", [host, session, ("X-VALUE-Session", TOKEN)], 403, False),
            ("GET", "/api/health", [host], None, False),
            ("GET", "/api/health", [host, session], None, True),
            ("GET", "/api/health", [host, ("X-VALUE-Session", "wrong")], 403, False),
            ("POST", "/api/health", [host, json_type], 403, False),
            ("OPTIONS", "/api/modules/install", [host], None, False),
            ("OPTIONS", "/api/modules/install", [host, ("Origin", "http://localhost:3000")], 403, False),
            ("POST", "/api/projects", [host, session, json_type], None, True),
            ("POST", "/api/projects", [host, session, ("Content-Type", "application/json; charset=utf-8")], None, True),
            ("POST", "/api/modules/install", [host, session, ("Content-Type", "application/zip")], None, True),
            ("POST", "/api/projects", [host, session, ("Content-Type", "text/plain")], 415, False),
            ("POST", "/api/projects", [host, session, ("Content-Type", "text/plain;charset=UTF-8")], 415, False),
            ("POST", "/api/projects", [host, session, ("Content-Type", "application/x-www-form-urlencoded")], 415, False),
            ("POST", "/api/projects", [host, session, ("Content-Type", "multipart/form-data; boundary=x")], 415, False),
            ("POST", "/api/projects", [host, session], 415, False),
            ("POST", "/api/projects", [host, session, ("Content-Type", "json")], 415, False),
            ("POST", "/api/projects", [host, session, json_type, ("Content-Length", "abc")], 400, False),
            ("POST", "/api/projects", [host, session, json_type, ("Content-Length", "-1")], 400, False),
            ("POST", "/api/projects", [host, session, json_type, ("Transfer-Encoding", "chunked")], 411, False),
            ("POST", "/api/projects", [host, json_type], 403, False),
        ]
        self.assertGreaterEqual(len(rows), 18)
        for method, path, pairs, status, authenticated in rows:
            with self.subTest(method=method, path=path, headers=pairs):
                decision = evaluate(method, path, _message(pairs), bound_port=PORT, token=TOKEN)
                self.assertEqual(decision.status, status, decision)
                self.assertEqual(decision.authenticated, authenticated)
                if status is not None:
                    self.assertTrue(decision.code.startswith("GF_"))

    def test_order_and_codes(self) -> None:
        host = ("Host", f"127.0.0.1:{PORT}")
        cases = [
            ([("Host", "evil:1"), ("Origin", "https://evil.example")], "GF_HOST_REJECTED"),
            ([host, ("Origin", "https://evil.example"), ("Sec-Fetch-Site", "cross-site")], "GF_BROWSER_ORIGIN_REJECTED"),
            ([host, ("Sec-Fetch-Site", "cross-site")], "GF_BROWSER_CONTEXT_REJECTED"),
            ([host], "GF_SESSION_REQUIRED"),
            ([host, ("X-VALUE-Session", "x")], "GF_SESSION_INVALID"),
            ([host, ("X-VALUE-Session", TOKEN), ("Content-Type", "text/plain")], "GF_CONTENT_TYPE_REJECTED"),
        ]
        for pairs, code in cases:
            with self.subTest(code=code):
                self.assertEqual(evaluate("POST", "/api/x", _message(pairs), bound_port=PORT, token=TOKEN).code, code)

    def test_a_server_without_a_token_refuses_everything_but_tokenless_health(self) -> None:
        host = ("Host", f"127.0.0.1:{PORT}")
        self.assertEqual(evaluate("GET", "/api/workspace", _message([host]), bound_port=PORT, token=None).status, 403)
        self.assertEqual(evaluate("GET", "/api/workspace", _message([host, ("X-VALUE-Session", "")]), bound_port=PORT, token=None).status, 403)
        self.assertIsNone(evaluate("GET", "/api/health", _message([host]), bound_port=PORT, token=None).status)


class LiveBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.home = Path(self._folder.name) / "state"
        env = patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, self.token = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.port = int(self.httpd.server_address[1])
        self.host = f"127.0.0.1:{self.port}"

    # -- raw requests: nothing is added behind the test's back -------------
    def _raw(self, method: str, path: str, headers: list[tuple[str, str]] | None = None, body: bytes | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for name, value in headers or []:
                connection.putheader(name, value)
            if body is not None and not any(name.lower() == "content-length" for name, _ in headers or []):
                connection.putheader("Content-Length", str(len(body)))
            connection.endheaders(body)
            response = connection.getresponse()
            raw = response.read()
            return response.status, dict((key.lower(), value) for key, value in response.getheaders()), raw
        finally:
            connection.close()

    def _authorized(self, *extra: tuple[str, str]) -> list[tuple[str, str]]:
        return [("Host", self.host), ("X-VALUE-Session", self.token), *extra]

    def _tree(self, *roots: Path) -> str:
        digest = hashlib.sha256()
        for root in roots:
            for path in sorted(root.rglob("*")):
                digest.update(path.relative_to(self.home).as_posix().encode())
                if path.is_file():
                    digest.update(hashlib.sha256(path.read_bytes()).digest())
        return digest.hexdigest()

    def _assert_safe_headers(self, headers: dict[str, str]) -> None:
        for name, value in SECURITY_RESPONSE_HEADERS:
            self.assertEqual(headers.get(name.lower()), value, name)
        self.assertFalse([name for name in headers if name.startswith("access-control-")], headers)

    # -- F5-01 / R1-02: blind cross-site writes ---------------------------
    def test_csrf_reset_rejected_with_positive_control(self) -> None:
        guided = {"extensions": {"value_101": {"origin": "guided-course", "course_revision": "value-101/v1",
                                               "variant_kind": "baseline"}}}
        study = self.home / "projects" / "value-study" / "project.json"
        run = self.home / "runs" / "value-run" / "status.json"
        for path, payload in ((study, {"id": "value-study", **guided}),
                              (run, {"id": "value-run", "status": "completed", **guided})):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), "utf-8")
        before = self._tree(self.home / "projects", self.home / "runs", self.home / "trash")
        body = b'{"confirm":true}'
        attacks = [
            ([("Host", self.host), ("Origin", "https://evil.example"), ("Content-Type", "text/plain")], 403),
            ([("Host", self.host), ("Origin", "https://evil.example"), ("Content-Type", "application/x-www-form-urlencoded")], 403),
            ([("Host", self.host), ("Origin", "null"), ("Content-Type", "text/plain")], 403),
            ([("Host", self.host), ("Sec-Fetch-Site", "cross-site"), ("Content-Type", "text/plain")], 403),
            ([("Host", self.host), ("Content-Type", "text/plain")], 403),
            ([("Host", self.host), ("Content-Type", "application/json")], 403),
            ([("Host", f"attacker.example:{self.port}"), ("Content-Type", "application/json")], 421),
            (self._authorized(("Content-Type", "text/plain")), 415),
            (self._authorized(("Origin", f"http://127.0.0.1:{self.port}"), ("Content-Type", "application/json")), 403),
        ]
        for headers, status in attacks:
            with self.subTest(headers=headers):
                code, response_headers, raw = self._raw("POST", "/api/tutorials/value-101/reset", headers, body)
                self.assertEqual(code, status, raw)
                self.assertTrue(response_headers.get("x-value-error-code", "").startswith("GF_"))
                self._assert_safe_headers(response_headers)
        self.assertEqual(self._tree(self.home / "projects", self.home / "runs", self.home / "trash"), before)
        self.assertTrue(study.is_file() and run.is_file())
        # Positive control: the same request through the legitimate path does reset.
        code, _headers, raw = self._raw("POST", "/api/tutorials/value-101/reset",
                                        self._authorized(("Content-Type", "application/json")), body)
        self.assertEqual(code, 200, raw)
        self.assertTrue(json.loads(raw)["ok"])
        self.assertFalse(study.exists())
        self.assertFalse(run.exists())

    def test_cross_site_data_pack_creation_is_refused(self) -> None:
        body = json.dumps({"name": "csrf", "id": "csrf-pack"}).encode()
        for content_type in ("text/plain", "application/x-www-form-urlencoded"):
            code, _h, _raw = self._raw("POST", "/api/data-packs", [("Host", self.host), ("Origin", "https://evil.example"),
                                                                    ("Content-Type", content_type)], body)
            self.assertEqual(code, 403)
        self.assertFalse((self.home / "data-packs" / "csrf-pack").exists())

    # -- F4-01 / R1-01: DNS rebinding to module installation (code execution)
    def test_module_install_rce_with_positive_control(self) -> None:
        from gridform_core.module_bundle import build_module_bundle

        example = ROOT / "examples" / "external_module_bundle"
        source = Path(self._folder.name) / "src"
        shutil.copytree(example / "src", source)
        marker = Path(self._folder.name) / "imported.marker"
        package = source / "value_example_flat_offer" / "__init__.py"
        package.write_text(package.read_text("utf-8") + (
            "\nimport os as _value_test_os\n"
            "if _value_test_os.environ.get('VALUE_TEST_IMPORT_MARKER'):\n"
            "    with open(_value_test_os.environ['VALUE_TEST_IMPORT_MARKER'], 'a') as _value_test_marker:\n"
            "        _value_test_marker.write('imported in pid %d\\n' % _value_test_os.getpid())\n"
        ), "utf-8")
        bundle = Path(self._folder.name) / "rce.zip"
        build_module_bundle(manifest_path=example / "value-module.json", source_root=source,
                            license_path=ROOT / "LICENSE", readme_path=example / "README.md", destination=bundle)
        payload = bundle.read_bytes()
        modules_before = set(sys.modules)
        path_before = list(sys.path)
        self.addCleanup(self._restore_imports, modules_before, path_before)
        with patch.dict(os.environ, {"VALUE_TEST_IMPORT_MARKER": str(marker)}):
            upload = [("Content-Type", "application/zip"), ("X-Filename", "rce.zip"),
                      ("X-VALUE-Executable-Trust", "acknowledged")]
            attacks = [
                ([("Host", f"attacker.example:{self.port}"), *upload], 421),          # DNS rebinding page
                ([("Host", self.host), *upload], 403),                                 # no session
                ([("Host", self.host), ("Origin", "http://localhost:3000"), *upload], 403),  # old CORS allowlist
                ([("Host", self.host), ("Origin", "http://127.0.0.1:18800"), ("X-VALUE-Session", self.token), *upload], 403),
            ]
            for headers, status in attacks:
                with self.subTest(headers=headers[:2]):
                    code, _h, raw = self._raw("POST", "/api/modules/install", headers, payload)
                    self.assertEqual(code, status, raw)
                    self.assertFalse(marker.exists(), "uploaded code ran for a refused request")
            preflight, headers, _raw = self._raw("OPTIONS", "/api/modules/install", [
                ("Host", self.host), ("Origin", "http://localhost:3000"),
                ("Access-Control-Request-Method", "POST"),
                ("Access-Control-Request-Headers", "x-value-executable-trust")])
            self.assertEqual(preflight, 403)
            self.assertFalse([name for name in headers if name.startswith("access-control-")])
            # Positive control: the legitimate, acknowledged install imports the code.
            code, _h, raw = self._raw("POST", "/api/modules/install", self._authorized(*upload), payload)
            self.assertEqual(code, 201, raw)
            self.assertTrue(marker.is_file())
            self.assertIn(f"imported in pid {os.getpid()}", marker.read_text("utf-8"))

    def _restore_imports(self, modules_before: set[str], path_before: list[str]) -> None:
        for name in set(sys.modules) - modules_before:
            if name.startswith("value_example_flat_offer"):
                sys.modules.pop(name, None)
        sys.path[:] = path_before
        server.refresh_module_catalog()

    # -- R1-01: Host check before any body is read, even a large one -------
    def test_forged_host_gets_421_even_with_a_large_body(self) -> None:
        body = b"x" * (1536 * 1024)
        code, headers, raw = self._raw("POST", "/api/data-packs/install", [
            ("Host", f"attacker.example:{self.port}"), ("Content-Type", "application/zip")], body)
        self.assertEqual(code, 421)
        self.assertEqual(json.loads(raw)["error_code"], "GF_HOST_REJECTED")
        self.assertEqual(headers.get("x-value-error-code"), "GF_HOST_REJECTED")
        for host in (f"attacker.example:{self.port}", "127.0.0.1", f"[::1]:{self.port}"):
            code, _h, _raw = self._raw("GET", "/api/health", [("Host", host)])
            self.assertEqual(code, 421, host)

    def test_invalid_content_length_is_400(self) -> None:
        code, _h, raw = self._raw("POST", "/api/projects", self._authorized(
            ("Content-Type", "application/json"), ("Content-Length", "abc")), b"")
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(raw)["error_code"], "GF_CONTENT_LENGTH_INVALID")

    def test_simple_content_types_rejected(self) -> None:
        for content_type in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=a", None):
            headers = self._authorized() + ([("Content-Type", content_type)] if content_type else [])
            code, _h, raw = self._raw("POST", "/api/projects/validate", headers, b"{}")
            self.assertEqual(code, 415, (content_type, raw))
            self.assertEqual(json.loads(raw)["error_code"], "GF_CONTENT_TYPE_REJECTED")
        code, _h, _raw = self._raw("POST", "/api/projects/validate", self._authorized(("Content-Type", "application/json")), b"{}")
        self.assertNotEqual(code, 415)

    # -- R1-15: no CORS at all ---------------------------------------------
    def test_no_cors_headers(self) -> None:
        for method, headers in (
            ("GET", self._authorized()),
            ("OPTIONS", [("Host", self.host)]),
            ("OPTIONS", [("Host", self.host), ("Origin", "http://localhost:8800")]),
            ("GET", [("Host", self.host), ("Origin", "http://127.0.0.1:18800")]),
        ):
            code, response_headers, _raw = self._raw(method, "/api/workspace", headers)
            self.assertIn(code, (200, 204, 403))
            self.assertFalse([name for name in response_headers if name.startswith("access-control-")], response_headers)
        source = (ROOT / "backend" / "server.py").read_text("utf-8")
        self.assertNotIn("ALLOWED_ORIGINS", source)
        self.assertNotIn("Access-Control-", source)

    def test_health_without_a_session_is_reduced(self) -> None:
        code, headers, raw = self._raw("GET", "/api/health", [("Host", self.host)])
        self.assertEqual(code, 200)
        reduced = json.loads(raw)
        self.assertEqual(set(reduced), REDUCED_HEALTH_KEYS)
        self.assertEqual(reduced["service"], "value-modular-local")
        self.assertIs(reduced["session_required"], True)
        # P1 spec 4: the contract the interface checks is the one /api/workspace
        # has always published (gridform_core.frontend_contract); equal to app/lib/api.ts.
        self.assertEqual(server.FRONTEND_CONTRACT_VERSION, "value.expanded-frontend/v1")
        self.assertIs(server.FRONTEND_CONTRACT_VERSION, frontend_contract.FRONTEND_CONTRACT_VERSION)
        self.assertEqual(reduced["frontend_contract_version"], "value.expanded-frontend/v1")
        client = (ROOT / "app" / "lib" / "api.ts").read_text("utf-8")
        match = re.search(r'export const FRONTEND_CONTRACT_VERSION = "([^"]+)";', client)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), server.FRONTEND_CONTRACT_VERSION)
        self.assertNotIn(sys.executable, raw.decode())
        code, _h, raw = self._raw("GET", "/api/health", self._authorized())
        full = json.loads(raw)
        self.assertTrue(REDUCED_HEALTH_KEYS < set(full))
        self.assertIn("runtime_capabilities", full)
        self.assertNotIn(self.token, raw.decode())
        self.assertEqual(full["frontend_contract_version"], "value.expanded-frontend/v1")

    def test_workspace_still_reports_the_existing_frontend_contract(self) -> None:
        # Red line 1: /api/workspace has published this string since the root
        # commit; the W2 health field must not shadow or change it.
        code, _h, raw = self._raw("GET", "/api/workspace", self._authorized())
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(raw)["frontend_contract_version"], "value.expanded-frontend/v1")

    # -- R1-14: every response emitter carries the safety headers ----------
    def test_response_emitters_safe(self) -> None:
        run = self.home / "runs" / "r1"
        (run / "model-output").mkdir(parents=True)
        (run / "status.json").write_text(json.dumps({"id": "r1", "status": "completed", "project_id": "p"}), "utf-8")
        (run / "model-output" / "report.html").write_text("<script>alert(1)</script>", "utf-8")
        cases = [
            ("GET", "/api/health", [("Host", self.host)], None),                     # _json (tokenless)
            ("GET", "/api/workspace", self._authorized(), None),                      # _json
            ("GET", "/api/comparisons?runs=missing&format=csv", self._authorized(), None),  # 404 _json
            ("GET", "/api/runs?limit=abc", self._authorized(), None),                 # mapped 400
            ("GET", "/api/workspace", [("Host", "evil:1")], None),                    # guard 421
            ("OPTIONS", "/api/workspace", [("Host", self.host)], None),               # _route_options
            ("PUT", "/api/workspace", self._authorized(), None),                      # http.server send_error 501
        ]
        for method, path, headers, body in cases:
            with self.subTest(method=method, path=path):
                _code, response_headers, _raw = self._raw(method, path, headers, body)
                self._assert_safe_headers(response_headers)
        code, response_headers, _raw = self._raw("GET", "/api/runs/r1/artifacts", self._authorized())
        self._assert_safe_headers(response_headers)
        # Too many headers: answered by http.server's own send_error, before routing.
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.sock = None
            connection.connect()
            connection.sock.sendall(b"GET /api/health HTTP/1.1\r\nHost: x\r\n" + b"X-Pad: 1\r\n" * 101 + b"\r\n")
            raw = connection.sock.recv(65536).decode("latin-1")
        finally:
            connection.close()
        self.assertRegex(raw, r"^HTTP/1\.[01] 431")
        for name, value in SECURITY_RESPONSE_HEADERS:
            self.assertIn(f"{name}: {value}", raw)

    def test_comparison_csv_is_an_attachment(self) -> None:
        with patch.object(server, "_run_root", side_effect=lambda run_id: self.home), \
                patch.object(server, "build_run_summary", return_value={}), \
                patch.object(server, "compare_run_summaries", return_value={"rows": []}), \
                patch.object(server, "comparison_csv", return_value="a,b\n1,2\n"):
            code, headers, raw = self._raw("GET", "/api/comparisons?runs=a,b&format=csv", self._authorized())
        self.assertEqual(code, 200, raw)
        self.assertTrue(headers["content-type"].startswith("text/csv"))
        self.assertRegex(headers.get("content-disposition", ""), r"^attachment;")
        self._assert_safe_headers(headers)


class StaticGuardPlacementTests(unittest.TestCase):
    def test_guard_runs_before_every_route_including_uploads(self) -> None:
        source = (ROOT / "backend" / "server.py").read_text("utf-8")
        dispatch = re.search(r"def _dispatch\(self, route: Any\) -> None:(.*?)\n    def ", source, re.S).group(1)
        self.assertRegex(dispatch, r"if self\._guard\(\):\s+route\(\)")
        for verb in ("GET", "POST", "OPTIONS"):
            self.assertRegex(source, rf"def do_{verb}\(self\) -> None:.*\n\s+self\._dispatch\(self\._route_{verb.lower()}\)")
        self.assertNotRegex(source, r"def do_(PUT|DELETE|PATCH|HEAD)\(")


if __name__ == "__main__":
    unittest.main()
