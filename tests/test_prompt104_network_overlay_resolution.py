from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection
from gridform_core.builtin.scheme_c_1000twh.runtime_compat.map_projects_to_generators_by_location import (
    find_nearest_generator,
)


class Prompt104NetworkOverlayResolutionTests(unittest.TestCase):
    def test_location_mapper_does_not_import_the_legacy_plotting_runtime(self) -> None:
        selected, distance = find_nearest_generator(
            51.5074,
            -0.1278,
            "solar",
            {"solar_London": object()},
        )
        self.assertEqual(selected, "solar_London")
        self.assertLess(distance, 1.0)

    def project(self) -> dict[str, object]:
        return {
            "modules": {
                "psm": "value-staged-bid-at-cost-psm",
                "balancing": "value-zonal-redispatch-balancing",
            },
            "selected_extensions": ["value-zonal-redispatch-extension"],
            "market_configuration": {"network_pack_id": "signed-network-v1"},
        }

    def write_pack(self, root: Path, pack_id: str) -> Path:
        root.mkdir(parents=True)
        (root / "manifest.json").write_text(json.dumps({
            "schema_version": "value.data-pack/v1",
            "id": pack_id,
            "data_pack_type": "network_overlay",
            "bindings": {"value.zonal.zones": {}},
        }), encoding="utf-8")
        return root

    def test_explicit_overlay_is_separate_from_the_base_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.write_pack(root / "base", "research-data")
            overlay = self.write_pack(root / "overlay", "signed-network-v1")
            selected = resolve_zonal_pack_selection(
                self.project(), base_pack_root=base, explicit_network_pack_root=overlay
            )
            self.assertEqual(selected.base_pack_root, base.resolve())
            self.assertEqual(selected.network_pack_root, overlay.resolve())
            self.assertEqual(selected.network_pack_id, "signed-network-v1")
            self.assertEqual(
                set(selected.revision_manifest["bindings"]),
                {"value.zonal.zones"},
            )
            self.assertEqual(
                selected.revision_manifest["network_overlay"]["id"],
                "signed-network-v1",
            )

    def test_installed_overlay_is_resolved_by_id_without_an_absolute_study_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.write_pack(root / "base", "research-data")
            overlay = self.write_pack(
                root / "data-workbench" / "installed-packs" / "signed-network-v1",
                "signed-network-v1",
            )
            selected = resolve_zonal_pack_selection(
                self.project(), base_pack_root=base, data_home=root
            )
            self.assertEqual(selected.network_pack_root, overlay.resolve())
            self.assertNotIn(str(root), json.dumps(self.project()))

    def test_wrong_or_missing_signed_overlay_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.write_pack(root / "base", "research-data")
            wrong = self.write_pack(root / "wrong", "another-network")
            with self.assertRaisesRegex(ValueError, "does not match"):
                resolve_zonal_pack_selection(
                    self.project(), base_pack_root=base,
                    explicit_network_pack_root=wrong,
                )
            with self.assertRaisesRegex(ValueError, "not installed"):
                resolve_zonal_pack_selection(
                    self.project(), base_pack_root=base, data_home=root
                )

    def test_copperplate_never_requires_a_network_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = self.write_pack(root / "base", "research-data")
            project = self.project()
            project["modules"]["balancing"] = "value-copperplate-balancing"
            project["selected_extensions"] = []
            project["market_configuration"] = {}
            selected = resolve_zonal_pack_selection(project, base_pack_root=base)
            self.assertIsNone(selected.network_pack_root)
            self.assertIsNone(selected.network_manifest)


if __name__ == "__main__":
    unittest.main()
