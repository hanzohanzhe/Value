import json
import hashlib
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gridform_core.subannual_checkpoint import (
    REQUIRED_INPUT_IDENTITIES,
    REQUIRED_MODULE_IDENTITIES,
    LedgerPrefixIdentity,
    SubannualCheckpointStore,
    SubannualCheckpoint,
    SubannualCheckpointIdentity,
    calendar_month_boundaries,
    checkpoint_content_sha256,
    validate_subannual_checkpoint,
)


ROOT = Path(__file__).resolve().parents[1]
_SHA256 = "a" * 64


def _identity_values(keys: frozenset[str]) -> dict[str, str]:
    return {key: _SHA256 for key in keys}


def _claim_once(root: str, barrier: object, queue: object) -> None:
    """Child-process target for the real exclusive-create claim protocol."""

    barrier.wait()
    try:
        path = SubannualCheckpointStore(Path(root)).claim({"authorization_id": "annual-2028"})
    except FileExistsError:
        queue.put("lost")
    else:
        queue.put(path.name)


class SubannualCheckpointContractTests(unittest.TestCase):
    def test_month_boundary_comes_from_frozen_reference_clock(self) -> None:
        boundaries = calendar_month_boundaries(
            (
                "2022-01-31:47",
                "2022-01-31:48",
                "2022-02-01:01",
                "2022-02-01:02",
            ),
            model_year=2028,
            period_hours=0.5,
            run_id="zonal-run",
        )
        self.assertEqual(len(boundaries), 1)
        self.assertEqual(boundaries[0].calendar_month, 1)
        self.assertEqual(boundaries[0].last_period_index, 1)
        self.assertEqual(boundaries[0].next_period_index, 2)
        self.assertEqual(boundaries[0].boundary_timestamp, "2028-02-01T00:00:00")
        self.assertEqual(boundaries[0].next_period_id, "2022-02-01:01")

    def test_dst_fall_back_periods_do_not_block_october_boundary(self) -> None:
        boundaries = calendar_month_boundaries(
            (
                "2022-10-30:48",
                "2022-10-30:49",
                "2022-10-30:50",
                "2022-10-31:48",
                "2022-11-01:01",
            ),
            model_year=2028,
            period_hours=0.5,
            run_id="zonal-run",
        )

        self.assertEqual(len(boundaries), 1)
        self.assertEqual(boundaries[0].calendar_month, 10)
        self.assertEqual(boundaries[0].last_period_index, 3)
        self.assertEqual(boundaries[0].next_period_id, "2022-11-01:01")

    def test_indexed_teaching_clock_maps_to_calendar_boundaries(self) -> None:
        boundaries = calendar_month_boundaries(
            (
                "2025:1486",
                "2025:1487",
                "2025:1488",
                "2025:1489",
            ),
            model_year=2025,
            period_hours=0.5,
            run_id="teaching-run",
        )
        self.assertEqual(len(boundaries), 1)
        self.assertEqual(boundaries[0].calendar_month, 1)
        self.assertEqual(boundaries[0].last_period_index, 1)
        self.assertEqual(boundaries[0].next_period_id, "2025:1488")

    def test_two_period_indexed_teaching_clock_has_no_month_boundary(self) -> None:
        self.assertEqual(
            calendar_month_boundaries(
                ("2025:0", "2025:1"),
                model_year=2025,
                period_hours=0.5,
                run_id="teaching-run",
            ),
            (),
        )

    def test_unparseable_or_non_monotonic_clock_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "frozen chronology"):
            calendar_month_boundaries(
                ("2022-01-31:48", "bad-period-id"),
                model_year=2028,
                period_hours=0.5,
                run_id="zonal-run",
            )

    def test_schema_requires_the_complete_v1_envelope_without_extras(self) -> None:
        schema = json.loads(
            (ROOT / "gridform_core" / "data" / "contracts" / "subannual-checkpoint-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        required = {
            "schema_version", "checkpoint_id", "run_id", "model_year", "calendar_month",
            "boundary_timestamp", "last_committed_period", "last_committed_period_id",
            "next_period", "next_period_id", "period_hours", "chronology_sha256",
            "chronological_storage_state", "agent_observations", "writer_offsets",
            "random_generator_states", "year_to_date", "frozen_input_hashes",
            "frozen_module_hashes", "parent_annual_checkpoint_identity", "ledger_boundary",
            "publication_state", "content_sha256",
        }
        self.assertEqual(schema["$id"], "urn:value:contract:subannual-checkpoint:v1")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), required)

    def test_checkpoint_hash_excludes_its_declared_content_hash(self) -> None:
        checkpoint = self._checkpoint()
        self.assertEqual(
            checkpoint_content_sha256(checkpoint),
            checkpoint_content_sha256({**checkpoint.to_dict(), "content_sha256": "b" * 64}),
        )

    def test_checkpoint_validation_requires_every_frozen_identity(self) -> None:
        checkpoint = self._checkpoint()
        expected = SubannualCheckpointIdentity(
            run_id="zonal-run",
            model_year=2028,
            period_hours=0.5,
            chronology_sha256=_SHA256,
            frozen_input_hashes=_identity_values(REQUIRED_INPUT_IDENTITIES),
            frozen_module_hashes=_identity_values(REQUIRED_MODULE_IDENTITIES),
        )
        validate_subannual_checkpoint(checkpoint, expected)
        missing = dict(checkpoint.frozen_input_hashes)
        missing.pop("network_pack_id")
        with self.assertRaisesRegex(ValueError, "frozen_input_hashes"):
            validate_subannual_checkpoint(
                SubannualCheckpoint(
                    **{**checkpoint.to_dict(), "frozen_input_hashes": missing}
                ),
                expected,
            )

    def _checkpoint(self) -> SubannualCheckpoint:
        payload = {
            "checkpoint_id": "zonal-run:2028:month-01:period-1",
            "run_id": "zonal-run",
            "model_year": 2028,
            "calendar_month": 1,
            "boundary_timestamp": "2028-02-01T00:00:00",
            "last_committed_period": 1,
            "last_committed_period_id": "2022-01-31:48",
            "next_period": 2,
            "next_period_id": "2022-02-01:01",
            "period_hours": 0.5,
            "chronology_sha256": _SHA256,
            "chronological_storage_state": [],
            "agent_observations": {},
            "writer_offsets": {},
            "random_generator_states": {},
            "year_to_date": {},
            "frozen_input_hashes": _identity_values(REQUIRED_INPUT_IDENTITIES),
            "frozen_module_hashes": _identity_values(REQUIRED_MODULE_IDENTITIES),
            "parent_annual_checkpoint_identity": {},
            "ledger_boundary": LedgerPrefixIdentity(
                database_sha256=_SHA256,
                committed_period_count=2,
                maximum_committed_period=1,
                committed_prefix_sha256=_SHA256,
            ),
            "publication_state": "verified",
            "content_sha256": _SHA256,
        }
        checkpoint = SubannualCheckpoint(**payload)
        return SubannualCheckpoint(
            **{**checkpoint.to_dict(), "content_sha256": checkpoint_content_sha256(checkpoint)}
        )


class SubannualCheckpointStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = SubannualCheckpointStore(self.root)
        self.identity = SubannualCheckpointIdentity(
            run_id="zonal-run",
            model_year=2028,
            period_hours=0.5,
            chronology_sha256=_SHA256,
            frozen_input_hashes=_identity_values(REQUIRED_INPUT_IDENTITIES),
            frozen_module_hashes=_identity_values(REQUIRED_MODULE_IDENTITIES),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_temporary_write_failure_keeps_previous_verified_manifest_usable(self) -> None:
        first = self._checkpoint(month=1, last_period=1439)
        self.store.publish(first)
        with patch("gridform_core.subannual_checkpoint.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.store.publish(self._checkpoint(month=2, last_period=2831))

        candidates = self.store.discover(self.identity)
        self.assertEqual([item.checkpoint_id for item in candidates], [first.checkpoint_id])
        self.assertEqual(
            self.store.load(first.checkpoint_id, self.identity).to_dict(), first.to_dict()
        )

    def test_publish_rechecks_file_and_canonical_hashes_after_rename(self) -> None:
        checkpoint = self._checkpoint(month=1, last_period=1439)
        original_replace = os.replace

        def replace_and_corrupt(source: object, destination: object) -> None:
            original_replace(source, destination)
            if Path(destination) == self._path(checkpoint):
                Path(destination).write_bytes(b"{}\n")

        with patch("gridform_core.subannual_checkpoint.os.replace", side_effect=replace_and_corrupt):
            with self.assertRaisesRegex(ValueError, "complete-file SHA-256"):
                self.store.publish(checkpoint)
        self.assertFalse((self.root / "model-output" / "checkpoints-subannual-v1" / "manifest.json").exists())

    def test_prune_verified_retains_two_newest_months(self) -> None:
        january = self._checkpoint(month=1, last_period=1439)
        february = self._checkpoint(month=2, last_period=2831)
        march = self._checkpoint(month=3, last_period=4319)
        for checkpoint in (january, february, march):
            self.store.publish(checkpoint)

        self.store.prune_verified(year=2028)

        candidates = self.store.discover(self.identity)
        self.assertEqual(
            [item.checkpoint_id for item in candidates],
            [march.checkpoint_id, february.checkpoint_id],
        )
        self.assertFalse(self._path(january).exists())

    def test_prune_manifest_write_failure_preserves_all_published_artifacts(self) -> None:
        checkpoints = [
            self._checkpoint(month=month, last_period=period)
            for month, period in ((1, 1439), (2, 2831), (3, 4319))
        ]
        for checkpoint in checkpoints:
            self.store.publish(checkpoint)
        original_write = self.store._atomic_write

        def fail_manifest(destination: Path, data: bytes) -> None:
            if destination == self.store.manifest_path:
                raise OSError("manifest write failed")
            original_write(destination, data)

        with patch.object(self.store, "_atomic_write", side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, "manifest write failed"):
                self.store.prune_verified(year=2028)

        self.assertEqual(len(self.store.discover(self.identity)), 3)
        self.assertTrue(all(self._path(checkpoint).exists() for checkpoint in checkpoints))

    def test_prune_partial_cleanup_leaves_new_manifest_authoritative(self) -> None:
        january = self._checkpoint(month=1, last_period=1439)
        february = self._checkpoint(month=2, last_period=2831)
        march = self._checkpoint(month=3, last_period=4319)
        for checkpoint in (january, february, march):
            self.store.publish(checkpoint)
        original_unlink = Path.unlink

        def fail_january(path: object, *args: object) -> None:
            if Path(path) == self._path(january):
                raise OSError("cleanup failed")
            original_unlink(path)

        with patch.object(Path, "unlink", autospec=True, side_effect=fail_january):
            self.store.prune_verified(year=2028)

        self.assertEqual(
            [candidate.checkpoint_id for candidate in self.store.discover(self.identity)],
            [march.checkpoint_id, february.checkpoint_id],
        )
        self.assertTrue(self._path(january).exists())

    def test_annual_supersession_removes_only_completed_year_monthly_files(self) -> None:
        completed = self._checkpoint(month=12, last_period=17519, year=2028)
        next_year = self._checkpoint(month=1, last_period=1439, year=2029)
        self.store.publish(completed)
        self.store.publish(next_year)

        self.store.supersede_with_annual(year=2028, annual_checkpoint_sha256="b" * 64)

        self.assertFalse(self._path(completed).exists())
        self.assertTrue(self._path(next_year).exists())
        next_identity = SubannualCheckpointIdentity(
            **{**self.identity.to_dict(), "model_year": 2029}
        )
        self.assertEqual(
            [candidate.checkpoint_id for candidate in self.store.discover(next_identity)],
            [next_year.checkpoint_id],
        )

    def test_annual_manifest_write_failure_preserves_completed_year_artifact(self) -> None:
        completed = self._checkpoint(month=12, last_period=17519, year=2028)
        self.store.publish(completed)
        original_write = self.store._atomic_write

        def fail_manifest(destination: Path, data: bytes) -> None:
            if destination == self.store.manifest_path:
                raise OSError("manifest write failed")
            original_write(destination, data)

        with patch.object(self.store, "_atomic_write", side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, "manifest write failed"):
                self.store.supersede_with_annual(year=2028, annual_checkpoint_sha256="b" * 64)

        self.assertEqual(
            [candidate.checkpoint_id for candidate in self.store.discover(self.identity)],
            [completed.checkpoint_id],
        )
        self.assertTrue(self._path(completed).exists())

    def test_annual_partial_cleanup_keeps_new_manifest_authoritative(self) -> None:
        january = self._checkpoint(month=1, last_period=1439)
        december = self._checkpoint(month=12, last_period=17519)
        for checkpoint in (january, december):
            self.store.publish(checkpoint)
        original_unlink = Path.unlink

        def fail_january(path: object, *args: object) -> None:
            if Path(path) == self._path(january):
                raise OSError("cleanup failed")
            original_unlink(path)

        with patch.object(Path, "unlink", autospec=True, side_effect=fail_january):
            self.store.supersede_with_annual(year=2028, annual_checkpoint_sha256="b" * 64)

        self.assertEqual(self.store.discover(self.identity), ())
        self.assertTrue(self._path(january).exists())
        self.assertFalse(self._path(december).exists())

    def test_same_boundary_changed_content_cannot_replace_published_artifact_before_manifest(self) -> None:
        original = self._checkpoint(month=1, last_period=1439)
        changed = self._checkpoint(month=1, last_period=1439, observations={"revision": 2})
        self.store.publish(original)
        original_path = self._path(original)
        original_bytes = original_path.read_bytes()
        original_write = self.store._atomic_write

        def fail_manifest(destination: Path, data: bytes) -> None:
            if destination == self.store.manifest_path:
                raise OSError("manifest write failed")
            original_write(destination, data)

        with patch.object(self.store, "_atomic_write", side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, "manifest write failed"):
                self.store.publish(changed)

        self.assertNotEqual(self._path(changed), original_path)
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(
            self.store.load(original.checkpoint_id, self.identity).to_dict(), original.to_dict()
        )

    def test_different_run_same_boundary_uses_distinct_artifacts_without_collision(self) -> None:
        first = self._checkpoint(month=1, last_period=1439)
        other = self._checkpoint(month=1, last_period=1439, run_id="other-run")
        self.store.publish(first)
        self.store.publish(other)

        self.assertNotEqual(self._path(first), self._path(other))
        self.assertTrue(self._path(first).exists())
        self.assertTrue(self._path(other).exists())
        self.assertEqual(
            self.store.load(first.checkpoint_id, self.identity).to_dict(), first.to_dict()
        )
        candidates = self.store.discover(self.identity)
        self.assertEqual({candidate.checkpoint_id for candidate in candidates}, {first.checkpoint_id, other.checkpoint_id})
        self.assertTrue(next(candidate for candidate in candidates if candidate.checkpoint_id == first.checkpoint_id).selectable)
        self.assertFalse(next(candidate for candidate in candidates if candidate.checkpoint_id == other.checkpoint_id).selectable)

    def test_latest_corrupt_candidate_is_reported_without_auto_selecting_previous(self) -> None:
        january = self._checkpoint(month=1, last_period=1439)
        february = self._checkpoint(month=2, last_period=2831)
        self.store.publish(january)
        self.store.publish(february)
        self._path(february).write_text("{}\n", encoding="utf-8")

        candidates = self.store.discover(self.identity)

        self.assertEqual(candidates[0].checkpoint_id, february.checkpoint_id)
        self.assertFalse(candidates[0].compatible)
        self.assertFalse(candidates[0].selectable)
        self.assertEqual(candidates[0].mismatch.code, "complete_file_sha256_mismatch")
        self.assertEqual(candidates[1].checkpoint_id, january.checkpoint_id)
        self.assertTrue(candidates[1].selectable)
        with self.assertRaisesRegex(ValueError, "complete-file SHA-256"):
            self.store.load(february.checkpoint_id, self.identity)
        self.assertEqual(
            self.store.load(january.checkpoint_id, self.identity).to_dict(), january.to_dict()
        )

    def test_simultaneous_claims_have_exactly_one_cross_process_winner(self) -> None:
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        queue = context.Queue()
        processes = [
            context.Process(target=_claim_once, args=(str(self.root), barrier, queue))
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(15)
            self.assertEqual(process.exitcode, 0)
        outcomes = sorted(queue.get(timeout=2) for _ in processes)
        self.assertEqual(outcomes, ["annual-2028.claim", "lost"])
        claim = self.root / "model-output" / "checkpoints-subannual-v1" / "claims" / "annual-2028.claim"
        self.assertEqual(
            hashlib.sha256(claim.read_bytes()).hexdigest(),
            hashlib.sha256(b'{"authorization_id":"annual-2028"}\n').hexdigest(),
        )

    def _checkpoint(
        self, *, month: int, last_period: int, year: int = 2028, run_id: str = "zonal-run",
        observations: dict[str, object] | None = None,
    ) -> SubannualCheckpoint:
        payload = {
            "checkpoint_id": f"{run_id}:{year}:month-{month:02d}:period-{last_period}",
            "run_id": run_id,
            "model_year": year,
            "calendar_month": month,
            "boundary_timestamp": f"{year}-{month + 1 if month < 12 else 12:02d}-01T00:00:00",
            "last_committed_period": last_period,
            "last_committed_period_id": "2022-01-31:48",
            "next_period": last_period + 1,
            "next_period_id": "2022-02-01:01",
            "period_hours": 0.5,
            "chronology_sha256": _SHA256,
            "chronological_storage_state": [], "agent_observations": observations or {}, "writer_offsets": {},
            "random_generator_states": {}, "year_to_date": {},
            "frozen_input_hashes": _identity_values(REQUIRED_INPUT_IDENTITIES),
            "frozen_module_hashes": _identity_values(REQUIRED_MODULE_IDENTITIES),
            "parent_annual_checkpoint_identity": {},
            "ledger_boundary": LedgerPrefixIdentity(
                database_sha256=_SHA256, committed_period_count=last_period + 1,
                maximum_committed_period=last_period, committed_prefix_sha256=_SHA256,
            ),
            "publication_state": "verified", "content_sha256": _SHA256,
        }
        checkpoint = SubannualCheckpoint(**payload)
        return SubannualCheckpoint(
            **{**checkpoint.to_dict(), "content_sha256": checkpoint_content_sha256(checkpoint)}
        )

    def _path(self, checkpoint: SubannualCheckpoint) -> Path:
        return (
            self.root / "model-output" / "checkpoints-subannual-v1" / str(checkpoint.model_year)
            / (
                f"month-{checkpoint.calendar_month:02d}-period-{checkpoint.last_committed_period}"
                f"-{checkpoint.content_sha256}.json"
            )
        )


if __name__ == "__main__":
    unittest.main()
