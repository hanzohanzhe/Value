"""P0-4 S7: validation gates of the production profile, declared-deviation
signatures of the doctoral reproduction profile, and the Q14 consequence.

The VALUE 101 variants of :mod:`tests.p04_variants` run once (one subprocess
each): the doctoral market rule set for ``baseline``, ``nuclear_balancing``
and ``overshoot`` (the 0.6.0-alpha.2 kernel defects), and the Study's own
corrected rule set for ``baseline`` and ``overshoot``.  Their ledgers are then
read under both gate policies.

R4-1 (DECISIONS A26) corrected the two kernel defects these runs exercised
(DEV-BAL-04 in ``nuclear_balancing``, DEV-STO-01 in the doctoral storage
dispatch) in both profiles and withdrew their declared deviations, so the
doctoral runs now pass both gates and no declared deviation explains a gate
failure; tampered ledgers show that a failure stays ``failed``.
"""

from __future__ import annotations

import concurrent.futures
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gridform_core import declared_deviations
from gridform_core import energy_balance_oracle as oracle
from gridform_core.bundle_validator import _validation_evidence_errors
from gridform_core.market_replay import query_dispatch_timeline
from gridform_core.methodology import REFERENCE_PROFILE_ID, resolve_methodology
from gridform_core.result_advisories import result_publication
from gridform_core.scientific_validation import (
    FAILED,
    NOT_EVALUATED,
    PASSED,
    RETAINED_COMPARISON_INFORMATIONAL,
    MechanismCheck,
    build_scientific_validation_report,
)
from tests import p04_variants

RUNS = (
    ("baseline", "doctoral"),
    ("nuclear_balancing", "doctoral"),
    ("overshoot", "doctoral"),
    ("baseline", "profile"),
    ("overshoot", "profile"),
)
CONFORMANT = "reproduction_conformant"
DECLARED = "reproduction_with_declared_deviations"


def _parity() -> dict:
    return {"schema_version": "value.stage-parity/v3", "contract_parity_passed": True,
            "checks": [{"metric": "typed_years", "actual": 1.0, "expected": 1.0,
                        "absolute_tolerance": 0.0, "pass": True}]}


def _annual_report(oracle_report: dict, *, policy: str, invariants_status: str = "passed") -> dict:
    """A full-year report around a real ledger's oracle verdict (the annual path's inputs)."""

    invariants = {"checks": [{"id": "run.demand_input_reconciliation", "class": "cross_path",
                              "status": invariants_status}]}
    profile = REFERENCE_PROFILE_ID if policy == "declared_deviations" else "value-corrected"
    return build_scientific_validation_report(
        mode="full", periods_per_year=17_520, parity_report=_parity(),
        mechanism_checks=[MechanismCheck("ok", 1.0, 1.0, "MW")],
        retained_comparison_role=RETAINED_COMPARISON_INFORMATIONAL,
        run_invariants=invariants, energy_balance=oracle_report,
        gate_policy=policy, profile_id=profile,
        declared_deviations=declared_deviations.for_profile(profile),
    )


class ValidationGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="value-p04-gate-")
        root = Path(cls._tmp.name)

        def one(run):
            name, rule_set = run
            output = root / f"{name}-{rule_set}"
            p04_variants.run_variant(name, output, rule_set=rule_set)
            return run, output

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            cls.outputs = dict(pool.map(one, RUNS))
        cls.reports = {run: oracle.evaluate_run_ledger(output) for run, output in cls.outputs.items()}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _validation(self, run) -> dict:
        return json.loads((self.outputs[run] / "validation" / "scientific-validation.json").read_text(encoding="utf-8"))

    def _ledger_copy(self, run, name: str) -> Path:
        target = Path(self._tmp.name) / "copies" / name / "market.sqlite"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.outputs[run] / "market" / "market.sqlite", target)
        return target

    # --- production policy -------------------------------------------------

    def test_corrected_runs_pass_the_gates_and_book_the_shortfall(self):
        for name in ("baseline", "overshoot"):
            with self.subTest(name):
                validation = self._validation((name, "profile"))
                self.assertEqual(validation["validation_gate"]["policy"], "production")
                self.assertEqual(validation["validation_gate"]["status"], PASSED)
                self.assertEqual(validation["energy_balance_status"], PASSED)
                self.assertEqual(validation["storage_invariant_status"], PASSED)
                self.assertEqual(validation["raw_invariants"]["status"], PASSED)
                self.assertIsNone(validation["declared_deviations"])
        overshoot = self._validation(("overshoot", "profile"))
        # Decision A2: unmet demand is a stress event booked as unserved
        # energy, not an energy-balance failure; the raw boundary verdict
        # stays visible as evidence.
        self.assertEqual(overshoot["energy_balance"]["raw_boundary_status"], FAILED)
        self.assertEqual(overshoot["stress"]["shortfall_basis"], "exact")
        with closing(sqlite3.connect(self.outputs[("overshoot", "profile")] / "market" / "market.sqlite")) as db:
            booked = db.execute("SELECT SUM(shortfall_mwh) FROM balance_boundary_period").fetchone()[0]
        # The oracle's estimate on the declared full-node boundary equals the
        # kernel's booked unserved energy (it used to report a lower bound).
        self.assertAlmostEqual(overshoot["stress"]["shortfall_mwh"], booked, places=6)

    def test_production_gate_after_the_r41_kernel_corrections(self):
        # Before R4-1: energy balance failed (DEV-BAL-04 +3.000 MWh) and the
        # storage gate failed (P5-03); both defects are corrected (A26).
        balancing = _annual_report(self.reports[("nuclear_balancing", "doctoral")], policy="production")
        self.assertEqual(balancing["energy_balance_status"], PASSED)
        self.assertEqual(balancing["energy_balance"]["gate_failed_checks"], [])
        self.assertEqual(balancing["storage_invariant_status"], PASSED)
        self.assertEqual(balancing["scientific_validation_status"], PASSED)
        overshoot = _annual_report(self.reports[("overshoot", "doctoral")], policy="production")
        self.assertEqual(overshoot["energy_balance_status"], PASSED)  # A2: booked as unserved
        self.assertEqual(overshoot["storage_invariant_status"], PASSED)
        tampered = oracle.evaluate_ledger(self._tampered_balance())
        failed = _annual_report(tampered, policy="production")
        self.assertEqual(failed["energy_balance_status"], FAILED)
        self.assertIn("period.balance_account", failed["energy_balance"]["gate_failed_checks"])
        self.assertEqual(failed["scientific_validation_status"], FAILED)
        self.assertFalse(failed["annual_economics_eligible"])
        failed_invariants = _annual_report(self.reports[("baseline", "profile")], policy="production",
                                           invariants_status="failed")
        self.assertEqual(failed_invariants["scientific_validation_status"], FAILED)
        self.assertFalse(failed_invariants["annual_economics_eligible"])
        clean = _annual_report(self.reports[("baseline", "profile")], policy="production")
        self.assertEqual((clean["scientific_validation_status"], clean["annual_economics_eligible"]), (PASSED, True))

    # --- doctoral policy ---------------------------------------------------

    def test_doctoral_runs_are_conformant_after_r41(self):
        # Before R4-1 nuclear_balancing matched DEV-BAL-04 and the doctoral
        # baseline DEV-STO-01 (reproduction_with_declared_deviations, Q14
        # withheld); both are corrected and withdrawn (A26).
        balancing = _annual_report(self.reports[("nuclear_balancing", "doctoral")], policy="declared_deviations")
        self.assertEqual(balancing["energy_balance_status"], CONFORMANT)
        self.assertEqual(balancing["storage_invariant_status"], CONFORMANT)
        self.assertEqual(balancing["scientific_validation_status"], CONFORMANT)
        self.assertEqual(balancing["raw_invariants"]["status"], PASSED)  # Q14: published
        self.assertEqual(balancing["declared_deviations"]["matched"], [])
        baseline = _annual_report(self.reports[("baseline", "doctoral")], policy="declared_deviations")
        self.assertEqual(baseline["energy_balance_status"], CONFORMANT)
        self.assertEqual(baseline["storage_invariant_status"], CONFORMANT)
        self.assertEqual(baseline["scientific_validation_status"], CONFORMANT)
        overshoot = _annual_report(self.reports[("overshoot", "doctoral")], policy="declared_deviations")
        self.assertEqual(overshoot["energy_balance_status"], CONFORMANT)  # A2: stress, not a deviation
        self.assertEqual(overshoot["stress"]["stress_periods"], 48)
        self.assertEqual(overshoot["declared_deviations"]["evidence"]["DEV-BAL-02"]
                         ["forecast_above_supply_stress_periods"], 48)
        conformant = _annual_report(self.reports[("baseline", "profile")], policy="declared_deviations")
        self.assertEqual((conformant["energy_balance_status"], conformant["storage_invariant_status"]),
                         (CONFORMANT, CONFORMANT))
        self.assertEqual(conformant["scientific_validation_status"], CONFORMANT)
        self.assertEqual(conformant["raw_invariants"]["status"], PASSED)
        failed = _annual_report(self.reports[("nuclear_balancing", "doctoral")], policy="declared_deviations",
                                invariants_status="failed")
        self.assertEqual(failed["scientific_validation_status"], FAILED)  # run invariants are never declared

    def _tampered_balance(self) -> Path:
        """The doctoral nuclear_balancing ledger with 3 MWh of supply added in period 0."""

        ledger = self._ledger_copy(("nuclear_balancing", "doctoral"), "double-count")
        with closing(sqlite3.connect(ledger)) as db:
            db.execute("UPDATE period_summary SET accepted_supply_mwh = accepted_supply_mwh + 3.0 WHERE period = 0")
            db.commit()
        return ledger

    def test_undeclared_or_misshapen_failures_stay_failed(self):
        # No declared deviation explains a gate failure since R4-1 (A26),
        # under either catalogue reading.
        tampered = oracle.evaluate_ledger(self._tampered_balance())
        for declared in ([], declared_deviations.gating(declared_deviations.for_profile(REFERENCE_PROFILE_ID))):
            verdict = oracle.match_declared_deviations(tampered, declared)
            self.assertEqual(verdict["energy_balance_status"], FAILED)
            self.assertIn("period.balance_account", verdict["unexplained_checks"])
            self.assertEqual(verdict["matched"], [])
        # A store above its rated power (the former P5-03 shape) fails.
        ledger = self._ledger_copy(("baseline", "doctoral"), "over-reset")
        with closing(sqlite3.connect(ledger)) as db:
            db.execute(
                "UPDATE storage_energy_audit SET charge_input_mwh = 3.5 * ("
                "SELECT s.power_capacity_mw * 0.5 FROM storage_state s WHERE s.year=storage_energy_audit.year "
                "AND s.period=storage_energy_audit.period AND s.asset_id=storage_energy_audit.asset_id) "
                "WHERE period = 30"
            )
            db.commit()
        tampered = oracle.evaluate_ledger(ledger)
        rated = next(row for row in tampered["storage"]["checks"] if row["id"] == "storage.rated_power")
        self.assertEqual(rated["status"], FAILED)
        self.assertGreater(rated["unexplained"], 0)
        verdict = oracle.match_declared_deviations(
            tampered, declared_deviations.gating(declared_deviations.for_profile(REFERENCE_PROFILE_ID)))
        self.assertEqual(verdict["storage_invariant_status"], FAILED)
        # State-of-charge bounds are never declared.
        ledger = self._ledger_copy(("baseline", "doctoral"), "soc")
        with closing(sqlite3.connect(ledger)) as db:
            db.execute("UPDATE storage_state SET state_of_charge_mwh = energy_capacity_mwh + 1 WHERE period = 5")
            db.commit()
        tampered = oracle.evaluate_ledger(ledger)
        verdict = oracle.match_declared_deviations(
            tampered, declared_deviations.gating(declared_deviations.for_profile(REFERENCE_PROFILE_ID)))
        self.assertEqual(verdict["storage_invariant_status"], FAILED)
        self.assertIn("storage.soc_bounds", verdict["unexplained_checks"])

    def test_q14_publication_follows_the_doctoral_verdict(self):
        doctoral = resolve_methodology(REFERENCE_PROFILE_ID).to_dict()
        # R4-1 (A26): the doctoral nuclear_balancing day now publishes (it was
        # withheld for DEV-BAL-04); a tampered balance is withheld.
        cases = (
            ("nuclear_balancing-doctoral", self.reports[("nuclear_balancing", "doctoral")], "published", PASSED),
            ("baseline-doctoral", self.reports[("baseline", "doctoral")], "published", PASSED),
            ("baseline-profile", self.reports[("baseline", "profile")], "published", PASSED),
            ("tampered", oracle.evaluate_ledger(self._tampered_balance()), "withheld", FAILED),
        )
        for name, report, status, verdict in cases:
            with self.subTest(run=name):
                root = Path(self._tmp.name) / "q14" / name
                path = root / "model-output" / "validation" / "scientific-validation.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(_annual_report(report, policy="declared_deviations")),
                                encoding="utf-8")
                publication = result_publication({"methodology": doctoral, "status": "completed"}, root)
                self.assertEqual((publication["status"], publication["raw_invariants_status"]), (status, verdict))

    # --- evidence consistency ----------------------------------------------

    def test_bundle_validator_recomputes_gate_and_raw_invariants(self):
        output = self.outputs[("overshoot", "doctoral")]
        artifacts = {name: {} for name in (
            "validation/scientific-validation.json", "parity/stage-parity.json",
            "validation/run-invariants.json", "validation/energy-balance-oracle.json")}
        self.assertEqual(_validation_evidence_errors(output, artifacts), [])
        copy = Path(self._tmp.name) / "bundle-copy"
        shutil.copytree(output, copy)
        path = copy / "validation" / "scientific-validation.json"
        # R4-1 (A26): the doctoral overshoot day passes both gates, so each
        # copied field is set to a verdict the evidence does not support.
        for field, value in (("raw_invariants", {"status": "failed"}), ("storage_invariant_status", FAILED),
                             ("validation_gate", {"policy": "declared_deviations",
                                                  "profile_id": REFERENCE_PROFILE_ID, "status": DECLARED})):
            with self.subTest(field=field):
                report = json.loads((output / "validation" / "scientific-validation.json").read_text(encoding="utf-8"))
                report[field] = value
                path.write_text(json.dumps(report), encoding="utf-8")
                errors = _validation_evidence_errors(copy, artifacts)
                self.assertTrue(errors)
                self.assertEqual({row["code"] for row in errors}, {"GF_BUNDLE_VALIDATION_STATUS_MISMATCH"})

    def test_replay_windows_sum_to_the_run_level_stress(self):
        for run in (("overshoot", "profile"), ("overshoot", "doctoral")):
            with self.subTest(run=run):
                output = self.outputs[run]
                database = output / "market" / "market.sqlite"
                with closing(sqlite3.connect(database)) as db:
                    year = db.execute("SELECT MIN(year) FROM period_summary").fetchone()[0]
                timeline = query_dispatch_timeline(database, year=year, resolution="half_hour", limit=500)
                validation = self._validation(run)
                self.assertEqual({item["shortfall_basis"] for item in timeline["items"]}, {"exact"})
                self.assertAlmostEqual(sum(item["shortfall_mwh"] for item in timeline["items"]),
                                       validation["stress"]["shortfall_mwh"], places=6)
                self.assertEqual(sum(item["stress_periods"] for item in timeline["items"]),
                                 validation["stress"]["stress_periods"])


