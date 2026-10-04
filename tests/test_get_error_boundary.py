"""P0-3 S7 (F5-05/R1-09): one exception boundary per request, per-record isolation.

Also covers the HTTP side of S2/S4: a repeated cancel only writes the request
file once and the run shows cancel_requested; mark-lost answers through the
route; a Popen failure answers 500 JSON with a visible failed run.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from backend.lifecycle.file_locks import LockTimeout
from backend.lifecycle.run_status import create_status, read_status
from tests.local_api_harness import start_local_api


def _request(url: str, *, method: str = "GET", body: object | None = None, raw: bytes | None = None):
    data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "null"), dict(response.headers)
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8")
        return error.code, json.loads(payload), dict(error.headers)


def _raw_exchange(origin: str, request_text: str) -> bytes:
    host, port = origin.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=30) as connection:
        connection.sendall(request_text.encode("ascii"))
        chunks = []
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


class GetErrorBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, _token = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.runs = self.home / "runs"

    def _run(self, run_id: str, state: str = "completed", **fields) -> Path:
        run_dir = self.runs / run_id
        run_dir.mkdir(parents=True)
        create_status(run_dir, {
            "id": run_id, "project_id": "study", "status": state, "mode": "smoke",
            "execution_engine": "value-annual-orchestrator/v2", "results": [], **fields,
        })
        return run_dir

    def _market_run(self) -> Path:
        run_dir = self._run("market-run")
        market = run_dir / "model-output" / "market"
        market.mkdir(parents=True)
        sqlite3.connect(market / "market.sqlite").close()
        return run_dir

    def test_invalid_query_parameters_answer_400_json(self) -> None:
        self._market_run()
        for value in ("abc", "1e8", "-5"):
            status, payload, _ = _request(f"{self.origin}/api/runs/market-run/market/orders?limit={value}")
            self.assertEqual(status, 400, (value, payload))
            self.assertIn("error", payload)
        status, payload, _ = _request(f"{self.origin}/api/runs/market-run/market/orders?limit=abc")
        self.assertEqual(payload["error_code"], "GF_QUERY_INVALID")
        status, payload, _ = _request(f"{self.origin}/api/runs/market-run/planning/projects?limit=abc")
        self.assertIn(status, {400, 404})
        status, payload, _ = _request(f"{self.origin}/api/comparisons?runs=market-run")
        self.assertEqual(status, 400)
        self.assertIn("2 to 6", payload["error"])

    def test_three_kinds_of_bad_record_keep_workspace_and_runs_online(self) -> None:
        good = self._run("good-run")
        (good.parent / "bad-events").mkdir()
        create_status(good.parent / "bad-events", {
            "id": "bad-events", "project_id": "study", "status": "completed",
            "execution_engine": "value-annual-orchestrator/v2", "results": [],
        })
        events = good.parent / "bad-events" / "model-output"
        events.mkdir()
        (events / "module-events.jsonl").write_text(
            json.dumps({"module_id": "m", "year": None}) + "\n" + json.dumps([1, 2]) + "\n", encoding="utf-8",
        )
        listed = self.runs / "list-status"
        listed.mkdir()
        (listed / "status.json").write_text("[]", encoding="utf-8")
        study = self.home / "projects" / "gbk-study"
        study.mkdir(parents=True)
        (study / "project.json").write_bytes(json.dumps({"id": "gbk-study", "name": "研究"}, ensure_ascii=False).encode("gbk"))
        for route in ("/api/workspace", "/api/runs", "/api/projects"):
            status, payload, _ = _request(self.origin + route)
            self.assertEqual(status, 200, (route, payload))
        status, payload, _ = _request(self.origin + "/api/runs")
        ids = {row["id"] for row in payload["runs"]}
        self.assertEqual(ids, {"good-run", "bad-events"})
        status, payload, _ = _request(self.origin + "/api/runs/bad-events")
        self.assertEqual(status, 200)
        self.assertEqual(payload["module_evidence"]["m"]["years"], [])

    def test_unexpected_errors_answer_500_and_lock_timeouts_503(self) -> None:
        with patch.object(server, "list_packs", side_effect=RuntimeError("/secret/internal/path exploded")):
            status, payload, _ = _request(self.origin + "/api/data-packs")
        self.assertEqual(status, 500)
        self.assertNotIn("/secret/internal/path", json.dumps(payload))
        self.assertIn("error_code", payload)
        with patch.object(server, "list_packs", side_effect=LockTimeout(self.home / "x.lock", 5)):
            status, payload, headers = _request(self.origin + "/api/data-packs")
        self.assertEqual(status, 503)
        self.assertEqual(payload["error_code"], "GF_LOCK_TIMEOUT")
        self.assertEqual(headers.get("Retry-After"), "5")
        status, payload, _ = _request(self.origin + "/api/projects/validate", method="POST", raw=b"{not json")
        self.assertEqual(status, 400)

    def test_failure_after_headers_only_closes_the_connection(self) -> None:
        def half(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(b'{"partial":')
            raise RuntimeError("stream broke")

        for method in ("GET", "POST"):
            target = "_route_get" if method == "GET" else "_route_post"
            with patch.object(server.Handler, target, half):
                raw = _raw_exchange(
                    self.origin,
                    f"{method} /api/runs HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\nConnection: keep-alive\r\n\r\n",
                )
            self.assertEqual(raw.count(b"HTTP/1."), 1, raw[:300])
            self.assertTrue(raw.endswith(b'{"partial":'))

    def test_repeated_cancel_writes_the_request_once(self) -> None:
        run_dir = self._run("active-run", "running")
        status, payload, _ = _request(f"{self.origin}/api/runs/active-run/cancel", method="POST", body={})
        self.assertEqual(status, 202)
        self.assertEqual(payload["run"]["status"], "cancel_requested")
        self.assertEqual(payload["run"]["persisted_status"], "running")
        request = run_dir / "cancel-request.json"
        first = hashlib.sha256(request.read_bytes()).hexdigest()
        status_before = (run_dir / "status.json").read_bytes()
        status, payload, _ = _request(f"{self.origin}/api/runs/active-run/cancel", method="POST", body={})
        self.assertEqual(status, 202)
        self.assertEqual(hashlib.sha256(request.read_bytes()).hexdigest(), first)
        self.assertEqual((run_dir / "status.json").read_bytes(), status_before)
        self.assertEqual(read_status(run_dir)["status"], "running")

    def test_mark_lost_route_requires_confirmation(self) -> None:
        run_dir = self._run("legacy-run", "running")
        (run_dir / "worker.json").write_text(json.dumps({"schema_version": "value.worker-identity/v1", "pid": 1}), "utf-8")
        status, payload, _ = _request(f"{self.origin}/api/runs/legacy-run", method="GET")
        self.assertIn(payload["worker_liveness"], {"lost", "unverifiable"})
        status, payload, _ = _request(f"{self.origin}/api/runs/legacy-run/mark-lost", method="POST", body={})
        self.assertEqual((status, payload["error_code"]), (409, "GF_MARK_LOST_CONFIRMATION_REQUIRED"))


if __name__ == "__main__":
    unittest.main()
