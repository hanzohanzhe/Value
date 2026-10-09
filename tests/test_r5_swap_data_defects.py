"""R5 (DECISIONS A28): the swap-data defects of the final four-role report (build c204aac).

Each test names the defect it covers: S-F-高1 (the VALUE 101 demand files
are labelled MWh/period but read as MW), S-F-中2 (the cost per MWh served
counted the stress shortfall as served), S-F-中3 (hourly demand import), and
the low items S-F-低2 (clock_adapter label) and S-F-低4 (period wording).
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from backend.data_mapping import DataMappingService
from backend.data_pack_clone import clone_data_pack, manifest_sha256
from gridform_core.catalog import DATASET_SLOTS
from gridform_core.cost_ledger import a2_hidden_unserved_mwh, build_cem_cost_ledger
from gridform_core.data_pack_validation import (
    LEGACY_DEMAND_MW_SHA256,
    demand_scale_warning,
    legacy_demand_unit,
    validate_data_pack,
)
from gridform_core.methodology import UNIVERSAL_ACCOUNTING_CORRECTIONS, load_catalogue
from gridform_core.series_reader import period_span_text
from gridform_core.v2.contracts import MarketYearResult

ROOT = Path(__file__).resolve().parents[1]
VALUE_101 = ROOT / "data-packs" / "value-101-baseline-v1"
CORRECTION_ID = "r5.served-energy-net-of-stress-shortfall"


def _market(**overrides: object) -> MarketYearResult:
    values: dict[str, object] = dict(
        result_id="test:2025", year=2025, module_id="test-psm", module_version="1.0.0",
        generation_mwh_by_asset={"thermal": 900.0}, market_income_gbp_by_agent={},
        total_system_cost_gbp=0.0, total_operational_cost_gbp=40_000.0,
        total_levelized_capital_cost_gbp=60_000.0, total_demand_mwh=1_000.0,
        total_generation_mwh=900.0, total_blackout_mwh=10.0, total_excess_mwh=0.0,
    )
    values.update(overrides)
    return MarketYearResult(**values)  # type: ignore[arg-type]


def _balance(year: int, hidden: float, recorded: float = 10.0, stress_periods: int = 3) -> dict[str, object]:
    return {"market_ledger": {"energy_balance": {"by_year": [
        {"year": year - 1, "hidden_unserved_mwh": 999.0, "recorded_unserved_mwh": 0.0},
        {"year": year, "hidden_unserved_mwh": hidden, "recorded_unserved_mwh": recorded,
         "shortfall_mwh": hidden + recorded, "stress_periods": stress_periods},
    ]}}}


class ServedEnergyTests(unittest.TestCase):
    """S-F-中2: served = demand - recorded blackout - A2 stress shortfall (accounting only)."""

    def test_cost_per_mwh_served_divides_by_energy_actually_served(self) -> None:
        # Hand computation: demand 1,000; recorded blackout 10; A2 hidden
        # unserved 90 -> served 900; cost 100,000 -> 111.11 GBP/MWh (was 101.01).
        ledger = build_cem_cost_ledger(_market(extensions=_balance(2025, 90.0)))
        self.assertEqual(ledger.demand_served_mwh, 900.0)
        self.assertAlmostEqual(ledger.cem_system_cost_gbp_per_mwh_served, 100_000.0 / 900.0)
        # The other year's row is not used.
        self.assertEqual(a2_hidden_unserved_mwh(_market(extensions=_balance(2025, 90.0))), 90.0)

    def test_without_the_a2_account_the_old_denominator_stays(self) -> None:
        for extensions in ({}, {"market_ledger": {}}, {"market_ledger": {"energy_balance": {"by_year": []}}},
                           {"market_ledger": None}):
            with self.subTest(extensions=extensions):
                ledger = build_cem_cost_ledger(_market(extensions=extensions))
                self.assertEqual(ledger.demand_served_mwh, 990.0)
                self.assertAlmostEqual(ledger.cem_system_cost_gbp_per_mwh_served, 100_000.0 / 990.0)

    def test_numerical_noise_does_not_move_the_denominator(self) -> None:
        # GBP1 corrected (golden C9) books ~2e-8 MWh of hidden unserved energy in a
        # year without a stress period: noise, not unserved energy.
        demand = 232_910_596.5
        ledger = build_cem_cost_ledger(_market(total_demand_mwh=demand, total_blackout_mwh=0.0,
                                               extensions=_balance(2025, 1.97e-8, 0.0, stress_periods=0)))
        self.assertEqual(ledger.demand_served_mwh, demand)

    def test_correction_is_a_universal_accounting_correction_outside_the_method_identity(self) -> None:
        ids = [item[0] for item in UNIVERSAL_ACCOUNTING_CORRECTIONS]
        self.assertIn(CORRECTION_ID, ids)
        self.assertNotIn(CORRECTION_ID, load_catalogue().corrections)


class LegacyDemandUnitTests(unittest.TestCase):
    """S-F-高1: registry relabel - the VALUE 101 demand bytes are read as MW and every page says so."""

    def test_value_101_demand_bindings_are_relabelled_without_changing_bytes(self) -> None:
        manifest = json.loads((VALUE_101 / "manifest.json").read_text(encoding="utf-8"))
        for role in ("demand.real", "demand.forecast"):
            binding = manifest["bindings"][role]
            self.assertEqual(binding["unit"], "MWh/period")
            self.assertIn(binding["sha256"], LEGACY_DEMAND_MW_SHA256[role])
            relabel = legacy_demand_unit(role, binding)
            self.assertEqual(relabel["runtime_unit"], "MW")
            self.assertIn("header says mwh", relabel["note"])
            self.assertEqual(hashlib.sha256((VALUE_101 / binding["uri"]).read_bytes()).hexdigest(), binding["sha256"])

    def test_other_bindings_are_not_relabelled(self) -> None:
        binding = {"unit": "MWh/period", "sha256": "0" * 64}
        self.assertIsNone(legacy_demand_unit("demand.real", binding))
        manifest = json.loads((VALUE_101 / "manifest.json").read_text(encoding="utf-8"))
        legacy = manifest["bindings"]["demand.real"]
        self.assertIsNone(legacy_demand_unit("demand.real", {**legacy, "unit": "MW"}))
        self.assertIsNone(legacy_demand_unit("demand.real", {**legacy, "input_unit_contract": "value.demand-mw-half-hour/v1"}))
        self.assertIsNone(legacy_demand_unit("market.france.price", legacy))

    def test_scale_warning_names_both_annual_energies(self) -> None:
        self.assertIsNone(demand_scale_warning("demand.real", 268_950.0, 233_870.0, "the old file"))
        self.assertIsNone(demand_scale_warning("demand.real", 160_000.0, 233_870.0, "the old file"))
        warning = demand_scale_warning("demand.real", 539_540.0, 233_870.0, "the old file")
        self.assertIn("GF_DATA_DEMAND_SCALE", warning)
        self.assertIn("539,540 MWh per model year", warning)
        self.assertIn("2.31 times the old file (about 233,870 MWh per year)", warning)
        self.assertIn("0.50 times", demand_scale_warning("demand.real", 116_935.0, 233_870.0, "x"))


def _stamps(count: int, *, start: str, step_minutes: int) -> list[str]:
    first = dt.datetime.fromisoformat(start)
    return [(first + dt.timedelta(minutes=step_minutes * index)).strftime("%Y-%m-%dT%H:%M:%SZ") for index in range(count)]


class _Value101Copy:
    """An independent copy of the VALUE 101 baseline pack and a mapping service."""

    def setUp(self) -> None:  # noqa: D401 - unittest hook
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)  # type: ignore[attr-defined]
        self.root = Path(self.temp.name)
        self.packs = self.root / "packs"
        shutil.copytree(VALUE_101, self.packs / "value-101-baseline-v1")
        source = self.packs / "value-101-baseline-v1" / "manifest.json"
        copied = clone_data_pack("value-101-baseline-v1", {
            "schema_version": "value.data-pack-clone-request/v1", "name": "my swap",
            "source_manifest_sha256": manifest_sha256(source)},
            packs_root=self.packs, minimum_free_space_bytes=0)["data_pack"]
        self.pack_id = copied["id"]
        self.pack = self.packs / self.pack_id
        self.service = DataMappingService(packs_root=self.packs, staging_root=self.root / "staging",
            projects_root=self.root / "projects", trash_root=self.root / "trash",
            dataset_slots=DATASET_SLOTS, lifecycle_lock=threading.RLock())

    def review(self, raw: bytes, *, unit: str = "MW", role: str = "demand.real", target: str = "MW",
               **extra: object) -> dict:
        stage = self.service.stage(self.pack_id, role, raw, "demand.csv", manifest_sha256(self.pack / "manifest.json"))
        return self.service.preview(stage["stage_id"], {
            "schema_version": "value.data-mapping-preview-request/v1",
            "source_sha256": stage["source_sha256"], "target_manifest_sha256": stage["target_manifest_sha256"],
            "columns": [{"source": "load", "target": "value", "source_unit": unit, "target_unit": target}], **extra})

    def commit(self, review: dict, **extra: object) -> dict:
        return self.service.commit(review["review_id"], {
            "schema_version": "value.data-mapping-commit-request/v1",
            **{key: review[key] for key in ("source_sha256", "spec_sha256", "normalized_sha256", "target_manifest_sha256")},
            **extra})

    def baseline_values(self) -> list[float]:
        rows = (VALUE_101 / "files" / "demand__real" / "real.csv").read_text(encoding="utf-8").splitlines()[1:]
        return [float(row) for row in rows]


class DemandScaleMappingTests(_Value101Copy, unittest.TestCase):
    """S-F-高1: a replacement demand series far from the file it replaces is flagged with both energies."""

    def test_the_swap_data_unit_slip_is_flagged(self) -> None:
        values = self.baseline_values()
        # The tester's path: baseline value x 1.15 read as MWh/period, converted x 2.
        slip = "load\n" + "".join(f"{value * 1.15:.6f}\n" for value in values)
        review = self.review(slip.encode(), unit="MWh/period")
        self.assertTrue(review["valid"], review["errors"])
        warning = next(item for item in review["warnings"] if item.startswith("GF_DATA_DEMAND_SCALE"))
        self.assertIn("2.30 times the file it replaces in this pack", warning)
        self.assertIn("read as MW although its header says mwh", warning)
        baseline_mwh = sum(values) / len(values) * 8760.0
        self.assertIn(f"about {baseline_mwh:,.0f} MWh per year", warning)
        # The right reading (MW, x 1.15) passes without the warning.
        right = self.review(slip.encode(), unit="MW")
        self.assertFalse(any(item.startswith("GF_DATA_DEMAND_SCALE") for item in right["warnings"]))

    def test_pack_validation_compares_a_copy_with_its_origin(self) -> None:
        values = self.baseline_values()
        slip = "load\n" + "".join(f"{value * 2.3:.6f}\n" for value in values)
        self.commit(self.review(slip.encode()))
        manifest = json.loads((self.pack / "manifest.json").read_text(encoding="utf-8"))
        slots = [slot for slot in DATASET_SLOTS if slot["role"] == "demand.real"]
        report = validate_data_pack(self.pack, manifest, slots, layers=False)
        warnings = report["bindings"][0]["warnings"]
        self.assertTrue(any("GF_DATA_DEMAND_SCALE" in item and "value-101-baseline-v1" in item for item in warnings), warnings)
        # The untouched forecast role equals the origin's bytes: no comparison note.
        slots = [slot for slot in DATASET_SLOTS if slot["role"] == "demand.forecast"]
        report = validate_data_pack(self.pack, manifest, slots, layers=False)
        self.assertFalse(any("GF_DATA_DEMAND_SCALE" in item for item in report["bindings"][0]["warnings"]))


class HourlyDemandTests(_Value101Copy, unittest.TestCase):
    """S-F-中3: hourly demand is accepted like hourly prices: each hour is used for two half-hours."""

    def test_hourly_year_without_timestamps_is_expanded(self) -> None:
        raw = "load\n" + "".join(f"{20 + (hour % 24)}\n" for hour in range(8760))
        review = self.review(raw.encode())
        self.assertTrue(review["valid"], review["errors"])
        self.assertEqual(review["interval_minutes"], 60)
        self.assertEqual(review["source_interval_minutes"], 60)
        text = " ".join(review["warnings"])
        self.assertIn("GF_MAPPING_HOURLY_DEMAND", text)
        self.assertIn("17,520 half-hour periods", text)
        self.assertNotIn("at least 17520", text)
        self.assertEqual(review["acknowledgements_required"], [])
        binding = self.commit(review)["binding"]
        self.assertEqual(binding["interval_minutes"], 30)
        self.assertEqual(binding["source_interval_minutes"], 60)
        rows = list(csv.DictReader(io.StringIO((self.pack / binding["uri"]).read_text(encoding="utf-8"))))
        self.assertEqual(len(rows), 17_520)
        self.assertEqual([float(row["value"]) for row in rows[:4]], [20.0, 20.0, 21.0, 21.0])

    def test_hourly_mwh_per_period_is_energy_per_hour(self) -> None:
        raw = "load\n" + "60\n" * 8760
        review = self.review(raw.encode(), unit="MWh/period")
        self.assertTrue(review["valid"], review["errors"])
        # 60 MWh in one hour is 60 MW (not 120 MW as for a half-hour period).
        self.assertEqual(float(review["sample_rows"][0]["value"]), 60.0)
        self.assertIn("converted to MW with a 60-minute period", " ".join(review["warnings"]))

    def test_hourly_leap_year_with_timestamps_reports_no_gaps(self) -> None:
        stamps = _stamps(8784, start="2024-01-01T00:00:00", step_minutes=60)
        raw = "time,load\n" + "".join(f"{stamp},63.6\n" for stamp in stamps)
        review = self.review(raw.encode(), timestamp={"column": "time", "time_zone": "UTC"}, model_start_year=2025)
        self.assertTrue(review["valid"], review["errors"])
        self.assertEqual(review["timestamp"]["problem_count"], 0)
        self.assertEqual(review["timestamp"]["interval_minutes"], 60)
        text = " ".join(review["warnings"])
        self.assertNotIn("GF_DATA_TIMESTAMP_COVERAGE", text)
        self.assertNotIn("repeating the series", text)
        self.assertNotIn("gap of 60 minutes", " ".join(review["errors"]))
        self.assertTrue(review["clock"]["leap_day_removed"])
        binding = self.commit(review)["binding"]
        self.assertEqual(binding["timestamp_check"]["interval_minutes"], 60)
        # The chronology layer re-checks the retained hourly source at its own period.
        manifest = json.loads((self.pack / "manifest.json").read_text(encoding="utf-8"))
        report = validate_data_pack(self.pack, manifest, DATASET_SLOTS, layers=True)
        findings = json.dumps(report["layers"].get("chronology"))
        self.assertNotIn("GF_DATA_TIMESTAMPS", findings)

    def test_half_hourly_demand_is_unchanged(self) -> None:
        raw = "load\n" + "60\n" * 17_520
        review = self.review(raw.encode(), unit="MWh/period")
        self.assertTrue(review["valid"], review["errors"])
        self.assertEqual(review["interval_minutes"], 30)
        self.assertIsNone(review["source_interval_minutes"])
        self.assertEqual(float(review["sample_rows"][0]["value"]), 120.0)
        self.assertNotIn("repeat_rows", json.loads((self.root / "staging" / "reviews" / review["review_id"] / "spec.json").read_text()))

    def test_prices_are_never_expanded_by_the_mapping(self) -> None:
        raw = "load\n" + "70\n" * 8760
        review = self.review(raw.encode(), unit="GBP/MWh", role="market.france.price", target="GBP/MWh")
        self.assertTrue(review["valid"], review["errors"])
        self.assertIsNone(review["source_interval_minutes"])
        self.assertIn("each hour is used for two half-hour periods", " ".join(review["warnings"]))


class ClockWordingTests(unittest.TestCase):
    """S-F-低2 and S-F-低4."""

    def test_period_span_text(self) -> None:
        self.assertEqual(period_span_text(1), "1 period (30 minutes)")
        self.assertEqual(period_span_text(2), "2 periods (1 hour)")
        self.assertEqual(period_span_text(3), "3 periods (1.5 hours)")
        self.assertEqual(period_span_text(520), "520 periods (10.8 days)")

    def test_clock_adapter_says_what_the_reader_does(self) -> None:
        cases = {8760: "hourly_to_half_hour", 17_520: "as_is", 17_568: "leap_day_removed", 17_519: "repeated_from_start"}
        with tempfile.TemporaryDirectory() as folder:
            for rows, label in cases.items():
                for role in ("market.france.price", "demand.real"):
                    if role == "demand.real" and rows < 17_520:
                        continue
                    with self.subTest(role=role, rows=rows):
                        path = Path(folder) / f"{role}-{rows}.csv"
                        path.write_text("value\n" + "70\n" * rows)
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                        binding = {"uri": path.name, "format": "csv", "sha256": digest, "csv_header": True,
                                   "csv_column": "value", "unit": "MW" if role == "demand.real" else "GBP/MWh",
                                   **({"input_unit_contract": "value.demand-mw-half-hour/v1", "interval_minutes": 30}
                                      if role == "demand.real" else {})}
                        slots = [slot for slot in DATASET_SLOTS if slot["role"] == role]
                        report = validate_data_pack(Path(folder), {"bindings": {role: binding}}, slots, layers=False)
                        self.assertEqual(report["bindings"][0]["details"]["clock_adapter"], label)


if __name__ == "__main__":
    unittest.main()
