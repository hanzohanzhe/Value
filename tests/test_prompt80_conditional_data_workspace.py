from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.data_contract_templates import (
    preview_binding,
    runtime_supported_formats,
    template_for_role,
)
from gridform_core.network_ac import ACGeneratorSpec
from gridform_core.network_contracts import AssetBusMapping, NetworkBranch, NetworkBus
from gridform_core.network_expansion import NetworkCandidate


class Prompt80ConditionalDataWorkspaceTests(unittest.TestCase):
    def test_generated_network_and_ac_templates_match_runtime_dataclasses(self):
        cases = (
            ("value.network.buses", "buses", NetworkBus),
            ("value.network.branches", "branches", NetworkBranch),
            ("value.network.asset-map", "asset_mappings", AssetBusMapping),
            ("value.network.ac.generators", "generator_specs", ACGeneratorSpec),
            ("value.network.expansion.candidates", "candidates", NetworkCandidate),
        )
        for role, key, contract in cases:
            raw, media, filename = template_for_role(role, ("json",))
            payload = json.loads(raw.decode("utf-8"))
            self.assertIn("application/json", media)
            self.assertTrue(filename.endswith(".json"))
            self.assertEqual(contract.from_dict(payload[key][0]).to_dict()["schema_version"], contract.from_dict(payload[key][0]).schema_version)

    def test_hydrology_template_uses_canonical_timestamp_and_explicit_clock(self):
        raw, _media, _filename = template_for_role(
            "value.hydrology.run-of-river-inflow", ("csv",)
        )
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(
            set(rows[0]),
            {"timestamp", "site_id", "value", "unit", "interval_hours", "timezone"},
        )
        self.assertIn("+00:00", rows[0]["timestamp"])

    def test_manifest_formats_are_distinguished_from_shipped_parsers(self):
        self.assertEqual(
            runtime_supported_formats("value.network.buses", ("csv", "json")),
            ("json",),
        )
        self.assertEqual(
            runtime_supported_formats("value.network.nodal-demand", ("csv", "parquet")),
            ("csv",),
        )

    def test_preview_is_bounded_and_reports_duplicate_sample_identities(self):
        with tempfile.TemporaryDirectory(prefix="value-p80-") as temporary:
            root = Path(temporary)
            path = root / "nodal.csv"
            path.write_text(
                "period_id,bus_id,demand_mwh\n2025:0,A,1\n2025:0,A,2\n2025:1,A,3\n",
                encoding="utf-8",
            )
            import hashlib
            binding = {
                "uri": "nodal.csv", "filename": "nodal.csv", "format": "csv",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            result = preview_binding(
                root,
                {"bindings": {"value.network.nodal-demand": binding}},
                {
                    "role": "value.network.nodal-demand", "label": "Nodal demand",
                    "formats": ["csv"], "unit": "MWh/period",
                    "capability": "data.network.topology/v1",
                },
                sample_rows=2,
            )
            self.assertEqual(result["sampled_rows"], 2)
            self.assertEqual(result["duplicate_sample_identities"], 1)
            self.assertEqual(len(result["sample"]), 2)


if __name__ == "__main__":
    unittest.main()
