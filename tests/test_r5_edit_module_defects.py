"""R5-3 (DECISIONS A28): edit-module role defects of the R4 final-build acceptance.

中1  storage tranche records grew without bound in the full-trace clearing
     declaration (a store kept full by a high fixed offer is topped up with a
     tiny new tranche every period; 20 GB for two VALUE 101 years).  The
     declared state is bounded and recording only: dispatch is unchanged.
中2  with two active manifests of one module ID, Disable on the copy's
     quarantine row disabled the installation and left the copy behind, an
     unrecoverable state.  Disable now parks every manifest of the ID, Enable
     refuses while a copy is active, Remove moves copies too, and the offline
     inventory names a copy left behind by a disabled installation.
低1/低3  wording: readiness remedy for a method upgrade; storage template name.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as kernel
from gridform_core.market_ledger import set_active_market_ledger
from gridform_validation.value_clearing_oracle import audit_declared_storage_limits

ROOT = Path(__file__).resolve().parents[1]


class _Battery:
    def __init__(self, tranches):
        self.name = "battery-a"
        self.battery_type = "1c"
        self.stored_energy = dict(tranches)
        self.power_capacity_mw = 10.0
        self.energy_capacity_mwh = 1000.0
        self.n_1 = 0.95
        self.n_2 = 0.95


class _FullLedger:
    trace_level = "full"


class _SummaryLedger:
    trace_level = "summary"


def _full_battery(count):
    """A store held full by a high offer: one large opening tranche and tiny top-ups."""

    tranches = {-1: 990.0}
    for period in range(count - 1):
        tranches[period] = 0.0002
    return _Battery(tranches)


class DeclaredStorageStateTests(unittest.TestCase):
    def setUp(self) -> None:
        kernel.reset_storage_tranche_record_observation()
        set_active_market_ledger(_FullLedger())
        self.addCleanup(set_active_market_ledger, None)

    def test_small_state_is_recorded_tranche_by_tranche_as_before(self) -> None:
        battery = _full_battery(kernel.STORAGE_STATE_TRANCHE_RECORD_LIMIT)
        (row,) = kernel._storage_pre_state([battery])
        self.assertEqual(
            row["stored_tranches_mwh"],
            [{"charge_period": int(key), "stored_mwh": float(value)} for key, value in battery.stored_energy.items()],
        )
        self.assertNotIn("stored_tranches_aggregate", row)
        self.assertNotIn("stored_tranche_representation", row)
        self.assertEqual(kernel.storage_tranche_record_observation()["compacted_states"], 0)

    def test_large_state_lists_offered_tranches_and_one_aggregate(self) -> None:
        battery = _full_battery(4435)
        offers = [
            {"resource_kind": "storage_discharge", "asset_id": "battery-a", "charge_period": -1},
            {"resource_kind": "storage_discharge", "asset_id": "battery-a", "charge_period": 17},
            {"resource_kind": "generation", "asset_id": "gas", "charge_period": 3},
        ]
        (row,) = kernel._storage_pre_state([battery], offers)
        self.assertEqual(row["stored_tranche_representation"], kernel.STORAGE_STATE_COMPACT_REPRESENTATION)
        self.assertEqual(row["stored_tranche_count"], 4435)
        self.assertEqual([item["charge_period"] for item in row["stored_tranches_mwh"]], [-1, 17])
        aggregate = row["stored_tranches_aggregate"]
        self.assertEqual(aggregate["tranche_count"], 4433)
        self.assertEqual((aggregate["charge_period_min"], aggregate["charge_period_max"]), (0, 4433))
        explicit = sum(item["stored_mwh"] for item in row["stored_tranches_mwh"])
        self.assertAlmostEqual(explicit + aggregate["stored_mwh"], row["state_of_charge_mwh"], places=9)
        self.assertEqual(row["state_of_charge_mwh"], float(sum(battery.stored_energy.values())))
        # Bounded: the reported 536 KB row is now a few hundred bytes.
        legacy = json.dumps([{"charge_period": int(k), "stored_mwh": float(v)} for k, v in battery.stored_energy.items()])
        self.assertGreater(len(legacy), 100_000)
        self.assertLess(len(json.dumps(row)), 2_000)
        observed = kernel.storage_tranche_record_observation()
        self.assertEqual(observed, {"max_tranche_count": 4435, "compacted_states": 1})

    def test_state_is_read_only(self) -> None:
        battery = _full_battery(500)
        before = dict(battery.stored_energy)
        kernel._storage_pre_state([battery], [])
        self.assertEqual(battery.stored_energy, before)
        self.assertEqual(list(battery.stored_energy), list(before))

    def test_summary_trace_builds_no_state(self) -> None:
        set_active_market_ledger(_SummaryLedger())
        self.assertEqual(kernel._storage_pre_state([_full_battery(500)]), [])

    def test_oracle_still_checks_every_offered_tranche(self) -> None:
        battery = _full_battery(400)
        offer = {"resource_kind": "storage_discharge", "asset_id": "battery-a", "charge_period": 5,
                 "maximum_power_mw": 0.0002 * 0.95 / 0.5}
        payload = {"period_hours": 0.5, "offers": [offer]}
        payload["storage_pre_state"] = kernel._storage_pre_state([battery], payload["offers"])
        self.assertTrue(audit_declared_storage_limits(payload)["passed"])
        payload["offers"] = [dict(offer, maximum_power_mw=1.0)]
        result = audit_declared_storage_limits(payload)
        self.assertFalse(result["passed"])
        self.assertEqual(result["violations"][0]["constraint"], "storage_tranche_energy")


_GOLDEN_RUNNER = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, str(Path(sys.argv[1]) / "scripts" / "golden"))
from gridform_core.builtin.scheme_c_1000twh.runtime_compat import modular_simulation_model as m
m.STORAGE_STATE_TRANCHE_RECORD_LIMIT = int(sys.argv[3])
import run_case
run_case.run_case("C3", Path(sys.argv[2]))
print(json.dumps(m.storage_tranche_record_observation()))
"""


