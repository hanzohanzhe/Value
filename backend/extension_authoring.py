"""Build reviewed, bounded audit-observer extension source projects.

The source project is also an inventory-checked installation ZIP. It contains
ordinary trusted local Python; downloading or validating never imports it.
"""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Mapping

from gridform_core.extension_framework import (
    ArtifactDeclaration, ConditionalDataRole, ExtensionManifest,
    ExtensionRegistry, HookDeclaration, NAMESPACE, SEMVER, canonical_hash,
)
from gridform_core.module_installation import MODULE_ID

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "Observes the model year and PSM input identity only; no scientific algorithm or declared-series consumption."
FIELDS = {"id", "name", "namespace", "version", "question", "validation_plan", "migration_notes"}


def _proposal(request: Mapping[str, object]) -> dict[str, str]:
    value = request.get("proposal")
    if not isinstance(value, Mapping) or set(value) != FIELDS:
        raise ValueError("Provide the proposal ID, name, namespace, version, question, validation plan and migration notes.")
    result = {}
    for key, raw in value.items():
        if not isinstance(raw, str) or not raw.strip() or len(raw) > (4096 if key in {"question", "validation_plan", "migration_notes"} else 200):
            raise ValueError(f"Proposal {key} must be non-empty bounded text.")
        result[key] = raw.strip()
    if not MODULE_ID.fullmatch(result["id"]):
        raise ValueError("Extension ID must be 3–64 lowercase letters, digits or hyphens, starting with a letter.")
    if not NAMESPACE.fullmatch(result["namespace"]) or result["namespace"].startswith("value.core"):
        raise ValueError("Use a non-reserved namespaced identifier, such as community.audit-example.")
    if not SEMVER.fullmatch(result["version"]):
        raise ValueError("Extension version must be semantic, such as 0.1.0.")
    return result


def _package(proposal: Mapping[str, str]) -> str:
    return "value_ext_" + canonical_hash([proposal["id"], proposal["version"], proposal["namespace"]])[:16]


def _default_manifest(proposal: Mapping[str, str]) -> ExtensionManifest:
    namespace, package = proposal["namespace"], _package(proposal)
    capability = f"extension.{namespace}.audit/v1"
    return ExtensionManifest(
        id=proposal["id"], name=proposal["name"], version=proposal["version"],
        licence="Apache-2.0", namespace=namespace, provided_capabilities=(capability,),
        data_roles=(ConditionalDataRole(
            role=f"{namespace}.audit-input", capability=capability, group="Extension",
            label="Audit declaration example", formats=("csv",), unit="dimensionless",
            time_semantics="one example row per model year; observer does not consume its values",
            validation_rules={"minimum_rows": 1},
        ),),
        artifacts=(ArtifactDeclaration(
            artifact_type=f"{namespace}.year-summary", media_type="application/json",
            schema_version=f"{namespace}.artifact/v1", summary_fields=("year", "source_inputs_sha256"),
        ),),
        hooks=tuple(HookDeclaration(hook=name, implementation=f"{package}.hooks:AuditObserver")
                    for name in ("initialize", "after_psm")),
        state_schema_version=f"{namespace}.state/v1", maturity="experimental",
        required_contract_versions={"project": "value.project/v2"},
    )


