"""A doctoral Run through the product path: POST /runs, then the worker (X0 S8/S9, Q3).

The server preflights the source pack, freezes the inputs and spawns the
worker; the worker verifies the snapshot and runs on ``input-snapshot/pack``.
Replaced: the process spawn (the worker body, ``model_runner.execute``, runs
in process on the Run the server created) and the execution-bundle capture
(archiving and re-hashing the whole source tree takes minutes and is not what
this test is about; ``tests/test_run_execution*`` cover it).  Preflight, the
input snapshot, snapshot verification and the run entry are real.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from gridform_core import methodology
from gridform_core.methodology import COMBINATION_ERROR_CODE, REFERENCE_PROFILE_ID
from gridform_core.project_revision import save_project_revision
from gridform_core.v2.module_manifest import workspace_registry
from tests.test_pack_source_identity import VALUE_101_CANONICAL_SHA, VALUE_101_FILE_SHA, value_101_pinned_by

ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "value-101-baseline-v1"
PACK_ROOT = ROOT / "data-packs" / PACK_ID


class DoctoralWorkerPathTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name)
        shutil.copytree(PACK_ROOT, self.home / "data-packs" / PACK_ID)

    def _save_study(self, study_id: str, profile_id: str) -> None:
        registry = workspace_registry(Path("missing-modules-directory"))
        manifest = json.loads((self.home / "data-packs" / PACK_ID / "manifest.json").read_text(encoding="utf-8"))
        base = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        project = methodology.apply_reference_preset(dict(base, id=study_id), profile_id)
        save_project_revision(self.home / "projects" / study_id, project, registry, manifest)

    @contextlib.contextmanager
    def _api(self):
        """The real local API on this data home; yields ``post(path, body) -> (status, payload)`` and the spawns."""

        from backend import server
        from tests.local_api_harness import start_local_api

        spawned: list[dict] = []
        execution = {"identity_sha256": "e" * 64, "identity_complete": True, "source_sha256": "f" * 64,
                     "environment_sha256": "0" * 64, "limitations": []}
        with start_local_api(data_home=self.home) as (_httpd, origin, _token), \
                patch.object(server, "current_execution", lambda **kwargs: dict(execution)), \
                patch.object(server, "bind_run_execution", lambda project, run_dir, record: project), \
                patch.object(server.RunSupervisor, "spawn_worker",
                             side_effect=lambda **kwargs: spawned.append(kwargs) or {"pid": 0}):
            def post(path: str, body: dict) -> tuple[int, dict]:
                request = urllib.request.Request(
                    origin + path, method="POST", data=json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(request, timeout=300) as response:
                        return response.status, json.loads(response.read())
                except urllib.error.HTTPError as error:
                    return error.code, json.loads(error.read())

            yield post, spawned

    def _start_and_work(self, study_id: str, *, before_worker=None) -> dict:
        from backend import model_runner

        with self._api() as (post, spawned):
            status, payload = post(f"/api/projects/{study_id}/runs", {"mode": "smoke"})
        self.assertIn(status, {200, 201, 202}, payload)
        self.assertEqual(len(spawned), 1)
        run_id = spawned[0]["run_id"]
        run_dir = self.home / "runs" / run_id
        self.assertTrue((run_dir / "input-snapshot" / "pack" / "manifest.json").is_file())
        if before_worker is not None:
            before_worker(run_dir)
        with patch.object(model_runner, "STATE_ROOT", self.home), \
                patch.object(model_runner, "verify_run_execution", lambda *args, **kwargs: None):
            code = model_runner.execute(study_id, run_id, "smoke", status_path=run_dir / "status.json")
        status_payload = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        status_payload["_exit_code"] = code
        return status_payload

    def test_doctoral_d1_completes_from_its_frozen_snapshot(self):
        self._save_study("doctoral-d1", REFERENCE_PROFILE_ID)
        status = self._start_and_work("doctoral-d1")
        self.assertEqual(status["_exit_code"], 0, status.get("error"))
        self.assertEqual(status["status"], "completed", status)
        self.assertEqual(status["methodology"]["profile_id"], REFERENCE_PROFILE_ID)
        frozen = json.loads((self.home / "runs" / status["id"] / "input-snapshot" / "pack" / "manifest.json")
                            .read_text(encoding="utf-8"))
        self.assertTrue(frozen["snapshot_frozen"])
        self.assertEqual(methodology.combination_violations(REFERENCE_PROFILE_ID, data_packs=[(frozen, None)]), [])

    def test_a_pin_by_the_manifest_file_sha_alone_completes_in_the_worker(self):
        """Review round 4 (major): preflight and the worker accept the same sha candidates."""

        with value_101_pinned_by([VALUE_101_FILE_SHA]):
            self._save_study("doctoral-file-pin", REFERENCE_PROFILE_ID)
            status = self._start_and_work("doctoral-file-pin")
        self.assertEqual(status["_exit_code"], 0, status.get("error"))
        self.assertEqual(status["status"], "completed", status)

    def test_a_run_input_snapshot_used_as_the_pack_completes_in_the_worker(self):
        """Review round 4 (minor): a frozen copy frozen again is admitted by preflight and the worker."""

        self._save_study("doctoral-first", REFERENCE_PROFILE_ID)
        first = self._start_and_work("doctoral-first")
        self.assertEqual(first["status"], "completed", first)
        pack = self.home / "data-packs" / PACK_ID
        shutil.rmtree(pack)
        shutil.copytree(self.home / "runs" / first["id"] / "input-snapshot" / "pack", pack)
        for path in pack.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        self._save_study("doctoral-refrozen", REFERENCE_PROFILE_ID)
        status = self._start_and_work("doctoral-refrozen")
        self.assertEqual(status["_exit_code"], 0, status.get("error"))
        self.assertEqual(status["status"], "completed", status)
        frozen = json.loads((self.home / "runs" / status["id"] / "input-snapshot" / "pack" / "manifest.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(methodology.whitelist_manifest(frozen)["id"], PACK_ID)
        self.assertEqual(methodology.manifest_sha256_candidates(frozen),
                         {VALUE_101_FILE_SHA, VALUE_101_CANONICAL_SHA})

    def test_a_refused_combination_in_the_worker_carries_the_profile_code(self):
        """External code enabled between admission and the worker (TOCTOU): the run-entry backstop fires."""

        self._save_study("doctoral-toctou", REFERENCE_PROFILE_ID)

        def enable_external_code(_run_dir):
            self._external = patch.object(methodology, "external_code_entries",
                                          return_value=["module:late-local-module"])
            self._external.start()
            self.addCleanup(self._external.stop)

        status = self._start_and_work("doctoral-toctou", before_worker=enable_external_code)
        self.assertEqual(status["_exit_code"], 1)
        self.assertEqual(status["execution_status"], "failed")
        self.assertEqual(status["error_code"], COMBINATION_ERROR_CODE)
        self.assertEqual(status["error_category"], "methodology")
        self.assertIn("methodology profile", status["error"].lower())


if __name__ == "__main__":
    unittest.main()
