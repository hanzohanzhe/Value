"""Legacy identifiers stay readable; acknowledgement keys follow the registry (X0 S7)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import server
from gridform_core.frontend_contract import (
    EXPERIMENTAL_ACK,
    builtin_maturity_acknowledgement_key,
    maturity_acknowledgement_key,
    maturity_acknowledgement_requirements,
)
from gridform_core.legacy_module_ids import (
    CURRENT_ORCHESTRATOR_ENGINE,
    LEGACY_MODULE_IDS,
    ORCHESTRATOR_ENGINES,
    normalize_engine,
    normalize_module_id,
)
from gridform_core.v2.module_manifest import builtin_registry
from gridform_core.value_101 import value_101_study
from gridform_core.value_101_lifecycle import build_value_101_network_pair
from gridform_core.value_uk import value_uk_study_templates


class LegacyEngineVisibilityTests(unittest.TestCase):
    def test_runs_with_the_pre_rename_engine_label_are_listed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            runs = Path(folder)
            for run_id, engine in (
                ("current", "value-annual-orchestrator/v2"),
                ("upgraded", "gridform-annual-orchestrator/v2"),
                ("reference", "scheme-c-authoritative-exact/v1"),
            ):
                (runs / run_id).mkdir()
                (runs / run_id / "status.json").write_text(json.dumps({
                    "id": run_id, "project_id": "p", "status": "completed",
                    "execution_engine": engine, "updated_at": "2026-10-04T00:00:00+01:00",
                }), encoding="utf-8")
            with patch.object(server, "RUNS_ROOT", runs):
                visible = sorted(run["id"] for run in server.list_runs())
        self.assertEqual(visible, ["current", "upgraded"])

    def test_normalisation_maps_old_names_and_keeps_unknown_ones(self) -> None:
        self.assertEqual(normalize_engine("gridform-annual-orchestrator/v2"), CURRENT_ORCHESTRATOR_ENGINE)
        self.assertIn("gridform-annual-orchestrator/v2", ORCHESTRATOR_ENGINES)
        self.assertEqual(normalize_module_id("force-staged-bid-at-cost-psm"), "value-staged-bid-at-cost-psm")
        self.assertEqual(normalize_module_id("value-bid-at-cost-psm"), "value-bid-at-cost-psm")
        registry = builtin_registry()
        for old, new in LEGACY_MODULE_IDS.items():
            with self.subTest(old=old):
                self.assertNotIn(old, registry.manifests())
                known = set(registry.manifests()) | set(registry.extension_manifests())
                self.assertIn(new, known)


class AcknowledgementKeyTests(unittest.TestCase):
    def test_key_format_and_registry_versions(self) -> None:
        self.assertEqual(maturity_acknowledgement_key("module", "m", "1.2.3"), "module:m@1.2.3")
        with self.assertRaises(ValueError):
            maturity_acknowledgement_key("solver", "m", "1")
        registry = builtin_registry()
        zonal = registry.manifest("value-zonal-redispatch-balancing")
        self.assertEqual(
            builtin_maturity_acknowledgement_key("module", "value-zonal-redispatch-balancing"),
            f"module:value-zonal-redispatch-balancing@{zonal.version}",
        )

    def _assert_template_satisfies_requirements(self, study: dict) -> None:
        registry = builtin_registry()
        required = maturity_acknowledgement_requirements(
            registry, dict(study["modules"]), list(study.get("selected_extensions") or [])
        )
        self.assertTrue(required)
        acknowledged = dict(study["maturity_acknowledgements"])
        self.assertEqual({row["key"] for row in required}, {key for key in acknowledged if not key.startswith("solver-contract:")})
        self.assertTrue(all(acknowledged[row["key"]] == EXPERIMENTAL_ACK for row in required))

    def test_value_101_network_lesson_keys_match_the_registry(self) -> None:
        pair, _ = build_value_101_network_pair(value_101_study(), network_pack_id="value-101-network-v1")
        for variant in ("copperplate", "constrained"):
            with self.subTest(variant=variant):
                self._assert_template_satisfies_requirements(pair[variant])

    def test_value_uk_template_keys_match_the_registry(self) -> None:
        templates = value_uk_study_templates("value-uk-base", "value-uk-network")
        self._assert_template_satisfies_requirements(templates[1])

    def test_registry_version_bump_moves_the_template_key(self) -> None:
        registry = builtin_registry()
        manifest = registry.manifest("value-zonal-redispatch-balancing")
        bumped = type(manifest).from_dict({**manifest.to_dict(), "version": "9.9.9"}) if hasattr(manifest, "to_dict") else None
        if bumped is None:
            self.skipTest("manifest has no to_dict")
        with patch.object(type(registry), "manifest", lambda self, module_id, **_: bumped if module_id == manifest.id else registry._manifests[module_id]):
            key = builtin_maturity_acknowledgement_key("module", manifest.id, registry)
        self.assertEqual(key, f"module:{manifest.id}@9.9.9")


if __name__ == "__main__":
    unittest.main()