def _validate_manifest(proposal: Mapping[str, str], raw: object, registry: object) -> ExtensionManifest:
    manifest = _default_manifest(proposal) if raw is None else ExtensionManifest.from_dict(raw)
    for field in ("id", "name", "namespace", "version"):
        if getattr(manifest, field) != proposal[field]:
            raise ValueError(f"Manifest {field} must match the proposal; edit both or reset the manifest.")
    if manifest.licence != "Apache-2.0" or manifest.maturity != "experimental":
        raise ValueError("The generated observer uses Apache-2.0 and experimental maturity.")
    if manifest.id in registry.extension_manifests():
        raise ValueError("This extension ID is already installed. Choose an independent ID for this new-function scaffold.")
    if len(manifest.data_roles) > 32 or len(manifest.parameters) > 32 or len(manifest.composed_module_ids) > 32:
        raise ValueError("The scaffold supports at most 32 roles, parameters or composed modules.")
    expected_hooks = {(name, f"{_package(proposal)}.hooks:AuditObserver") for name in ("initialize", "after_psm")}
    if len(manifest.hooks) != 2 or {(item.hook, item.implementation) for item in manifest.hooks} != expected_hooks:
        raise ValueError("This executable scaffold supports initialize and after_psm on its generated AuditObserver only. Add other algorithms locally.")
    if any(item.before or item.after for item in manifest.hooks):
        raise ValueError("The generated observer has no cross-extension ordering requirements; define and validate them locally.")
    actual_capability = f"extension.{proposal['namespace']}.audit/v1"
    if tuple(manifest.provided_capabilities) != (actual_capability,):
        raise ValueError("The generated observer only implements " + actual_capability)
    def bounded_identifier(value, label):
        if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 200:
            raise ValueError(label + " must be a non-empty identifier string of at most 200 characters.")
    bounded_identifier(manifest.state_schema_version, "Observer state schema version")
    if len(manifest.artifacts) != 1 or manifest.artifacts[0].media_type != "application/json":
        raise ValueError("Declare one JSON observer artifact.")
    artifact = manifest.artifacts[0]
    bounded_identifier(artifact.artifact_type, "Observer artifact type")
    bounded_identifier(artifact.schema_version, "Observer artifact schema version")
    if (not artifact.artifact_type or not artifact.schema_version
            or not artifact.summary_fields or len(set(artifact.summary_fields)) != len(artifact.summary_fields)
            or not set(artifact.summary_fields).issubset({"year", "source_inputs_sha256"})):
        raise ValueError("The observer summary supports year and source_inputs_sha256; other metrics need a local implementation.")
    missing = set(manifest.composed_module_ids).difference(registry.manifests())
    if missing:
        raise ValueError("Install the composed modules first: " + ", ".join(sorted(missing)))
    ExtensionRegistry(tuple(registry.extension_manifests().values()) + (manifest,))
    return manifest