class CompactedDeclarationGoldenTests(unittest.TestCase):
    """C3 (full trace, 48 periods) with every declared state compacted vs. as recorded.

    Every market table except the two declaration tables is identical, and
    the independent clearing oracle reaches the same verdict on both.
    """

    def _run(self, folder: Path, limit: int) -> dict:
        env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        completed = subprocess.run(
            [sys.executable, "-B", "-c", _GOLDEN_RUNNER, str(ROOT), str(folder), str(limit)],
            env=env, capture_output=True, text=True, timeout=600, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def test_compaction_changes_no_market_table(self) -> None:
        from gridform_validation.value_clearing_oracle import validate_declared_database

        with tempfile.TemporaryDirectory() as tmp:
            as_recorded = Path(tmp) / "recorded"
            compacted = Path(tmp) / "compacted"
            self.assertEqual(self._run(as_recorded, kernel.STORAGE_STATE_TRANCHE_RECORD_LIMIT)["compacted_states"], 0)
            self.assertGreater(self._run(compacted, -1)["compacted_states"], 0)
            a, b = as_recorded / "market" / "market.sqlite", compacted / "market" / "market.sqlite"
            with closing(sqlite3.connect(a)) as left, closing(sqlite3.connect(b)) as right:
                tables = [row[0] for row in left.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                self.assertIn("storage_state", tables)
                for table in tables:
                    if table in {"clearing_inputs", "clearing_outcomes"}:
                        continue
                    self.assertEqual(
                        left.execute(f"SELECT * FROM {table}").fetchall(),
                        right.execute(f"SELECT * FROM {table}").fetchall(), table,
                    )
                compact_rows = [
                    json.loads(payload)["payload"] for (payload,) in right.execute("SELECT payload_json FROM clearing_inputs")
                ]
            self.assertTrue(any(
                state.get("stored_tranche_representation") == kernel.STORAGE_STATE_COMPACT_REPRESENTATION
                for payload in compact_rows
                for key in ("storage_pre_state", "storage_pre_clearing_state")
                for state in payload.get(key) or []
            ))
            verdicts = []
            for database in (a, b):
                report = validate_declared_database(database)
                verdicts.append({key: report[key] for key in (
                    "declared_rows", "lp_passed_rows", "lp_failed_rows", "storage_transition_failed_rows", "passed")})
            self.assertEqual(verdicts[0], verdicts[1])
            self.assertEqual(verdicts[1]["lp_failed_rows"], 0)


class StorageEstimateWarningTests(unittest.TestCase):
    def test_full_trace_with_a_local_storage_module_warns(self) -> None:
        from gridform_core.preflight import _storage_module_estimate_warning

        issue = _storage_module_estimate_warning({"storage_cost": "hx-flat-offer-73"}, "full")
        self.assertEqual(issue["code"], "GF_PREFLIGHT_ESTIMATE_STORAGE_MODULE")
        self.assertEqual(issue["severity"], "warning")
        self.assertIn("hx-flat-offer-73", issue["message"])

    def test_built_in_module_or_summary_trace_does_not_warn(self) -> None:
        from gridform_core.preflight import _storage_module_estimate_warning

        self.assertIsNone(_storage_module_estimate_warning({"storage_cost": "dynamic-annual-storage-cost"}, "full"))
        self.assertIsNone(_storage_module_estimate_warning({"storage_cost": "hx-flat-offer-73"}, "summary"))
        self.assertIsNone(_storage_module_estimate_warning({}, "full"))


class DuplicateManifestLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        from tests.module_lifecycle_fixtures import forget_external_code, write_external_module

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.modules = Path(temporary.name) / "modules"
        self.modules.mkdir()
        self.addCleanup(forget_external_code, self.modules, ["r53_dup_pkg"])
        write_external_module(self.modules, "r53-dup", "r53_dup_pkg")
        copy = self.modules / "r53-dup-copy.json"
        copy.write_bytes((self.modules / "r53-dup.json").read_bytes())
        self.copy = copy

    def _declaring(self) -> list[str]:
        from gridform_core.module_recovery import active_manifests_declaring

        return [path.name for path in active_manifests_declaring(self.modules, "module", "r53-dup")]

    def test_both_manifests_are_quarantined_first(self) -> None:
        from gridform_core.v2.module_manifest import workspace_registry

        registry = workspace_registry(self.modules)
        self.assertEqual(sorted(entry.code for entry in registry.quarantined), ["GF_MODULE_ID_DUPLICATE"] * 2)
        self.assertEqual(self._declaring(), ["r53-dup-copy.json", "r53-dup.json"])

    def test_disable_parks_the_copy_and_clears_the_quarantine(self) -> None:
        from gridform_core.module_installation import ModuleInstallationError, set_module_enabled
        from gridform_core.v2.module_manifest import workspace_registry

        result = set_module_enabled("r53-dup", False, modules_root=self.modules)
        self.assertFalse(result["enabled"])
        self.assertEqual(self._declaring(), [])
        (parked,) = result["parked_manifests"]
        self.assertTrue(parked.startswith("disabled-manifests/modules/r53-dup-copy."))
        self.assertTrue((self.modules / parked).is_file())
        self.assertEqual(workspace_registry(self.modules).quarantined, ())
        # Enable works again (the installer's own manifest is written back) ...
        enabled = set_module_enabled("r53-dup", True, modules_root=self.modules)
        self.assertTrue(enabled["enabled"])
        self.assertEqual(self._declaring(), ["r53-dup.json"])
        # ... and refuses, naming the file, while a copy is active.
        set_module_enabled("r53-dup", False, modules_root=self.modules)
        self.copy.write_text(json.dumps({"id": "r53-dup"}), encoding="utf-8")
        with self.assertRaises(ModuleInstallationError) as caught:
            set_module_enabled("r53-dup", True, modules_root=self.modules)
        self.assertEqual(caught.exception.code, "GF_MODULE_ID_COLLISION")
        self.assertIn("modules/r53-dup-copy.json", str(caught.exception))

    def test_a_copy_left_by_a_disabled_installation_is_named_and_removable(self) -> None:
        from gridform_core.module_recovery import disable, inventory, remove_installation

        # The state the R4 tester reached: installation disabled, copy still active.
        (self.modules / "r53-dup.json").unlink()
        record_path = next((self.modules / "installed" / "r53-dup").glob("*/installation.json"))
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["enabled"] = False
        record_path.write_text(json.dumps(record), encoding="utf-8")
        rows = [row for row in inventory(self.modules)["entries"] if row["file"] == "r53-dup-copy.json"]
        self.assertIn("active manifest of a disabled installation", rows[0]["problems"])
        self.assertEqual(rows[0]["fix"], "park-manifest module r53-dup-copy.json")
        # Offline disable and Remove both take the copy with them.
        changed = disable(self.modules, "module", "r53-dup")["changed"]
        self.assertTrue(any("r53-dup-copy.json" in item and "(parked)" in item for item in changed))
        self.assertEqual(self._declaring(), [])
        self.copy.write_text(json.dumps({"id": "r53-dup"}), encoding="utf-8")
        removed = remove_installation(self.modules, "module", "r53-dup")
        self.assertTrue(any(item.startswith("r53-dup-copy.json -> ") for item in removed["parked"]))
        self.assertEqual(self._declaring(), [])


class WordingTests(unittest.TestCase):
    def test_method_upgrade_remedy_names_the_real_entry_point(self) -> None:
        source = (ROOT / "gridform_core" / "preflight.py").read_text(encoding="utf-8")
        self.assertNotIn("(POST /api/projects/<id>/revision-migration)", source)
        self.assertIn("Press Check readiness again: VALUE lists the changes for your confirmation", source)

    def test_storage_template_is_named_for_the_fixed_offer_example(self) -> None:
        import io
        import zipfile

        from backend.module_authoring import module_authoring_template
        from gridform_core.v2.module_manifest import builtin_registry

        archive = zipfile.ZipFile(io.BytesIO(module_authoring_template(builtin_registry(), "dynamic-annual-storage-cost")))
        manifest = json.loads(archive.read("value-module.json"))
        self.assertEqual(manifest["name"], "Draft fixed-offer storage example (GBP 42/MWh)")


if __name__ == "__main__":
    unittest.main()
