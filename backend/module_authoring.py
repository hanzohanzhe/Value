"""Read-only registered module authoring evidence and local source scaffolds."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Mapping

from gridform_core.module_conformance import REQUIRED_METHODS
from gridform_core.module_installation import MODULE_ID
from gridform_core.v2.module_manifest import SEMVER

MAX_SOURCE_BYTES = 64 * 1024
ROOT = Path(__file__).resolve().parents[1]


def _source(manifest):
    # Registration already loaded the entry point; GET must not import/instantiate it.
    module = sys.modules.get(manifest.implementation.split(":", 1)[0])
    filename = getattr(module, "__file__", None)
    path = Path(filename) if filename else None
    if path is None or path.suffix != ".py" or not path.is_file():
        return None, {"available": False, "filename": None, "content": None, "truncated": False, "reason": "registered_python_source_unavailable"}
    digest = hashlib.sha256()
    shown = bytearray()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(MAX_SOURCE_BYTES), b""):
            digest.update(chunk)
            size += len(chunk)
            if len(shown) < MAX_SOURCE_BYTES:
                shown.extend(chunk[:MAX_SOURCE_BYTES - len(shown)])
    return digest.hexdigest(), {"available": True, "filename": path.name, "content": bytes(shown).decode("utf-8", errors="ignore"), "truncated": size > MAX_SOURCE_BYTES, "reason": "source_display_limited_to_64_kib" if size > MAX_SOURCE_BYTES else None}


def _detail_identity(registry, module_id, expected_slot=None):
    manifest = registry.manifest(module_id, expected_slot=expected_slot)
    digest, source = _source(manifest)
    identity = {"module_id": manifest.id, "module_version": manifest.version, "slot": manifest.slot, "contract_version": manifest.contract_version, "entry_point": manifest.implementation, "source_sha256": digest, "scientific_version": manifest.scientific_version, "execution_kind": manifest.execution_kind}
    raw = json.dumps({"manifest": manifest.to_dict(), "identity": identity}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return manifest, identity, hashlib.sha256(raw).hexdigest(), source


def module_candidate_identity(registry, module_id, expected_slot=None) -> str:
    _, identity, identity_hash, _ = _detail_identity(registry, module_id, expected_slot)
    if identity["source_sha256"] is None:
        raise ValueError("Registered module source identity is unavailable")
    return identity_hash


def module_authoring_detail(registry, module_id, *, installation_records=()) -> dict:
    manifest, identity, identity_hash, source = _detail_identity(registry, module_id)
    manifest_hash = hashlib.sha256(json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    conformance = {"status": "not_run", "errors": [], "warnings": [], "scientific_validation_status": "not_evaluated", "origin": None}
    for record in installation_records:
        if not isinstance(record, Mapping):
            continue
        report = record.get("conformance")
        if not isinstance(report, Mapping) or identity["source_sha256"] is None:
            continue
        if record.get("manifest_sha256") != manifest_hash or record.get("module_id") != manifest.id or record.get("module_version") != manifest.version or record.get("source_sha256") != identity["source_sha256"] or record.get("slot") != manifest.slot or record.get("contract_version") != manifest.contract_version or record.get("implementation") != manifest.implementation:
            continue
        if report.get("module_id") != manifest.id or report.get("version") != manifest.version or report.get("slot") != manifest.slot or report.get("status") not in {"passed", "failed"}:
            continue
        conformance = {"status": report["status"], "errors": list(report.get("errors") or []), "warnings": list(report.get("warnings") or []), "scientific_validation_status": record.get("scientific_validation_status", "not_evaluated"), "origin": record.get("origin")}
        break
    return {"schema_version": "value.module-authoring/v1", "module_id": manifest.id, "identity": identity, "identity_sha256": identity_hash, "manifest": manifest.to_dict(), "methods": list(REQUIRED_METHODS.get(manifest.slot, ())), "source": source, "conformance": conformance}


def module_authoring_template(registry, module_id, *, template_id=None, version="0.1.0") -> bytes:
    manifest = registry.manifest(module_id)
    if template_id is None:
        base = "draft-" + manifest.id
        template_id = base if len(base) <= 64 else base[:51].rstrip("-") + "-" + hashlib.sha256(base.encode()).hexdigest()[:12]
    if not isinstance(template_id, str) or not MODULE_ID.fullmatch(template_id):
        raise ValueError("Template module ID must contain lowercase letters, digits and hyphens, start with a letter, and have between 3 and 64 characters")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ValueError("Template version must be semantic")
    if template_id in registry.manifests():
        raise ValueError("Template module ID is already registered")
    package = "value_author_" + hashlib.sha256(template_id.encode()).hexdigest()[:12]
    payload = json.loads((ROOT / "examples" / "external_module_bundle" / "value-module.json").read_text(encoding="utf-8")) if manifest.slot == "storage_cost" else manifest.to_dict()
    payload.update(id=template_id, name="Draft " + manifest.name, version=version, implementation=package + ".plugin:CandidateModule", scientific_version="flat42-example-only" if manifest.slot == "storage_cost" else "scaffold-not-validated", status="experimental", solver_contract={}, provides_capabilities=[], requires_capabilities=[], description="Local authoring scaffold; requires implementation and validation before research use.")
    if manifest.slot == "storage_cost":
        payload["provides_capabilities"] = ["storage.bid-cost-function"]
        example = ROOT / "examples" / "external_module_bundle" / "src" / "value_example_flat_offer" / "plugin.py"
        source = example.read_text(encoding="utf-8").replace("FlatStorageCostDefinition", "CandidateModule").replace('"example-flat-storage-offer"', repr(template_id)).replace('"1.0.0"', repr(version)).replace('"example-only-not-a-baseline"', '"flat42-example-only"')
        scope = "This executable experimental example returns GBP 42/MWh and implements the real Battery lifecycle. Change the single price_gbp_per_mwh default from 42.0 to 73.0 to change its offer. Update manifest id/version/scientific_version and matching CandidateModule identity before building a new version. The report exposes fixed_offer_gbp_per_mwh and actual annual sales; zero cycle/holding compatibility fields do not represent a scientific cost decomposition. Validate your changed economics before research use."
    else:
        source = '"""Unimplemented local module scaffold. No scientific algorithm is provided."""\n\nclass CandidateModule:\n'
        source += f"    id = {template_id!r}\n    version = {version!r}\n    scientific_version = 'scaffold-not-validated'\n"
        for method in REQUIRED_METHODS[manifest.slot]:
            source += f"\n    def {method}(self, *args, **kwargs):\n        raise NotImplementedError('Implement the declared {manifest.slot} {method} contract before use')\n"
        scope = "All lifecycle methods raise NotImplementedError. Implement the real typed contracts, state responsibilities, units and numerical validation before installing or using the module."
    readme = f"# {template_id}\n\n{scope}\n\nThe manifest records the selected {manifest.slot} slot contract ({manifest.contract_version}) and its data/state responsibilities. See VALUE's gridform_core/v2 interfaces and contract definitions; variadic stubs do not define a new contract. Generic scaffold capability and solver claims are empty; the flat42 example retains only its implemented storage.bid-cost-function declaration. Declare only what your implementation verifies.\n\nThis ZIP is an editable source project, not an installable module bundle. Extract it, edit source and manifest, then build from the VALUE repository root:\n\n```sh\npython scripts/build_module_bundle.py --manifest /path/to/project/value-module.json --source-root /path/to/project/src --license /path/to/project/LICENSE --readme /path/to/project/README.md --output /path/to/{template_id}.zip\n```\n\nInstall the built bundle through Modules to run conformance checks. Conformance does not establish scientific validity. Compare versions in a new derived Study and retain old Run identities. Generated scaffold files are licensed under Apache-2.0 (see LICENSE); no source from the selected module is copied into a generic scaffold.\n"
    files = {"value-module.json": json.dumps(payload, indent=2, ensure_ascii=False) + "\n", f"src/{package}/__init__.py": "", f"src/{package}/plugin.py": source, "README.md": readme, "LICENSE": (ROOT / "LICENSE").read_text(encoding="utf-8")}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in sorted(files.items()):
            archive.writestr(filename, content)
    return stream.getvalue()
