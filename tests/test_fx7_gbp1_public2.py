"""FX7 (decisions A16-6, A16-7): solar model approval status; GBP1 public2 local registration.

A16-6: the author approved the A13 plane-of-array model choices directly; the
parameter table and the reference statistics say so, with the values unchanged.

A16-7: GBP1 public2 (local build, never published) is registered locally as a
scientific_reference pack, and the VALUE-UK nuclear station fleet applies to
it under the profile-gated correction ``p05.nuclear-stations-public2``.  The
GBP1 case needs ``VALUE_P0_5_PACKS`` = GBP1 public1 directory, then R029
public1 directory (the P0-5 research-pack convention); public2 is built from
them into a temporary directory with hardlinks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOSS_TABLE = ROOT / "gridform_core" / "data" / "weather" / "value_uk_vre_loss_factors_v1.json"
REFERENCE_STATISTICS = ROOT / "docs" / "dev" / "REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md"


class SolarModelApprovalTests(unittest.TestCase):
    def test_parameter_table_marks_the_a13_model_choices_approved(self):
        table = json.loads(LOSS_TABLE.read_text(encoding="utf-8"))
        solar = table["solar_plane_of_array"]
        self.assertTrue(solar["status"].startswith("AUTHOR APPROVED (DECISIONS A16-6"))
        self.assertNotIn("PENDING", solar["status"])
        self.assertIn("A16-6", table["status"])
        self.assertNotIn("PENDING", table["status"])
        # The approval changes no value (A16-6: "作者直接认可").
        self.assertEqual((solar["tilt_rule"], solar["decomposition"], solar["transposition"]),
                         ("jacobson-jadhav-2018", "erbs-1982", "hay-davies-1980"))
        self.assertEqual((solar["albedo"], solar["solar_constant_w_m2"], solar["max_zenith_deg"]), (0.2, 1361.0, 87.0))

    def test_reference_statistics_section_3_5_is_approved(self):
        text = REFERENCE_STATISTICS.read_text(encoding="utf-8")
        heading = next(line for line in text.splitlines() if line.startswith("### 3.5 "))
        self.assertIn("作者已认可，A16-6", heading)
        self.assertIn("已由作者直接认可（DECISIONS A16-6", text.splitlines()[2])

    def test_catalogue_descriptions_match_the_code(self):
        from gridform_core.methodology import load_catalogue

        catalogue = load_catalogue()
        solar = catalogue.corrections["p05.solar-plane-of-array"].description
        self.assertIn("Jacobson & Jadhav (2018) optimal tilt", solar)
        self.assertNotIn("tilted at the site latitude", solar)
        self.assertNotIn("PENDING", catalogue.corrections["p05.vre-loss-factors"].description)


PUBLIC1 = "value-uk-open-data-pack-v1"
PUBLIC2 = "value-uk-open-data-pack-public2"
R029 = "value-uk-calendar-vx-trade001"
CORRECTION = "p05.nuclear-stations-public2"


def _research_packs() -> tuple[Path, Path] | None:
    parts = [Path(item) for item in os.environ.get("VALUE_P0_5_PACKS", "").split(os.pathsep) if item.strip()]
    found: dict[str, Path] = {}
    for root in parts:
        manifest = root / "manifest.json"
        if manifest.is_file():
            found.setdefault(str(json.loads(manifest.read_text(encoding="utf-8")).get("id")), root)
    if PUBLIC1 in found and R029 in found:
        return found[PUBLIC1], found[R029]
    return None


class Public2RegistrationTests(unittest.TestCase):
    def test_public2_is_a_locally_registered_scientific_reference(self):
        from gridform_core import methodology

        self.assertEqual(methodology.KNOWN_PACK_CLASSES[PUBLIC2], "scientific_reference")
        self.assertEqual(methodology.classify_data_pack({"id": PUBLIC2, "pack_class": "scientific_reference"}),
                         "scientific_reference")
        # A conflicting self-declaration still makes the pack the strictest class.
        self.assertEqual(methodology.classify_data_pack({"id": PUBLIC2, "pack_class": "synthetic"}), "user_workspace")

    def test_corrected_policy_is_strict_and_doctoral_does_not_pin_public2(self):
        from gridform_core import methodology
        from gridform_core.data_method import policy_for_profile

        policy = policy_for_profile("value-corrected", {"id": PUBLIC2})
        self.assertEqual((policy.pack_class, policy.strictness), ("scientific_reference", "strict"))
        rows = methodology.combination_violations(methodology.REFERENCE_PROFILE_ID,
                                                  data_packs=[({"id": PUBLIC2, "bindings": {}}, None)])
        self.assertTrue(rows)
        self.assertEqual(methodology.combination_violations("value-corrected",
                                                            data_packs=[({"id": PUBLIC2, "bindings": {}}, None)]), [])

    def test_builder_pack_id_matches_the_registry(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import build_value_uk_pack_revision as builder
        finally:
            sys.path.remove(str(ROOT / "scripts"))
        from gridform_core import pack_source_identity

        self.assertEqual(builder.PACK_ID, PUBLIC2)
        self.assertEqual(pack_source_identity.VALUE_UK_OPEN_DATA_PACK_PUBLIC2_ID, PUBLIC2)


class Public2ProfileIntervalTests(unittest.TestCase):
    """The builder declares the hourly VRE profiles, so the strict corrected reader accepts sa.csv (8761 hours)."""

    def test_declared_hourly_profile_reads_on_the_half_hour_clock(self):
        import hashlib

        from gridform_core.data_method import policy_for_profile, read_role
        from tests.test_p05b_pack_revision import _toy_packs
        from scripts import build_value_uk_pack_revision as builder

        hours = [round((h % 24) / 24.0, 6) for h in range(8761)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, approved = _toy_packs(root)
            manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
            relative = "files/profiles__vre_solar/sa.csv"
            (base / relative).parent.mkdir(parents=True)
            (base / relative).write_text("\n".join(str(v) for v in hours) + "\n", encoding="utf-8")
            manifest["bindings"]["profiles.vre_solar"] = {
                "uri": relative, "sha256": hashlib.sha256((base / relative).read_bytes()).hexdigest(), "unit": "p.u."}
            (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            builder.build(base, approved, root / "public2")
            built = json.loads((root / "public2" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(built["bindings"]["profiles.vre_solar"]["interval_minutes"], 60)
            self.assertEqual(built["derivation"]["builder"], "scripts/build_value_uk_pack_revision.py@v2")
            policy = policy_for_profile("value-corrected", built)
            self.assertEqual(policy.strictness, "strict")
            values = read_role(root / "public2", built, "profiles.vre_solar", policy, periods=17520).values
            # Undeclared, the same bytes are refused as a short series by the strict reader.
            del built["bindings"]["profiles.vre_solar"]["interval_minutes"]
            with self.assertRaisesRegex(Exception, "GF_DATA_SHORT_SERIES"):
                read_role(root / "public2", built, "profiles.vre_solar", policy, periods=17520)
        self.assertEqual(len(values), 17520)
        self.assertEqual(list(values[:6]), [hours[0], hours[0], hours[1], hours[1], hours[2], hours[2]])
        self.assertEqual(values[17519], hours[8759])


class NuclearStationsPublic2Tests(unittest.TestCase):
    """Trigger fixture of p05.nuclear-stations-public2."""

    def test_catalogue_entry_is_profile_gated_and_corrected_only(self):
        from gridform_core.methodology import REFERENCE_PROFILE_ID, load_catalogue, resolve_methodology

        correction = load_catalogue().corrections[CORRECTION]
        self.assertEqual((correction.track, correction.scope), ("profile_gated", "kernel_input"))
        self.assertEqual(set(correction.affects), {"trajectory", "accounting"})
        self.assertTrue(resolve_methodology("value-corrected").enabled(CORRECTION))
        self.assertFalse(resolve_methodology(REFERENCE_PROFILE_ID).enabled(CORRECTION))

    def test_station_fleet_follows_the_correction_on_public2_only(self):
        from gridform_core.methodology import REFERENCE_PROFILE_ID, activate, resolve_methodology
        from gridform_core.nuclear_policy import applies_to_data_pack

        corrected = resolve_methodology("value-corrected")
        doctoral = resolve_methodology(REFERENCE_PROFILE_ID)
        for methodology_, expected in ((corrected, True), (doctoral, False)):
            with self.subTest(profile=methodology_.profile_id):
                self.assertIs(applies_to_data_pack({"id": PUBLIC2}, methodology_), expected)
                # GBP1 public1 keeps its unconditional policy; others never take it.
                self.assertTrue(applies_to_data_pack({"id": PUBLIC1}, methodology_))
                self.assertFalse(applies_to_data_pack({"id": R029}, methodology_))
                with activate(methodology_):
                    self.assertIs(applies_to_data_pack({"id": PUBLIC2}), expected)
        # Outside a Run (preflight, previews): the catalogue default, the corrected profile.
        self.assertTrue(applies_to_data_pack({"id": PUBLIC2}))

    def test_public2_is_id_keyed_for_frozen_input_recovery(self):
        from gridform_core import pack_source_identity

        self.assertIn(PUBLIC2, pack_source_identity.NUCLEAR_POLICY_PACK_IDS)
        self.assertIn(PUBLIC2, pack_source_identity.ID_KEYED_PACK_IDS)
        self.assertEqual(pack_source_identity.NUCLEAR_POLICY_GATED_PACK_IDS, frozenset({PUBLIC2}))
        self.assertNotIn(PUBLIC2, pack_source_identity.DOCTORAL_WEATHER_PACK_IDS)

    @unittest.skipUnless(_research_packs(), "needs VALUE_P0_5_PACKS with GBP1 public1 and R029 public1")
    def test_gbp1_public2_state_has_the_edf_stations_and_their_load_factors(self):
        from gridform_core import firm_availability as firm
        from gridform_core.canonical_psm_data import native_initial_state
        from gridform_core.methodology import REFERENCE_PROFILE_ID, activate, resolve_methodology

        gbp1, r029 = _research_packs()  # type: ignore[misc]
        with tempfile.TemporaryDirectory(prefix="value-fx7-public2-") as temporary:
            out = Path(temporary) / "public2"
            # Hardlinks (read only here): a symlinked binding would escape the pack root.
            build = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "build_value_uk_pack_revision.py"),
                                    "--base", str(gbp1), "--approved", str(r029), "--out", str(out),
                                    "--link", "hardlink"], capture_output=True, text=True, cwd=ROOT)
            if build.returncode != 0 and "Invalid cross-device link" in build.stderr:
                self.skipTest("the temporary directory is on another file system than the research packs")
            self.assertEqual(build.returncode, 0, build.stderr[-2000:])
            with activate(resolve_methodology("value-corrected")):
                corrected = native_initial_state(out, 2025, scientific_parameters={})
            with activate(resolve_methodology(REFERENCE_PROFILE_ID)):
                aggregate = native_initial_state(out, 2025, scientific_parameters={})
        stations = {asset.asset_id: asset.capacity_mw for asset in corrected.assets if asset.technology == "Nuclear"}
        self.assertEqual(set(stations), {"nuclear:heysham-1", "nuclear:hartlepool", "nuclear:heysham-2",
                                         "nuclear:torness", "nuclear:sizewell-b"})
        self.assertEqual(sum(stations.values()), 5958.0)
        self.assertIn("nuclear_policy", corrected.extensions)
        self.assertTrue(any(project.technology == "Nuclear" for project in corrected.planning_projects))
        self.assertEqual([asset.asset_id for asset in aggregate.assets if asset.technology == "Nuclear"], ["Nuclear"])
        self.assertNotIn("nuclear_policy", aggregate.extensions)
        # Each station takes its own (A14) load factor, not the national fallback 0.723.
        bases = set()
        for asset in corrected.assets:
            if asset.technology == "Nuclear":
                profile, evidence = firm.asset_availability(
                    asset_id=asset.asset_id, technology="Nuclear", capacity_mw=asset.capacity_mw, year=2025,
                    periods=96, extensions=dict(asset.extensions))
                bases.add(evidence["basis"])
        self.assertEqual(bases, {"station"})


if __name__ == "__main__":
    unittest.main()