def _files(proposal: Mapping[str, str], manifest: ExtensionManifest) -> dict[str, bytes]:
    package, artifact = _package(proposal), manifest.artifacts[0]
    source = f'''"""Generated experimental observer. No dispatch or investment calculations."""
import re


class AuditObserver:
    def initialize(self, payload):
        return {{"schema_version": {manifest.state_schema_version!r}, "owner": {manifest.id!r},
                "initialized_year": payload["year"]}}

    def after_psm(self, payload):
        digest = payload["input_sha256"]
        year = payload["year"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{{64}}", digest):
            raise ValueError("Observer requires the recorded PSM input SHA-256")
        if not isinstance(year, int) or isinstance(year, bool):
            raise ValueError("Observer requires an integer model year")
        return {{"schema_version": {artifact.schema_version!r}, "producer_extension": {manifest.id!r},
                "artifact_type": {artifact.artifact_type!r}, "source_inputs_sha256": digest, "year": year}}
'''
    readme = f'''# {proposal['name']}

Research question: {proposal['question']}

## Executable scope

{SCOPE}

This is an experimental local Python extension. The declared CSV role proves data binding and validation only; this observer does not calculate with its values. Capability and data declarations alone do not implement a scientific method. Initialization owns namespace `{manifest.namespace}` under extension `{manifest.id}` and schema `{manifest.state_schema_version}`. The after_psm hook emits one declared JSON artifact for each executed model year.

## What a Run records

VALUE records two hook outputs: the state returned by `initialize` (stored under the extension namespace) and the artifacts returned by `after_psm` (one set per executed model year, shown in Inspect → Artifacts & provenance). The other hooks (`preflight`, `before_psm`, `before_cem`, `after_cem`, `transition`, `finalize`) run in their lifecycle position, but their return values are not recorded. Returning a declared artifact (a mapping with `artifact_type`) from one of them stops the Run with an error naming the hook, so no result is dropped silently; produce artifacts from `after_psm` instead.

## Author validation plan

{proposal['validation_plan']}

## Migration declaration

{proposal['migration_notes']}

Migration notes and manifest entries do not execute a state migration. New physical algorithms need their own numerical examples and validation.

## Use and edit

1. Inspect the manifest and Python source before trusting and installing this ZIP in Modules.
2. Open an independent Study draft. In Advanced → Optional domains, select the installed extension. Create an independent data-pack copy.
3. In Data, choose the draft context and bind `examples/audit-input.csv` to the declared audit role, adjusting years if needed. Return to the Study, select this pack, acknowledge experimental maturity, review the contracts and save.
4. Check readiness and explicitly start a bounded connection check. Open its extension result summaries in Inspect. A connection check is not an annual scientific result.
5. To implement another function, edit source, manifest, schemas and examples locally, then rebuild inventory from the VALUE repository:

```sh
python scripts/build_extension_bundle.py --project-root /path/to/extracted-project --output /path/to/reviewed-extension.zip
```

Use a new extension ID and Python package for an independent implementation. Keep original Run evidence. Rebuilding verifies packaging, not scientific validity.
'''
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False,
              "required": ["schema_version", "producer_extension", "artifact_type", "source_inputs_sha256", "year"],
              "properties": {"schema_version": {"const": artifact.schema_version}, "producer_extension": {"const": manifest.id},
                             "artifact_type": {"const": artifact.artifact_type}, "source_inputs_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "year": {"type": "integer"}}}
    json_bytes = lambda value: (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    return {
        "force-extension.json": json_bytes(manifest.to_dict()), "LICENSE": (ROOT / "LICENSE").read_bytes(),
        "README.md": readme.encode("utf-8"), "examples/proposal.json": json_bytes(dict(proposal)),
        "examples/audit-input.csv": b"year,value\n2025,1\n2026,1\n", "schemas/artifact.schema.json": json_bytes(schema),
        f"src/{package}/__init__.py": b"", f"src/{package}/hooks.py": source.encode("utf-8"),
    }


def _zip(files: Mapping[str, bytes]) -> bytes:
    descriptor = {"schema_version": "value.extension-bundle/v1", "manifest": "force-extension.json", "files": [
        {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(files.items())]}
    entries = {**files, "force-extension-bundle.json": (json.dumps(descriptor, indent=2, ensure_ascii=False) + "\n").encode()}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def validate_extension_proposal(request: Mapping[str, object], registry: object) -> dict[str, object]:
    report = {"schema_version": "value.extension-authoring/v1", "valid": False, "errors": [], "warnings": [],
              "proposal": request.get("proposal"), "manifest": None, "state_responsibility": None,
              "template_kind": "audit-observer", "execution_scope": SCOPE, "source_package": None,
              "manifest_sha256": None, "package_identity_sha256": None}
    try:
        proposal = _proposal(request)
        raw = request.get("manifest")
        if raw is not None and not isinstance(raw, Mapping):
            raise ValueError("Advanced manifest must be a JSON object.")
        manifest = _validate_manifest(proposal, raw, registry)
        content = _zip(_files(proposal, manifest))
        report.update(valid=True, proposal=proposal, manifest=manifest.to_dict(),
                      source_package=_package(proposal), manifest_sha256=canonical_hash(manifest.to_dict()),
                      package_identity_sha256=hashlib.sha256(content).hexdigest(),
                      state_responsibility={"owner": manifest.id, "namespace": manifest.namespace, "schema_version": manifest.state_schema_version},
                      warnings=["Experimental observer only; structural validation does not prove a scientific method.",
                                "Declared input roles are validated bindings; this observer does not consume their values.",
                                "Migration entries are declarations; no state migration is executed by this generator."])
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        report["errors"] = [str(exc)]
    return report


def extension_proposal_template(request: Mapping[str, object], registry: object) -> bytes:
    report = validate_extension_proposal(request, registry)
    if not report["valid"]:
        raise ValueError("; ".join(report["errors"]))
    if request.get("expected_package_identity_sha256") != report["package_identity_sha256"]:
        raise ValueError("The proposal or generated source changed after review. Validate it again before downloading.")
    content = _zip(_files(report["proposal"], ExtensionManifest.from_dict(report["manifest"])))
    if hashlib.sha256(content).hexdigest() != request.get("expected_package_identity_sha256"):
        raise ValueError("The generated ZIP bytes changed after review. Validate it again before downloading.")
    return content


def build_extension_source_project(project_root: Path, destination: Path) -> dict[str, object]:
    """Rebuild edited local files; never import their Python code."""
    from gridform_core.extension_bundle import validate_extension_bundle
    from gridform_core.module_bundle import MAX_MEMBERS, MAX_UNCOMPRESSED_BYTES
    root = project_root.resolve()
    files, size = {}, 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Source projects cannot contain symbolic links.")
        if not path.is_file() or path.name == "force-extension-bundle.json" or path.resolve() == destination.resolve():
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        size += path.stat().st_size
        if size > MAX_UNCOMPRESSED_BYTES or len(files) >= MAX_MEMBERS - 1:
            raise ValueError("Extension source project exceeds the bounded bundle size or member count.")
        files[path.relative_to(root).as_posix()] = path.read_bytes()
    content = _zip(files)
    with tempfile.TemporaryDirectory(prefix="value-extension-build-") as temporary:
        staged = Path(temporary) / "extension.zip"
        staged.write_bytes(content)
        validated = validate_extension_bundle(staged)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return {"extension_id": validated.manifest.id, "version": validated.manifest.version,
            "bundle_sha256": hashlib.sha256(content).hexdigest(), "bundle_bytes": len(content)}
