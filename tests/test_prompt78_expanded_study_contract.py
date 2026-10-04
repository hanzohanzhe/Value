from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backend.server as server
from gridform_core.catalog import DATASET_SLOTS, MODULES
from gridform_core.data_contract_templates import runtime_supported_formats, template_for_role
from gridform_core.frontend_contract import (
    EXPERIMENTAL_ACK,
    extension_catalogue,
    module_slot_catalog,
    resolve_study_draft,
)
from gridform_core.project_revision import save_project_revision
from gridform_core.v2.module_manifest import workspace_registry


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"
BASE_MODULES = {
    "psm": "value-bid-at-cost-psm",
    "storage_cost": "dynamic-annual-storage-cost",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "transition": "value-annual-state-transition",
}


class Prompt78ExpandedStudyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = workspace_registry(ROOT / "missing-p78-local-modules")
        self.pack = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
        self.base_roles = tuple(self.pack["bindings"])

    def draft(self, **changes: object) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": "value.study-draft/v1",
            "name": "Prompt 78 fixture",
            "data_pack_id": self.pack["id"],
            "start_year": 2025,
            "end_year": 2026,
            "modules": dict(BASE_MODULES),
            "selected_extensions": [],
            "extension_parameters": {},
            "maturity_acknowledgements": {},
            "parameters": {},
            "runtime_options": {},
        }
        value.update(changes)
        return value

    def resolve(self, draft: dict[str, object], roles: tuple[str, ...] | None = None):
        return resolve_study_draft(
            draft,
            registry=self.registry,
            module_catalog=MODULES,
            base_dataset_slots=DATASET_SLOTS,
            available_data_roles=roles if roles is not None else self.base_roles,
        )

    def test_workspace_catalogue_is_registry_owned_and_hides_unreleased_expansion_slot(self):
        slots = module_slot_catalog(self.registry, MODULES)
        by_slot = {item["slot"]: item for item in slots}
        self.assertNotIn("network_expansion", by_slot)
        self.assertTrue(
            self.registry.manifest("reference-transmission-expansion").slot
            == "network_expansion"
        )
        extensions = {item["id"]: item for item in extension_catalogue(self.registry)}
        self.assertEqual(extensions["value-network-contract-extension"]["maturity"], "ready")
        self.assertNotIn("value-ac-data-extension", extensions)
        self.assertIn("data_roles", extensions["value-hydrology-extension"])
        internal = workspace_registry(
            ROOT / "missing-p78-local-modules",
            include_internal_experimental=True,
        )
        self.assertEqual(
            internal.extension_registry.manifest("value-ac-data-extension").maturity,
            "experimental",
        )

    def test_base_draft_keeps_the_frozen_no_extension_graph(self):
        report = self.resolve(self.draft())
        self.assertTrue(report["valid"], report["errors"])
        expected = self.registry.resolve_selection(BASE_MODULES)
        self.assertEqual(report["graph_sha256"], expected.graph_sha256)
        self.assertNotIn("extension_graph", report["graph_preview"])

    def test_dc_requires_network_roles_then_resolves_the_same_graph_everywhere(self):
        modules = {**BASE_MODULES, "psm": "value-reference-dc-network"}
        modules.pop("storage_cost")
        draft = self.draft(
            modules=modules,
            selected_extensions=["value-network-contract-extension"],
        )
        missing = self.resolve(draft)
        self.assertFalse(missing["valid"])
        self.assertIn("GF_EXTENSION_DATA_MISSING", {item["code"] for item in missing["errors"]})
        network_roles = tuple(
            item.role
            for item in self.registry.extension_registry.manifest(
                "value-network-contract-extension"
            ).data_roles
            if item.required
        )
        ready = self.resolve(draft, self.base_roles + network_roles)
        self.assertTrue(ready["valid"], ready["errors"])
        expected = self.registry.resolve_selection(
            modules,
            selected_extensions=("value-network-contract-extension",),
            available_data_roles=self.base_roles + network_roles,
        )
        self.assertEqual(ready["graph_sha256"], expected.graph_sha256)

        manifest = json.loads(json.dumps(self.pack))
        template = dict(next(iter(manifest["bindings"].values())))
        for role in network_roles:
            manifest["bindings"][role] = {**template, "role": role}
        with tempfile.TemporaryDirectory(prefix="force-p78-revision-") as temporary:
            saved = save_project_revision(
                Path(temporary) / "project",
                ready["normalised_project"],
                self.registry,
                manifest,
            )
        self.assertEqual(
            saved["module_resolution_graph"]["graph_sha256"],
            ready["graph_sha256"],
        )

    def test_ac_and_expansion_fail_without_versioned_acknowledgement(self):
        internal = workspace_registry(
            ROOT / "missing-p78-local-modules",
            include_internal_experimental=True,
        )
        modules = {**BASE_MODULES, "psm": "value-reference-ac-feasibility"}
        modules.pop("storage_cost")
        selected = ["value-network-contract-extension", "value-ac-data-extension"]
        roles = self.base_roles + tuple(
            role.role
            for extension_id in selected
            for role in internal.extension_registry.manifest(extension_id).data_roles
            if role.required
        )
        draft = self.draft(modules=modules, selected_extensions=selected)
        blocked = resolve_study_draft(
            draft,
            registry=internal,
            module_catalog=internal.catalog(),
            base_dataset_slots=DATASET_SLOTS,
            available_data_roles=roles,
        )
        acknowledgements = blocked["maturity"]["acknowledgements_required"]
        self.assertEqual({item["kind"] for item in acknowledgements}, {"module", "extension"})
        self.assertIn("GF_EXPERIMENTAL_ACK_REQUIRED", {item["code"] for item in blocked["errors"]})
        draft["maturity_acknowledgements"] = {
            item["key"]: EXPERIMENTAL_ACK for item in acknowledgements
        }
        ready = resolve_study_draft(
            draft,
            registry=internal,
            module_catalog=internal.catalog(),
            base_dataset_slots=DATASET_SLOTS,
            available_data_roles=roles,
        )
        self.assertTrue(ready["valid"], ready["errors"])

    def test_hydrology_parameter_and_unknown_fields_fail_closed(self):
        extension = self.registry.extension_registry.manifest("value-hydrology-extension")
        roles = self.base_roles + tuple(role.role for role in extension.data_roles if role.required)
        draft = self.draft(
            selected_extensions=[extension.id],
            extension_parameters={"value.hydrology.information-structure": "omniscient_magic"},
            maturity_acknowledgements={
                f"extension:{extension.id}@{extension.version}": EXPERIMENTAL_ACK
            },
            made_up_capability=True,
        )
        report = self.resolve(draft, roles)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("GF_STUDY_FIELD_UNKNOWN", codes)
        self.assertIn("GF_EXTENSION_PARAMETER_INVALID", codes)

    def test_server_validation_preserves_resolved_extension_fields(self):
        extension = self.registry.extension_registry.manifest("value-hydrology-extension")
        draft = self.draft(
            selected_extensions=[extension.id],
            maturity_acknowledgements={
                f"extension:{extension.id}@{extension.version}": EXPERIMENTAL_ACK
            },
        )
        with tempfile.TemporaryDirectory(prefix="force-p78-server-") as temporary:
            packs = Path(temporary)
            pack_root = packs / str(self.pack["id"])
            pack_root.mkdir(parents=True)
            manifest = json.loads(json.dumps(self.pack))
            for source in PACK.rglob("*"):
                if source.is_file():
                    destination = pack_root / source.relative_to(PACK)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(source.read_bytes())
            for role in extension.data_roles:
                formats = runtime_supported_formats(role.role, role.formats)
                raw, _media_type, filename = template_for_role(role.role, formats)
                destination = pack_root / "conditional" / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                manifest["bindings"][role.role] = {
                    "role": role.role,
                    "uri": destination.relative_to(pack_root).as_posix(),
                    "filename": filename,
                    "format": destination.suffix.lstrip("."),
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            (pack_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with (
                patch.object(server, "PACKS_ROOT", packs),
                patch.object(server, "MODULE_REGISTRY", self.registry),
                patch.object(server, "MODULES", MODULES),
            ):
                report = server.validate_project(draft)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(
            report["normalised_project"]["extension_parameters"]
            ["value.hydrology.information-structure"],
            "perfect_foresight",
        )
        self.assertEqual(
            report["normalised_project"]["module_resolution_graph"]["graph_sha256"],
            report["draft_resolution"]["graph_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
