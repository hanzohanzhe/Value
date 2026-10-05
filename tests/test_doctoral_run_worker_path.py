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

from gridform_core import methodology, pack_source_identity
from gridform_core.frozen_input_integrity import verify_frozen_input_integrity
from gridform_core.methodology import COMBINATION_ERROR_CODE, REFERENCE_PROFILE_ID
from gridform_core.project_revision import save_project_revision
from gridform_core.v2.module_manifest import workspace_registry
from tests.test_frozen_input_integrity import rehash_snapshot_identity
from tests.test_pack_source_identity import (
    GBP1_ID, VALUE_101_CANONICAL_SHA, VALUE_101_FILE_SHA, doctoral_pins, gbp1_stand_in, stand_in_shas,
    value_101_pinned_by,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "value-101-baseline-v1"
PACK_ROOT = ROOT / "data-packs" / PACK_ID


def rehash_snapshot(snapshot: Path, manifest_path: Path, manifest: dict) -> None:
    """Rewrite a frozen pack manifest and re-derive the snapshot identity (an older snapshot format)."""

    for path in (manifest_path, snapshot / "snapshot.json"):
        path.chmod(0o644)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    rehash_snapshot_identity(snapshot)


def numeric_leaves(value, path=""):
    """{path: number} for every numeric leaf, timing fields (``*seconds*``) excluded."""

    if isinstance(value, dict):
        rows = {}
        for key, item in value.items():
            if "seconds" not in str(key):
                rows.update(numeric_leaves(item, f"{path}/{key}"))
        return rows
    if isinstance(value, list):
        rows = {}
        for index, item in enumerate(value):
            rows.update(numeric_leaves(item, f"{path}[{index}]"))
        return rows
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {path: value}
    return {}


class DoctoralWorkerPathTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name)
        shutil.copytree(PACK_ROOT, self.home / "data-packs" / PACK_ID)

    def _save_study(self, study_id: str, profile_id: str, pack_id: str = PACK_ID) -> None:
        registry = workspace_registry(Path("missing-modules-directory"))
        manifest = json.loads((self.home / "data-packs" / pack_id / "manifest.json").read_text(encoding="utf-8"))
        base = json.loads((ROOT / "tests" / "golden" / "projects" / "D1.json").read_text(encoding="utf-8"))
        project = methodology.apply_reference_preset(dict(base, id=study_id, data_pack_id=pack_id), profile_id)
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

    def test_a_doctoral_run_is_recovered_into_a_doctoral_study_that_runs(self):
        """Review round 4 (minor): frozen-input recovery of a doctoral Run keeps the Q3 whitelist.

        The recovered base pack (new id, scientific_baseline_eligible false) is
        identified by verified content identity with the pinned VALUE 101 pack;
        Study validation, preflight and the worker on its own frozen copy all
        admit it.
        """

        self._save_study("doctoral-source", REFERENCE_PROFILE_ID)
        source = self._start_and_work("doctoral-source")
        self.assertEqual(source["status"], "completed", source)
        with self._api() as (post, _spawned):
            status, review = post(f"/api/runs/{source['id']}/frozen-recovery/review", {"recovery_mode": "migration"})
            self.assertEqual(status, 200, review)
            self.assertTrue(review["allowed"], review["blocking_reasons"])
            self.assertNotIn("methodology_violations", review)
            status, created = post(f"/api/runs/{source['id']}/frozen-recovery", {
                "name": "Recovered doctoral D1", "acknowledge": True, "recovery_mode": "migration",
                "review_sha256": review["review_sha256"]})
            self.assertEqual(status, 201, created)
        study_id = created["project"]["id"]
        pack_id = created["project"]["data_pack_id"]
        self.assertTrue(pack_id.startswith("recovered-base-"))
        recovered = json.loads((self.home / "data-packs" / pack_id / "manifest.json").read_text(encoding="utf-8"))
        self.assertIs(recovered["scientific_baseline_eligible"], False)
        identity = pack_source_identity.resolve_pack_identity(recovered)
        self.assertEqual((identity.manifest["id"], identity.chain), (PACK_ID, ("recovery",)))
        self.assertEqual(set(identity.sha256_candidates), {VALUE_101_FILE_SHA, VALUE_101_CANONICAL_SHA})
        rerun = self._start_and_work(study_id)
        self.assertEqual(rerun["_exit_code"], 0, rerun.get("error"))
        self.assertEqual(rerun["status"], "completed", rerun)
        self.assertEqual(rerun["methodology"]["profile_id"], REFERENCE_PROFILE_ID)
        frozen = json.loads((self.home / "runs" / rerun["id"] / "input-snapshot" / "pack" / "manifest.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(pack_source_identity.resolve_pack_identity(frozen).chain, ("snapshot", "recovery"))
        # Review round 5: identified as the source means it behaves as the source.
        results = [json.loads((self.home / "runs" / run_id / "model-output" / "year-results-v2.json")
                              .read_text(encoding="utf-8")) for run_id in (source["id"], rerun["id"])]
        expected, actual = (numeric_leaves(item) for item in results)
        self.assertGreater(len(expected), 100)
        self.assertEqual(actual, expected)

    def test_a_doctoral_run_on_an_id_keyed_pack_is_blocked_at_recovery_review(self):
        """Review round 5 (major): model behaviour keys on the GBP1 id, so its recovered copy is not GBP1.

        A VALUE 101 copy under the GBP1 public1 id, pinned by its two shas,
        stands in for GBP1: the source Run is admitted, its recovery is
        blocked at review with the profile code.
        """

        _root, raw = gbp1_stand_in(self.home)
        with doctoral_pins({GBP1_ID: stand_in_shas(raw)}):
            self._save_study("doctoral-gbp1", REFERENCE_PROFILE_ID, pack_id=GBP1_ID)
            source = self._start_and_work("doctoral-gbp1")
            self.assertEqual(source["status"], "completed", source)
            with self._api() as (post, _spawned):
                status, review = post(f"/api/runs/{source['id']}/frozen-recovery/review",
                                      {"recovery_mode": "migration"})
        self.assertEqual(status, 200, review)
        self.assertFalse(review["allowed"])
        rows = review["methodology_violations"]
        self.assertEqual([row["sub_reason"] for row in rows], ["data_pack"])
        self.assertIn("model behaviour keys on the pack id", rows[0]["message"])
        self.assertTrue(any(reason.startswith(COMBINATION_ERROR_CODE) for reason in review["blocking_reasons"]),
                        review["blocking_reasons"])

    def test_recovery_review_blocks_inputs_that_are_not_the_pinned_content(self):
        """A doctoral Run whose recovered pack would not be a pinned pack is blocked at review, not at publish."""

        self._save_study("doctoral-edited", REFERENCE_PROFILE_ID)
        source = self._start_and_work("doctoral-edited")
        self.assertEqual(source["status"], "completed", source)
        snapshot = self.home / "runs" / source["id"] / "input-snapshot"
        # A snapshot frozen before the source record carried the source bytes (v1 record): no verifiable identity.
        manifest_path = snapshot / "pack" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = manifest[pack_source_identity.SOURCE_FIELD]
        manifest[pack_source_identity.SOURCE_FIELD] = {
            "schema_version": "value.snapshot-source-manifest/v1",
            "canonical_sha256": record["canonical_sha256"], "file_sha256": record["file_sha256"],
            "bindings": json.loads(record["manifest_text"])["bindings"]}
        rehash_snapshot(snapshot, manifest_path, manifest)
        status_path = self.home / "runs" / source["id"] / "status.json"
        run_status = json.loads(status_path.read_text(encoding="utf-8"))
        integrity = verify_frozen_input_integrity(snapshot)
        run_status.update(input_snapshot_id=integrity["snapshot_id"], input_tree_sha256=integrity["input_tree_sha256"])
        status_path.write_text(json.dumps(run_status), encoding="utf-8")
        with self._api() as (post, _spawned):
            status, review = post(f"/api/runs/{source['id']}/frozen-recovery/review", {"recovery_mode": "migration"})
        self.assertEqual(status, 200, review)
        self.assertFalse(review["allowed"])
        self.assertEqual([row["sub_reason"] for row in review["methodology_violations"]], ["data_pack"])
        self.assertTrue(any(reason.startswith(COMBINATION_ERROR_CODE) for reason in review["blocking_reasons"]),
                        review["blocking_reasons"])

    def test_a_corrected_run_on_an_id_keyed_pack_states_the_lost_behaviour_at_review(self):
        """Open issue (predates P0): value-corrected admits the recovered pack; the review says what changes."""

        _root, raw = gbp1_stand_in(self.home)
        self._save_study("corrected-gbp1", methodology.default_profile_id(), pack_id=GBP1_ID)
        source = self._start_and_work("corrected-gbp1")
        self.assertEqual(source["status"], "completed", source)
        with self._api() as (post, _spawned):
            status, review = post(f"/api/runs/{source['id']}/frozen-recovery/review", {"recovery_mode": "migration"})
        self.assertEqual(status, 200, review)
        self.assertNotIn("methodology_violations", review)
        self.assertTrue(any(f"Model behaviour keys on the source pack id {GBP1_ID}" in row
                            for row in review["limitations"]), review["limitations"])

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
