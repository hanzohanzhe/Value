"""Methodology profile catalogue, resolver and combination whitelist (X0 S8)."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gridform_core import methodology
from gridform_core.frontend_contract import resolve_study_draft
from gridform_core.parameters import REGISTRY, ParameterValidationError, resolve_scheme_c_parameters
from gridform_core.preflight import run_preflight
from gridform_core.v2.module_manifest import workspace_registry

ROOT = Path(__file__).resolve().parents[1]
DOCTORAL = methodology.REFERENCE_PROFILE_ID
CORRECTED = "value-corrected"

# Frozen-profile tripwire (plan X0 3.4).  The definition hash covers id,
# version, frozen, gated corrections, the whitelist and the reference preset.
# Changing any of them changes what "doctoral reproduction" means: update this
# constant only in a commit that says why (e.g. a package appending the new
# scientific_version of a lineage module that keeps the doctoral behaviour
# behind a gated correction).
DOCTORAL_DEFINITION_SHA256 = "a91a06e0fb2a8d8c6cd7c55c0f2b6a92fad5e83000b2bbcf51827427a395f287"

LINEAGE_MODULES = {
    "psm": "value-bid-at-cost-psm",
    "storage_cost": "value-legacy-storage-tariff",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "transition": "value-annual-state-transition",
}
GBP1_SHA = "17a68154c26680d472879fbe6a2f67eb3c610d5de68052b1b0101384a3270025"


def _pack(pack_id: str) -> dict:
    return json.loads((ROOT / "data-packs" / pack_id / "manifest.json").read_text(encoding="utf-8"))


class CatalogueCopy:
    """A temporary editable copy of the packaged catalogue."""

    def __init__(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name) / "methodology"
        shutil.copytree(methodology.CATALOGUE_ROOT, self.root)

    def edit(self, relative: str, mutate) -> None:
        path = self.root / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def load(self) -> methodology.Catalogue:
        return methodology.load_catalogue_from(self.root)

    def close(self) -> None:
        self.folder.cleanup()


def _gated(correction_id: str, fixture: object = {"test": "tests/test_x.py::T.test"}) -> dict:
    return {
        "id": correction_id, "package": "x0", "findings": ["P0-TEST"], "track": "profile_gated",
        "scope": "kernel", "affects": ["trajectory"], "applies_when": {}, "advisory": None,
        "trigger_fixture": fixture, "introduced_in": "test",
    }


class CatalogueSchemaTests(unittest.TestCase):
    def test_packaged_catalogue_has_two_profiles_and_one_default(self):
        catalogue = methodology.load_catalogue()
        self.assertEqual(list(catalogue.profiles), [CORRECTED, DOCTORAL])
        self.assertEqual(catalogue.default_profile_id, CORRECTED)
        doctoral = catalogue.profile(DOCTORAL)
        self.assertTrue(doctoral.frozen)
        self.assertEqual(doctoral.label, "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)")
        self.assertEqual(doctoral.note, "not an exact reproduction of the 2026-07-18 retained trajectory")
        self.assertEqual(doctoral.gated_corrections, ())
        self.assertEqual(doctoral.external_code_policy, "refuse_when_enabled")
        self.assertEqual(doctoral.result_publication["rule"], "raw_invariants_must_pass")
        self.assertEqual(doctoral.reference_configuration, {
            "modules": {"storage_cost": "value-legacy-storage-tariff"},
            "parameters": {"carbon.factor_scenario": "doctoral_reproduction_2026_07_18"},
        })
        self.assertEqual(catalogue.profile(CORRECTED).gated_corrections, "*")

    def test_frozen_profile_tripwire(self):
        self.assertEqual(methodology.resolve_methodology(DOCTORAL).profile_definition_sha256, DOCTORAL_DEFINITION_SHA256)

    def test_parameter_default_and_allowed_values_come_from_the_catalogue(self):
        definition = REGISTRY[methodology.PROFILE_PARAMETER]
        self.assertEqual(definition.default, methodology.default_profile_id())
        self.assertEqual(definition.allowed_values, methodology.profile_ids())
        self.assertEqual(definition.category, "scientific")
        resolved = resolve_scheme_c_parameters(ROOT / "data-packs" / "value-101-baseline-v1", {}, {}, periods_per_year=48)
        self.assertEqual(resolved.scientific.values[methodology.PROFILE_PARAMETER], CORRECTED)
        resolved = resolve_scheme_c_parameters(
            ROOT / "data-packs" / "value-101-baseline-v1", {methodology.PROFILE_PARAMETER: DOCTORAL}, {}, periods_per_year=48,
        )
        self.assertEqual(resolved.sources[methodology.PROFILE_PARAMETER]["source"], "project_override")
        with self.assertRaises(ParameterValidationError):
            resolve_scheme_c_parameters(
                ROOT / "data-packs" / "value-101-baseline-v1", {methodology.PROFILE_PARAMETER: "doctoral-reproduction"}, {}, periods_per_year=48,
            )

    def test_schema_violations_are_rejected(self):
        cases = {
            "two defaults": ("profiles.json", lambda p: p["profiles"][1].update(default=True)),
            "no default": ("profiles.json", lambda p: p["profiles"][0].update(default=False)),
            "frozen with every correction": ("profiles.json", lambda p: p["profiles"][1].update(gated_corrections="*")),
            "unknown gated id": ("profiles.json", lambda p: p["profiles"][1].update(gated_corrections=["x0.missing"])),
            "bad publication rule": ("profiles.json", lambda p: p["profiles"][1].update(result_publication={"rule": "always"})),
            "bad correction id": ("corrections/x0.json", lambda p: p["corrections"].append({**_gated("x0.ok"), "id": "X0_Bad"})),
            "foreign package id": ("corrections/x0.json", lambda p: p["corrections"].append({**_gated("p04.other"), "package": "x0"})),
            "gated without trigger fixture": ("corrections/x0.json", lambda p: p["corrections"].append(_gated("x0.no-fixture", fixture=None))),
            "duplicate id": ("corrections/x0.json", lambda p: p["corrections"].append(copy.deepcopy(p["corrections"][0]))),
            "unknown applies_when key": ("corrections/x0.json", lambda p: p["corrections"].append({**_gated("x0.when"), "applies_when": {"weather": ["x"]}})),
        }
        for name, (relative, mutate) in cases.items():
            with self.subTest(name):
                copy_ = CatalogueCopy()
                try:
                    copy_.edit(relative, mutate)
                    with self.assertRaises(methodology.MethodologyCatalogError):
                        copy_.load()
                finally:
                    copy_.close()

    def test_gated_corrections_follow_the_profile_and_universal_ones_apply_everywhere(self):
        copy_ = CatalogueCopy()
        try:
            copy_.edit("corrections/x0.json", lambda p: p["corrections"].append(_gated("x0.toy-gate")))
            catalogue = copy_.load()
            corrected = methodology.resolve_methodology(CORRECTED, catalogue=catalogue)
            doctoral = methodology.resolve_methodology(DOCTORAL, catalogue=catalogue)
            self.assertTrue(corrected.enabled("x0.toy-gate"))
            self.assertFalse(doctoral.enabled("x0.toy-gate"))
            self.assertTrue(doctoral.enabled("x0.methodology-identity"))
            self.assertNotEqual(corrected.applied_corrections_sha256, doctoral.applied_corrections_sha256)
            with self.assertRaises(methodology.UnknownCorrectionError):
                doctoral.enabled("x0.typo")
        finally:
            copy_.close()

    def test_identity_and_record(self):
        resolved = methodology.resolve_methodology(DOCTORAL)
        self.assertEqual(set(resolved.identity()), {
            "profile_id", "profile_version", "profile_definition_sha256", "applied_corrections_sha256",
        })
        record = resolved.to_dict()
        self.assertEqual(record["schema_version"], "value.methodology/v1")
        self.assertEqual(record["profile_id"], DOCTORAL)
        self.assertIn("x0.methodology-identity", record["applied_correction_ids"])
        with self.assertRaises(methodology.UnknownProfileError):
            methodology.resolve_methodology("doctoral-reproduction")
        self.assertEqual(methodology.resolve_methodology(None).profile_id, CORRECTED)


class PresetTests(unittest.TestCase):
    def test_with_profile_pins_and_preset_writes_the_reference_configuration(self):
        project = {"modules": {"psm": "value-bid-at-cost-psm"}, "parameters": {"scenario.id": "existing_decarb_base"}}
        pinned = methodology.with_profile(project, DOCTORAL)
        self.assertEqual(pinned["parameters"][methodology.PROFILE_PARAMETER], DOCTORAL)
        self.assertNotIn(methodology.PROFILE_PARAMETER, project["parameters"])
        preset = methodology.apply_reference_preset(project, DOCTORAL)
        self.assertEqual(preset["modules"]["storage_cost"], "value-legacy-storage-tariff")
        self.assertEqual(preset["parameters"]["carbon.factor_scenario"], "doctoral_reproduction_2026_07_18")
        self.assertEqual(preset["parameters"]["scenario.id"], "existing_decarb_base")
        with self.assertRaises(methodology.UnknownProfileError):
            methodology.with_profile(project, "nope")

    def test_reference_deviations_are_reported_not_refused(self):
        resolved = methodology.resolve_methodology(DOCTORAL)
        self.assertEqual(methodology.reference_deviations(
            resolved, modules=LINEAGE_MODULES,
            scientific_parameters={"carbon.factor_scenario": "doctoral_reproduction_2026_07_18"},
        ), [])
        rows = methodology.reference_deviations(
            resolved, modules=LINEAGE_MODULES,
            scientific_parameters={"carbon.factor_scenario": "value_current_authoritative_v1"},
        )
        self.assertEqual(rows, [{"kind": "parameter", "key": "carbon.factor_scenario",
                                 "reference": "doctoral_reproduction_2026_07_18",
                                 "actual": "value_current_authoritative_v1"}])
        self.assertEqual(methodology.reference_deviations(
            methodology.resolve_methodology(CORRECTED), modules={}, scientific_parameters={}), [])


class WhitelistTests(unittest.TestCase):
    registry = workspace_registry(Path("missing-modules-directory"))

    def _violations(self, profile, modules=LINEAGE_MODULES, extensions=(), packs=None, registry=None):
        return methodology.selection_combination_violations(
            profile, registry=registry or self.registry, modules=modules, extensions=extensions,
            data_packs=packs if packs is not None else [(_pack("value-101-baseline-v1"), None)],
        )

    def test_lineage_chain_on_a_thesis_era_pack_is_supported(self):
        self.assertEqual(self._violations(DOCTORAL), [])
        for pack_id in ("value-101-baseline-v1", "value-synthetic-contract-pack-v1"):
            self.assertEqual(self._violations(DOCTORAL, packs=[(_pack(pack_id), None)]), [], pack_id)

    def test_value_added_modules_and_extensions_are_refused_with_sub_reasons(self):
        dynamic = {**LINEAGE_MODULES, "storage_cost": "dynamic-annual-storage-cost"}
        rows = self._violations(DOCTORAL, modules=dynamic)
        self.assertEqual([row["sub_reason"] for row in rows], ["module"])
        self.assertEqual(rows[0]["module_id"], "dynamic-annual-storage-cost")
        staged = {**LINEAGE_MODULES, "psm": "value-staged-bid-at-cost-psm", "balancing": "value-zonal-redispatch-balancing"}
        self.assertEqual({row["module_id"] for row in self._violations(DOCTORAL, modules=staged)},
                         {"value-staged-bid-at-cost-psm", "value-zonal-redispatch-balancing"})
        rows = self._violations(DOCTORAL, extensions=["value-toy-audit-extension"])
        self.assertEqual([row["sub_reason"] for row in rows], ["extension"])
        self.assertEqual(self._violations(CORRECTED, modules=staged, extensions=["value-toy-audit-extension"]), [])

    def test_lineage_module_with_a_different_scientific_version_is_refused(self):
        ok, reason = methodology.module_supported(DOCTORAL, "value-bid-at-cost-psm", "some-later-method")
        self.assertFalse(ok)
        self.assertIn("frozen lineage version", reason)
        self.assertEqual(methodology.module_supported(CORRECTED, "anything", None), (True, None))

    def test_data_packs_by_id_class_and_manifest_sha(self):
        network = _pack("value-101-network-v1")
        rows = self._violations(DOCTORAL, packs=[(_pack("value-101-baseline-v1"), None), (network, None)])
        self.assertEqual([row["sub_reason"] for row in rows], ["data_pack"])
        gbp1 = {"id": "value-uk-open-data-pack-v1", "country": "GB"}
        self.assertEqual(methodology.classify_data_pack(gbp1), "scientific_reference")
        self.assertEqual(self._violations(DOCTORAL, packs=[(gbp1, b"other bytes")])[0]["sub_reason"], "data_pack")
        with patch("gridform_core.methodology.manifest_sha256_candidates", return_value={GBP1_SHA}):
            self.assertEqual(self._violations(DOCTORAL, packs=[(gbp1, b"x")]), [])
        r029 = {"id": "value-uk-calendar-vx-trade001", "country": "GB"}
        self.assertEqual(self._violations(DOCTORAL, packs=[(r029, None)])[0]["data_pack_id"], "value-uk-calendar-vx-trade001")
        user_copy = {"id": "release-r2-60-mwh-21be3dedd05d", "country": "SYNTHETIC", "teaching_only": True}
        self.assertEqual(methodology.classify_data_pack(user_copy), "teaching")
        self.assertEqual(self._violations(DOCTORAL, packs=[(user_copy, None)])[0]["sub_reason"], "data_pack")
        workspace = {"id": "my-pack", "country": "GB"}
        self.assertEqual(methodology.classify_data_pack(workspace), "user_workspace")
        self.assertEqual(self._violations(CORRECTED, packs=[(workspace, None), (r029, None)]), [])
        # A self-declared class is not trusted: a real GB pack cannot whitelist itself as synthetic.
        self.assertEqual(methodology.classify_data_pack({"id": "x", "pack_class": "synthetic"}), "user_workspace")
        claimed = {"id": "my-gb-copy", "country": "GB", "pack_class": "synthetic"}
        self.assertEqual(methodology.classify_data_pack(claimed), "user_workspace")
        self.assertEqual(self._violations(DOCTORAL, packs=[(claimed, None)])[0]["sub_reason"], "data_pack")
        synthetic = {"id": "contract-pack", "country": "SYNTHETIC"}
        self.assertEqual(methodology.classify_data_pack(synthetic), "synthetic")
        self.assertEqual(methodology.classify_data_pack(dict(synthetic, pack_class="synthetic")), "synthetic")
        self.assertEqual(self._violations(DOCTORAL, packs=[(synthetic, None)]), [])
        self.assertEqual(methodology.classify_data_pack(dict(user_copy, pack_class="synthetic")), "user_workspace")

    def test_value_101_baseline_is_pinned_by_manifest_sha(self):
        pack_root = ROOT / "data-packs" / "value-101-baseline-v1"
        manifest, raw = methodology.read_pack_manifest(pack_root)
        self.assertEqual(self._violations(DOCTORAL, packs=[(manifest, raw)]), [])
        # The same id with edited content (a rebuild in place) is not the frozen pack.
        edited = json.loads(raw.decode("utf-8"))
        edited["bindings"]["costs.capital"]["sha256"] = "0" * 64
        rows = self._violations(DOCTORAL, packs=[(edited, json.dumps(edited).encode("utf-8"))])
        self.assertEqual([row["sub_reason"] for row in rows], ["data_pack"])
        self.assertEqual(rows[0]["data_pack_id"], "value-101-baseline-v1")
        self.assertEqual(self._violations(CORRECTED, packs=[(edited, None)]), [])
        entries = {row["id"]: row for row in methodology.load_catalogue().profile(DOCTORAL).supported_data_packs}
        self.assertNotEqual(entries["value-101-baseline-v1"]["manifest_sha256"], "*")
        self.assertNotEqual(entries["value-uk-open-data-pack-v1"]["manifest_sha256"], "*")
        # The locally imported 1000 TWh pack cannot be pinned; the catalogue says why.
        self.assertEqual(entries["value-uk-1000twh-reproduction"]["manifest_sha256"], "*")
        self.assertIn("timestamps", entries["value-uk-1000twh-reproduction"]["pin_note"])

    def test_enabled_external_code_refuses_the_frozen_profile_only(self):
        with patch("gridform_core.methodology.external_code_entries", return_value=["module:my-storage-module"]):
            rows = self._violations(DOCTORAL)
            self.assertEqual([row["sub_reason"] for row in rows], ["external_code"])
            self.assertEqual(rows[0]["entries"], ["module:my-storage-module"])
            self.assertEqual(self._violations(CORRECTED), [])
        self.assertEqual(methodology.external_code_entries(self.registry), [])

    def test_combination_error_carries_one_code(self):
        with self.assertRaises(methodology.ProfileCombinationError) as caught:
            methodology.assert_combination(DOCTORAL, modules={"storage_cost": ("dynamic-annual-storage-cost", "x")})
        self.assertEqual(caught.exception.code, "VALUE_PROFILE_COMBINATION_UNSUPPORTED")
        self.assertEqual(caught.exception.to_dict()["sub_reasons"], ["module"])

    def test_methodology_errors_keep_their_codes_in_a_failed_run(self):
        """A worker failure records public_failure(error): each methodology error keeps its own code (plan 3.4)."""

        from gridform_core.errors import public_failure

        combination = methodology.ProfileCombinationError(DOCTORAL, [
            {"sub_reason": "data_pack", "message": "data pack x is not a thesis-era pack"},
            {"sub_reason": "external_code", "message": "module:y is enabled"},
        ])
        unknown = methodology.UnknownProfileError("Unknown methodology profile 'z'")
        mismatch = methodology.MethodologyMismatchError("a inside b")
        rows = {type(error).__name__: public_failure(error) for error in (combination, unknown, mismatch)}
        self.assertEqual({name: row.code for name, row in rows.items()}, {
            "ProfileCombinationError": "VALUE_PROFILE_COMBINATION_UNSUPPORTED",
            "UnknownProfileError": "VALUE_PROFILE_UNKNOWN",
            "MethodologyMismatchError": "VALUE_PROFILE_MISMATCH",
        })
        self.assertEqual({row.category for row in rows.values()}, {"methodology"})
        self.assertIn("Sub-reason: data_pack, external_code.", rows["ProfileCombinationError"].message)
        self.assertNotIn("thesis-era", rows["ProfileCombinationError"].message)
        # The classes stay ValueError/RuntimeError for existing handlers.
        self.assertIsInstance(combination, ValueError)
        self.assertIsInstance(unknown, ValueError)
        self.assertIsInstance(mismatch, RuntimeError)


class EntryPointTests(unittest.TestCase):
    """Study resolution and preflight run the same whitelist (C16)."""

    registry = workspace_registry(Path("missing-modules-directory"))

    def _project(self, profile, storage="value-legacy-storage-tariff"):
        return {
            "schema_version": "value.project/v1", "id": "p", "name": "P", "data_pack_id": "value-101-baseline-v1",
            "start_year": 2025, "end_year": 2026,
            "modules": {**LINEAGE_MODULES, "storage_cost": storage},
            "parameters": {methodology.PROFILE_PARAMETER: profile, "carbon.factor_scenario": "doctoral_reproduction_2026_07_18"},
            "runtime_options": {},
        }

    def test_study_draft_reports_profile_whitelist_and_option_flags(self):
        draft = resolve_study_draft(
            self._project(DOCTORAL, storage="dynamic-annual-storage-cost"), registry=self.registry,
            module_catalog=[], base_dataset_slots=[], data_packs=[(_pack("value-101-baseline-v1"), None)],
        )
        codes = {row["code"] for row in draft["errors"]}
        self.assertIn("VALUE_PROFILE_COMBINATION_UNSUPPORTED", codes)
        self.assertEqual(draft["methodology"]["profile_id"], DOCTORAL)
        options = {row["id"]: row for row in draft["compatible_modules"]["storage_cost"]}
        self.assertFalse(options["dynamic-annual-storage-cost"]["methodology_supported"])
        self.assertTrue(options["value-legacy-storage-tariff"]["methodology_supported"])
        ok = resolve_study_draft(self._project(DOCTORAL), registry=self.registry, module_catalog=[], base_dataset_slots=[])
        self.assertNotIn("VALUE_PROFILE_COMBINATION_UNSUPPORTED", {row["code"] for row in ok["errors"]})
        self.assertEqual(ok["methodology"]["reference_deviations"], [])

    def test_study_resolution_checks_the_network_pack_like_preflight(self):
        """C16: server.resolve_project_draft passes the base and the Network Pack to the whitelist."""

        from types import SimpleNamespace

        from backend import server

        with tempfile.TemporaryDirectory() as folder:
            packs = Path(folder) / "data-packs"
            shutil.copytree(ROOT / "data-packs" / "value-101-baseline-v1", packs / "value-101-baseline-v1")
            network_root = ROOT / "data-packs" / "value-101-network-v1"
            network_manifest = _pack("value-101-network-v1")
            selection = SimpleNamespace(network_manifest=network_manifest, network_pack_root=network_root)
            project = self._project(DOCTORAL)
            project["data_pack_id"] = "value-101-baseline-v1"
            with patch.object(server, "PACKS_ROOT", packs), \
                    patch.object(server, "resolve_zonal_pack_selection", return_value=selection), \
                    patch.object(server, "resolve_study_draft", wraps=resolve_study_draft) as spy:
                draft = server.resolve_project_draft(project)
        ids = [entry[0].get("id") for entry in spy.call_args.kwargs["data_packs"] if entry is not None]
        self.assertEqual(ids, ["value-101-baseline-v1", "value-101-network-v1"])
        violations = [row for issue in draft["errors"] if issue["code"] == "VALUE_PROFILE_COMBINATION_UNSUPPORTED"
                      for row in issue.get("detail") or []]
        self.assertIn("value-101-network-v1", {row.get("data_pack_id") for row in violations if row.get("sub_reason") == "data_pack"})

    def test_preflight_refuses_unsupported_combinations(self):
        def preflight(project):
            with tempfile.TemporaryDirectory() as folder, \
                 patch("gridform_core.preflight.shutil.disk_usage",
                       return_value=SimpleNamespace(total=4 * 1024**4, used=1024**4, free=3 * 1024**4)):
                return run_preflight(
                    project, mode="smoke", pack_root=ROOT / "data-packs" / "value-101-baseline-v1",
                    pack_manifest=_pack("value-101-baseline-v1"), dataset_slots=[], registry=self.registry,
                    output_root=Path(folder),
                )

        refused = preflight(self._project(DOCTORAL, storage="dynamic-annual-storage-cost"))
        self.assertIn("VALUE_PROFILE_COMBINATION_UNSUPPORTED", {row["code"] for row in refused["errors"]})
        self.assertFalse(refused["checks"]["methodology"]["passed"])
        accepted = preflight(self._project(DOCTORAL))
        self.assertTrue(accepted["checks"]["methodology"]["passed"])
        self.assertNotIn("VALUE_PROFILE_COMBINATION_UNSUPPORTED", {row["code"] for row in accepted["errors"]})
        corrected = preflight(self._project(CORRECTED, storage="dynamic-annual-storage-cost"))
        self.assertTrue(corrected["checks"]["methodology"]["passed"])
        self.assertEqual(corrected["checks"]["methodology"]["profile_id"], CORRECTED)


if __name__ == "__main__":
    unittest.main()
