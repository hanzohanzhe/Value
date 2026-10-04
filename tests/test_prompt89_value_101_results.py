from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gridform_core.application import run_project_application
from gridform_core.bundle_validator import validate_run_bundle
from gridform_core.market_replay import (
    market_replay_capabilities,
    query_dispatch_timeline,
    query_vre_curtailment_summary,
)
from gridform_core.planning_index import query_index_projects
from gridform_core.value_101 import value_101_study


ROOT = Path(__file__).resolve().parents[1]
VALUE_101 = ROOT / "data-packs" / "value-101-baseline-v1"


class Value101ResultEvidenceTests(unittest.TestCase):
    def test_real_tutorial_bundle_exposes_all_guided_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="value-101-results-") as temporary:
            output = Path(temporary) / "model-output"
            console = io.StringIO()
            with redirect_stdout(console), redirect_stderr(console):
                run_project_application(
                    value_101_study(),
                    run_id="value-101-result-evidence",
                    pack_root=VALUE_101,
                    output_dir=output,
                    mode="tutorial",
                )
            validation = validate_run_bundle(output)
            market = output / "market" / "market.sqlite"
            planning = output / "planning" / "project-index.sqlite"
            capabilities = market_replay_capabilities(market)
            dispatch = query_dispatch_timeline(
                market, year=2025, resolution="half_hour", limit=48
            )
            vre = query_vre_curtailment_summary(market)
            commissioned = query_index_projects(planning, outcome="commissioned", limit=20)
            provenance = json.loads((output / "provenance.json").read_text("utf-8"))

        self.assertTrue(validation["valid"], validation)
        self.assertEqual(capabilities["years"], [2025, 2026])
        self.assertEqual(capabilities["trace_level"], "full")
        self.assertTrue(capabilities["auction_replay"])
        self.assertEqual(dispatch["total"], 48)
        self.assertGreater(sum(row["storage_charge_mwh"] for row in dispatch["items"]), 0)
        self.assertGreater(sum(row["storage_discharge_mwh"] for row in dispatch["items"]), 0)
        self.assertGreater(sum(row["curtailed_mwh"] for row in dispatch["items"]), 0)
        self.assertEqual([row["year"] for row in vre["years"]], [2025, 2026])
        self.assertGreater(vre["years"][0]["neutral_unused_vre_mwh"], 0)
        self.assertTrue(any(
            row["project_id"].startswith("value101-solar-planning")
            for row in commissioned["items"]
        ), commissioned)
        artifact_ids = {row["artifact_id"] for row in provenance["artifacts"]}
        self.assertIn("market/market.sqlite", artifact_ids)
        self.assertIn("planning/project-index.sqlite", artifact_ids)
        self.assertIn("ledgers/annual-cost-ledger.json", artifact_ids)
        self.assertIn("ledgers/annual-carbon-ledger.sqlite", artifact_ids)


if __name__ == "__main__":
    unittest.main()