class DeclaredDeviationCatalogueTests(unittest.TestCase):
    def test_profiles_declare_their_deviations(self):
        doctoral = {row["id"]: row for row in declared_deviations.for_profile(REFERENCE_PROFILE_ID)}
        # R4-1 (A26): DEV-BAL-04 and DEV-STO-01 were corrected and withdrawn.
        self.assertEqual(set(doctoral), {"DEV-BAL-01", "DEV-BAL-02", "DEV-BAL-03"})
        self.assertEqual(declared_deviations.gating(list(doctoral.values())), [])
        self.assertEqual({row["id"]: row["withdrawn_by"] for row in declared_deviations.withdrawn()},
                         {"DEV-BAL-04": ["r41.must-run-surplus-counted-once"],
                          "DEV-STO-01": ["p06.storage-net-per-period"]})
        corrected = declared_deviations.for_profile("value-corrected")
        self.assertEqual(declared_deviations.gating(corrected), [])  # A2 evidence only
        self.assertEqual(declared_deviations.gate_policy(resolve_methodology(REFERENCE_PROFILE_ID).to_dict()),
                         "declared_deviations")
        self.assertEqual(declared_deviations.gate_policy(resolve_methodology().to_dict()), "production")
        self.assertEqual(declared_deviations.gate_policy(None), "production")

    def test_loader_rejects_malformed_entries(self):
        base = json.loads(declared_deviations.CATALOGUE_PATH.read_text(encoding="utf-8"))
        broken = [
            lambda rows: rows[1].update(gate_effect="maybe"),
            lambda rows: rows[1]["signature"].update(matcher="unknown"),
            # R4-1 (A26): the withdrawn gate matchers are unknown.
            lambda rows: rows[1]["signature"].update(matcher="stage_power_reset"),
            lambda rows: rows[1].update(gate_effect="explains_gate_failure"),
            lambda rows: rows[1]["signature"].update(checks=["period.balance_account"]),
            lambda rows: rows[0].update(profiles=[]),
            lambda rows: rows.append(dict(rows[0])),
        ]
        with tempfile.TemporaryDirectory() as folder:
            for index, edit in enumerate(broken):
                with self.subTest(index=index):
                    payload = json.loads(json.dumps(base))
                    edit(payload["deviations"])
                    path = Path(folder) / f"c{index}.json"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(declared_deviations.DeclaredDeviationCatalogError):
                        declared_deviations.load_from(path)

    def test_not_evaluated_evidence_is_never_conformant(self):
        verdict = oracle.match_declared_deviations(None, [])
        self.assertEqual((verdict["energy_balance_status"], verdict["storage_invariant_status"]),
                         (NOT_EVALUATED, NOT_EVALUATED))


if __name__ == "__main__":
    unittest.main()
