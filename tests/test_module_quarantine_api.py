"""HTTP behaviour of module quarantine and the module lifecycle (P0-2 S6).

G4-01 over HTTP is a coded 409 with ``modules/`` unchanged; a broken
external module leaves the backend running with ``/api/health`` degraded.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core import catalog
from gridform_core.module_quarantine import ModuleQuarantinedError, clear_negative_caches
from tests.local_api_harness import start_local_api
from tests.module_lifecycle_fixtures import (
    build_extension_bundle,
    forget_external_code,
    tree_digest,
    write_external_extension,
    write_external_module,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG_NAMES = ("MODULE_REGISTRY", "MODULES", "MODULE_SLOT_BY_ID", "REQUIRED_MODULE_SLOTS", "CATALOG_STALE")


class ModuleQuarantineApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory(prefix="value-p02-api-")
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name) / "state"
        self.modules = self.home / "modules"
        patches = [patch.dict(os.environ, {"VALUE_DATA_HOME": str(self.home)}),
                   patch.object(catalog, "_SNAPSHOT", None)]
        patches += [patch.object(server, name, getattr(server, name)) for name in CATALOG_NAMES]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        clear_negative_caches()
        self.addCleanup(clear_negative_caches)
        self.addCleanup(forget_external_code, self.modules, ("p02_api_broken", "p02_api_ok", "p02_api_hook"))
        context = start_local_api(data_home=self.home)
        self.httpd, self.origin, self.token = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def _request(self, method: str, route: str, body: object = None, headers: dict | None = None):
        data = None
        merged = dict(headers or {})
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            merged.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(self.origin + route, data=data, method=method, headers=merged)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    def _install_extension(self, extension_id: str, namespace: str) -> tuple[int, dict]:
        bundle = build_extension_bundle(Path(self.folder.name) / f"{extension_id}.zip", extension_id, namespace)
        return self._request("POST", "/api/extensions/install", bundle.read_bytes(), {
            "Content-Type": "application/zip", "X-Filename": bundle.name,
            "X-VALUE-Executable-Trust": "acknowledged",
        })

    def test_health_is_degraded_without_ids_or_paths(self) -> None:
        write_external_module(self.modules, "p02-api-broken", "p02_api_broken",
                              prefix="raise RuntimeError('broken import at ' + __file__)\n")
        server.refresh_module_catalog()
        connection = http.client.HTTPConnection(self.origin.removeprefix("http://"), timeout=30)
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        reduced = json.loads(response.read())
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(reduced["status"], "degraded")
        self.assertEqual(reduced["degraded_reasons"], [{"code": "GF_MODULE_IMPORT_FAILED", "count": 1}])
        text = json.dumps(reduced)
        self.assertNotIn("p02-api-broken", text)
        self.assertNotIn(str(self.home), text)
        status, full = self._request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(full["module_quarantine"][0]["id"], "p02-api-broken")
        self.assertNotIn(str(self.home), json.dumps(full["module_quarantine"]))
        status, workspace = self._request("GET", "/api/workspace")
        self.assertEqual(workspace["module_quarantine"]["status"], "degraded")
        entry = workspace["module_quarantine"]["entries"][0]
        self.assertEqual((entry["id"], entry["error_code"], entry["error_type"]),
                         ("p02-api-broken", "GF_MODULE_IMPORT_FAILED", "RuntimeError"))
        self.assertEqual(entry["version"], "1.0.0")  # from the raw manifest, for the S9 panel
        self.assertNotIn(str(self.modules), entry["message"])
        self.assertIn("module_recovery disable module p02-api-broken", entry["corrective_action"])

    def test_g401_sequence_over_http_is_a_coded_409_and_modules_is_unchanged(self) -> None:
        self.assertEqual(self._install_extension("g4-ns-a", "local.g4-shared")[0], 201)
        self.assertEqual(self._request("POST", "/api/extensions/g4-ns-a/disable", {})[0], 200)
        self.assertEqual(self._install_extension("g4-ns-b", "local.g4-shared")[0], 201)
        before = tree_digest(self.modules)
        status, body = self._request("POST", "/api/extensions/g4-ns-a/enable", {})
        self.assertEqual(status, 409)
        self.assertEqual(body["error_code"], "GF_EXTENSION_NAMESPACE_COLLISION")
        self.assertIn("g4-ns-b", body["error"])
        self.assertEqual(tree_digest(self.modules), before)
        status, health = self._request("GET", "/api/health")
        self.assertEqual(health["status"], "ok")

    def test_disabling_an_extension_with_a_broken_hook_clears_health(self) -> None:
        from gridform_core.module_quarantine import ExtensionHookImportError

        write_external_extension(self.modules, "p02-api-hook", "local.p02-api-hook", hook_package="p02_api_hook",
                                 hook_prefix="raise RuntimeError('hook breaks')\n")
        server.refresh_module_catalog()
        with self.assertRaises(ExtensionHookImportError):
            server.MODULE_REGISTRY.extension_registry.resolve(("p02-api-hook",))
        health = self._request("GET", "/api/health")[1]
        self.assertEqual((health["status"], health["degraded_reasons"]),
                         ("degraded", [{"code": "GF_EXTENSION_HOOK_IMPORT", "count": 1}]))
        status, body = self._request("POST", "/api/extensions/p02-api-hook/disable", {})
        self.assertEqual(status, 200, body)
        health = self._request("GET", "/api/health")[1]
        self.assertEqual((health["status"], health["degraded_reasons"]), ("ok", []))
        self.assertEqual(self._request("GET", "/api/workspace")[1]["module_quarantine"]["entries"], [])

    def test_a_damaged_installation_record_degrades_health_until_parked(self) -> None:
        import contextlib
        import io
        from gridform_core import module_recovery
        from gridform_core.execution_archive import _source_roots

        target = write_external_module(self.modules, "p02-api-ok", "p02_api_ok", enabled=False)
        (target / "installation.json").write_text("{damaged", encoding="utf-8")
        server.refresh_module_catalog()
        health = self._request("GET", "/api/health")[1]
        self.assertEqual((health["status"], health["degraded_reasons"]),
                         ("degraded", [{"code": "GF_MODULE_INSTALL_RECORD_INVALID", "count": 1}]))
        entry = self._request("GET", "/api/workspace")[1]["module_quarantine"]["entries"][0]
        self.assertEqual((entry["id"], entry["version"], entry["manifest_file"]),
                         ("p02-api-ok", "1.0.0", "installed/p02-api-ok/1.0.0/installation.json"))
        self.assertIn("park-installation module p02-api-ok 1.0.0", entry["corrective_action"])
        self.assertNotIn("python -m", entry["corrective_action"])
        with contextlib.redirect_stdout(io.StringIO()):
            code = module_recovery.main(["--modules-root", str(self.modules), "park-installation", "module",
                                         "p02-api-ok", "--force"])
        self.assertEqual(code, 0)
        _source_roots(ROOT, self.home)
        health = self._request("GET", "/api/health")[1]
        self.assertEqual((health["status"], health["degraded_reasons"]), ("ok", []))

    def test_a_quarantined_module_referenced_by_a_study_can_be_disabled(self) -> None:
        write_external_module(self.modules, "p02-api-broken", "p02_api_broken", prefix="raise SystemExit(3)\n")
        server.refresh_module_catalog()
        project = self.home / "projects" / "uses-broken" / "project.json"
        project.parent.mkdir(parents=True)
        project.write_text(json.dumps({"id": "uses-broken", "modules": {"storage_cost": "p02-api-broken"}}), "utf-8")
        status, body = self._request("POST", "/api/modules/p02-api-broken/disable", {})
        self.assertEqual(status, 200, body)
        self.assertFalse(body["installation"]["enabled"])
        self.assertFalse((self.modules / "p02-api-broken.json").exists())
        status, health = self._request("GET", "/api/health")
        self.assertEqual(health["status"], "ok")

    def test_pending_runs_need_explicit_confirmation(self) -> None:
        write_external_module(self.modules, "p02-api-ok", "p02_api_ok", enabled=False)
        run = self.home / "runs" / "queued-run"
        run.mkdir(parents=True)
        (run / "status.json").write_text(json.dumps({"id": "queued-run", "status": "queued"}), "utf-8")
        running = self.home / "runs" / "running-run"
        running.mkdir(parents=True)
        (running / "status.json").write_text(json.dumps({"id": "running-run", "status": "running"}), "utf-8")
        before = tree_digest(self.modules)
        with patch("gridform_core.module_quarantine.verify_after_write", lambda *a, **k: None):
            status, body = self._request("POST", "/api/modules/p02-api-ok/enable", {})
            self.assertEqual(status, 409)
            self.assertEqual(body["error_code"], "GF_MODULE_LIFECYCLE_RUNS_PENDING")
            self.assertIn("1 run(s) not started yet (queued-run) will not start", body["error"])  # R6-1 EM-中1
            self.assertIn("1 run(s) already running (running-run) keep their code but could not be resumed",
                          body["error"])
            self.assertEqual(tree_digest(self.modules), before)
            status, body = self._request("POST", "/api/modules/p02-api-ok/enable", {"confirm_pending_runs": True})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["installation"]["enabled"])

    def test_failed_refresh_marks_the_catalogue_stale_until_a_rescan(self) -> None:
        write_external_module(self.modules, "p02-api-ok", "p02_api_ok", enabled=False)
        real = catalog.module_catalog_snapshot
        with patch("gridform_core.module_quarantine.verify_after_write", lambda *a, **k: None), \
                patch.object(catalog, "module_catalog_snapshot", side_effect=RuntimeError("refresh failed")):
            status, body = self._request("POST", "/api/modules/p02-api-ok/enable", {})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["catalog_stale"])
        self.assertEqual(body["warning"]["error_code"], "GF_MODULE_CATALOG_REFRESH")
        status, health = self._request("GET", "/api/health")
        self.assertEqual((health["status"], health["degraded_reasons"]),
                         ("degraded", [{"code": "GF_MODULE_CATALOG_STALE", "count": 1}]))
        project = self.home / "projects" / "study" / "project.json"
        project.parent.mkdir(parents=True)
        project.write_text(json.dumps({"id": "study", "data_pack_id": "pack", "modules": {}}), "utf-8")
        status, body = self._request("POST", "/api/projects/study/runs", {"mode": "smoke"})
        self.assertEqual((status, body["error_code"]), (503, "GF_MODULE_CATALOG_STALE"))
        self.assertIs(catalog.module_catalog_snapshot, real)
        status, body = self._request("POST", "/api/modules/rescan", {})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "ok")
        self.assertIn("p02-api-ok", [row["id"] for row in self._request("GET", "/api/modules")[1]["modules"]])
        self.assertEqual(self._request("GET", "/api/health")[1]["status"], "ok")

    def test_rescan_retries_a_failed_import(self) -> None:
        write_external_module(self.modules, "p02-api-broken", "p02_api_broken",
                              prefix="import p02_api_missing_dependency\n")
        server.refresh_module_catalog()
        self.assertEqual(self._request("GET", "/api/health")[1]["status"], "degraded")
        dependency = self.modules / "installed" / "p02-api-broken" / "1.0.0" / "src" / "p02_api_missing_dependency.py"
        dependency.write_text("VALUE = 1\n", encoding="utf-8")
        server.refresh_module_catalog()
        self.assertEqual(self._request("GET", "/api/health")[1]["status"], "degraded")  # negative cache
        status, body = self._request("POST", "/api/modules/rescan", {})
        self.assertEqual((status, body["status"], body["cleared"]["imports"]), (200, "ok", 1))
        forget_external_code(self.modules, ("p02_api_missing_dependency",))

    def test_rescan_reimports_a_loaded_module_whose_source_broke(self) -> None:
        # R1-4 (M-D5): a module already imported by the backend keeps its old
        # code in sys.modules; Rescan must re-import it and quarantine it.
        target = write_external_module(self.modules, "p02-api-ok", "p02_api_ok")
        server.refresh_module_catalog()
        self.assertEqual(self._request("GET", "/api/health")[1]["status"], "ok")
        plugin = target / "src" / "p02_api_ok" / "plugin.py"
        working = plugin.read_text(encoding="utf-8")
        plugin.write_text("def broken(:\n", encoding="utf-8")
        server.refresh_module_catalog()
        self.assertEqual(self._request("GET", "/api/health")[1]["status"], "ok")  # the loaded copy hides the edit
        status, body = self._request("POST", "/api/modules/rescan", {})
        self.assertEqual((status, body["status"]), (200, "degraded"), body)
        self.assertGreaterEqual(body["reloaded_modules"], 1)
        entry = next(row for row in body["module_quarantine"]["entries"] if row["id"] == "p02-api-ok")
        self.assertEqual((entry["error_code"], entry["error_type"]), ("GF_MODULE_IMPORT_FAILED", "SyntaxError"))
        plugin.write_text(working, encoding="utf-8")
        status, body = self._request("POST", "/api/modules/rescan", {})
        self.assertEqual((status, body["status"]), (200, "ok"), body)
        self.assertIn("p02-api-ok", [row["id"] for row in self._request("GET", "/api/modules")[1]["modules"]])


class ErrorCodeMappingTests(unittest.TestCase):
    def test_coded_lifecycle_errors_map_to_their_status(self) -> None:
        from gridform_core.errors import ContractError
        from gridform_core.execution_archive import ExecutionArchiveError
        from gridform_core.extension_bundle import ExtensionBundleError
        from gridform_core.module_installation import ModuleInstallationError

        cases = [
            (ModuleQuarantinedError("GF_MODULE_PROBE_TIMEOUT", "slow"), 504),
            (ModuleQuarantinedError("GF_MODULE_CATALOG_STALE", "stale"), 503),
            (ExtensionBundleError("GF_EXTENSION_NAMESPACE_COLLISION", "taken"), 409),
            (ModuleInstallationError("GF_MODULE_CONFORMANCE", "fails"), 400),
            (ExecutionArchiveError("bad record", code="GF_EXECUTION_ARCHIVE_MODULE_RECORD"), 409),
            (ContractError("contract"), 400),
        ]
        for error, expected in cases:
            status, body, _ = server.map_request_exception(error)
            self.assertEqual(status, expected, error)
            self.assertEqual(body["error_code"], error.code)
        status, body, _ = server.map_request_exception(ExecutionArchiveError("uncoded"))
        self.assertEqual((status, body["error_code"]), (400, "GF_REQUEST_INVALID"))

    def test_a_damaged_installation_record_has_a_code(self) -> None:
        from gridform_core.execution_archive import ExecutionArchiveError, _source_roots

        with tempfile.TemporaryDirectory(prefix="value-p02-archive-") as folder:
            home = Path(folder)
            target = write_external_module(home / "modules", "p02-damaged", "p02_damaged")
            (target / "installation.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(ExecutionArchiveError) as caught:
                _source_roots(ROOT, home)
        self.assertEqual(caught.exception.code, "GF_EXECUTION_ARCHIVE_MODULE_RECORD")
        self.assertIn("modules/installed/p02-damaged/1.0.0/installation.json", str(caught.exception))
        self.assertIn("park-installation module p02-damaged 1.0.0", str(caught.exception))
        self.assertNotIn(folder, str(caught.exception))


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class BackendProcessSmokeTests(unittest.TestCase):
    def test_backend_with_a_broken_module_starts_degraded_within_20_seconds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-p02-smoke-") as folder:
            home = Path(folder) / "state"
            write_external_module(home / "modules", "p02-smoke-broken", "p02_smoke_broken",
                                  prefix="raise SystemExit(11)\n")
            port = _free_port()
            environment = dict(os.environ)
            environment.update(VALUE_DATA_HOME=str(home), PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
            started = time.monotonic()
            process = subprocess.Popen(
                [sys.executable, "-B", "-m", "backend.server", "--port", str(port)], cwd=ROOT, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            lines: list[str] = []
            try:
                while time.monotonic() - started < 20:
                    line = process.stdout.readline()
                    if not line:
                        break
                    lines.append(line)
                    if "VALUE modular API:" in line:
                        break
                self.assertTrue(any("VALUE modular API:" in line for line in lines), "".join(lines)[-3000:])
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                connection.request("GET", "/api/health")
                health = json.loads(connection.getresponse().read())
                connection.close()
                elapsed = time.monotonic() - started
                self.assertLess(elapsed, 20.0)
                self.assertEqual(health["status"], "degraded")
                self.assertEqual(health["degraded_reasons"], [{"code": "GF_MODULE_IMPORT_FAILED", "count": 1}])
                degraded = [line for line in lines if "VALUE started degraded" in line]
                self.assertEqual(len(degraded), 1, lines)
                self.assertTrue(re.search(r"GF_MODULE_IMPORT_FAILED x1", degraded[0]))
                self.assertNotIn(folder, degraded[0])
            finally:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                process.stdout.close()


if __name__ == "__main__":
    unittest.main()
