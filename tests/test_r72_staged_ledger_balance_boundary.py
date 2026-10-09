"""R7-2 (2): the staged ledger records its PSM identity and balance boundary.

Before R7-2 the staged v8 ledger metadata had no ``psm_module_id`` and no
declared boundary, so the energy-balance oracle ended every staged or zonal
Run with GF_ENERGY_BALANCE_BOUNDARY_UNKNOWN (validation gate not_evaluated).
The metadata is bookkeeping only: the dispatch is unchanged (golden C7/C8,
accounting-zone revision r72.staged-ledger-balance-boundary).
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gridform_core import energy_balance_contract as contract
from gridform_core.energy_balance_oracle import evaluate_ledger, resolve_boundary
from gridform_core.market_ledger import create_staged_market_ledger_v8
from tests.test_prompt95_staged_copperplate import FlatStorageCostDefinition, chronology


def _metadata(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT key, value FROM metadata").fetchall()
    finally:
        connection.close()
    values: dict[str, object] = {}
    for key, value in rows:
        try:
            values[str(key)] = json.loads(value)
        except (TypeError, ValueError):
            values[str(key)] = value
    return values


class StagedLedgerBalanceBoundaryTests(unittest.TestCase):
    def _run_staged(self, output: Path, *, demand: float = 12.0) -> Path:
        from gridform_core.builtin.value_modules import ValueCopperplateBalancing, ValueStagedBidAtCostPSM

        module = ValueStagedBidAtCostPSM()
        balancing = ValueCopperplateBalancing()
        module.configure_run(
            output_dir=output,
            storage_cost=FlatStorageCostDefinition(),
            balancing=balancing,
            expected_balancing_identity=(balancing.id, balancing.version),
            ledger_detail="summary",
        )
        module.run(chronology(forecast=(10.0,), actual=(demand,), vre=(0.5,)))
        self.module = module
        return output / "market" / "market.sqlite"

    def test_staged_ledger_declares_psm_identity_and_full_node_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = self._run_staged(Path(temporary))
            metadata = _metadata(ledger)
            report = evaluate_ledger(ledger)
        self.assertEqual(metadata["psm_module_id"], self.module.id)
        self.assertEqual(metadata["psm_module_version"], self.module.version)
        self.assertEqual(metadata[contract.METADATA_BOUNDARY_KEY], contract.FULL_NODE_V1)
        self.assertIsNone(metadata[contract.METADATA_RULE_SET_KEY])
        boundary = report["boundary"]
        self.assertEqual(boundary["boundary_id"], contract.FULL_NODE_V1)
        self.assertEqual(boundary["source"], "metadata")
        # The tolerance tier comes from the registry entry of the staged PSM.
        self.assertEqual(boundary["tolerance_tier"], contract.LP_SOLVER)
        self.assertIsNotNone(boundary["registry_entry"])
        self.assertNotIn("GF_ENERGY_BALANCE_BOUNDARY_UNKNOWN", report["reasons"])
        self.assertEqual(report["status"], "passed", report["reasons"])
        account = report["balance_account"]
        self.assertEqual(account["open_periods"], 0)

    def test_pre_r72_metadata_resolves_to_an_unknown_boundary(self) -> None:
        # The evidence of the verification run: without the PSM identity and
        # declared boundary the oracle cannot choose a balance equation.
        self.assertEqual(resolve_boundary({})["boundary_id"], contract.UNKNOWN_BOUNDARY)
        self.assertEqual(
            resolve_boundary(dict(contract.STAGED_LEDGER_BALANCE_METADATA, psm_module_id="value-staged-bid-at-cost-psm",
                                  psm_module_version="1.6.0"))["boundary_id"],
            contract.FULL_NODE_V1,
        )

    def test_ledger_created_before_r72_resumes_with_its_own_metadata(self) -> None:
        base = {"run_id": "pre-r72", "data_pack_id": "pack", "period_hours": 0.5}
        added = {
            **contract.STAGED_LEDGER_BALANCE_METADATA,
            "psm_module_id": "value-staged-bid-at-cost-psm",
            "psm_module_version": "1.6.0",
        }
        self.assertEqual(set(added), set(contract.STAGED_LEDGER_R72_METADATA_KEYS))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "market" / "market.sqlite"
            create_staged_market_ledger_v8(path, "summary", semantic_metadata=dict(base)).close_unsealed()
            before = _metadata(path)
            resumed = create_staged_market_ledger_v8(path, "summary", semantic_metadata={**base, **added})
            resumed.close_unsealed()
            after = _metadata(path)
            self.assertEqual(before, after)
            for key in contract.STAGED_LEDGER_R72_METADATA_KEYS:
                self.assertNotIn(key, after)

    def test_r72_ledger_keeps_the_immutability_check(self) -> None:
        base = {"run_id": "r72", "data_pack_id": "pack", "period_hours": 0.5}
        added = {
            **contract.STAGED_LEDGER_BALANCE_METADATA,
            "psm_module_id": "value-staged-bid-at-cost-psm",
            "psm_module_version": "1.6.0",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "market" / "market.sqlite"
            create_staged_market_ledger_v8(path, "summary", semantic_metadata={**base, **added}).close_unsealed()
            create_staged_market_ledger_v8(path, "summary", semantic_metadata={**base, **added}).close_unsealed()
            with self.assertRaisesRegex(Exception, "immutable"):
                create_staged_market_ledger_v8(
                    path, "summary", semantic_metadata={**base, **added, "psm_module_version": "9.9.9"},
                )
            with self.assertRaisesRegex(Exception, "immutable"):
                create_staged_market_ledger_v8(path, "summary", semantic_metadata=dict(base))


if __name__ == "__main__":
    unittest.main()
