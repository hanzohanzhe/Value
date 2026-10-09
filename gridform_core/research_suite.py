"""Non-executable two-pack research-suite bundles for VALUE."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence

from .data_bundle import DataBundleError, install_data_bundle, validate_data_bundle
from .methodology import profile_of_parameters, with_profile
from .project_revision import attach_revision_identity, project_fingerprint, save_project_revision
from .revision_migration import classify_revision_mismatch
from .v2.module_manifest import ModuleRegistryV2


SCHEMA_VERSION = "value.research-suite/v1"
INSTALLATION_SCHEMA = "value.research-suite-installation/v1"
DESCRIPTOR = "research-suite.json"
BASE_MEMBER = "components/base.data-bundle.zip"
NETWORK_MEMBER = "components/network.data-bundle.zip"
STUDIES_MEMBER = "study-templates.json"
RIGHTS_MEMBERS = ("RIGHTS.json", "ATTRIBUTION.md")
ALLOWED_MEMBERS = {DESCRIPTOR, BASE_MEMBER, NETWORK_MEMBER, STUDIES_MEMBER, *RIGHTS_MEMBERS}
MAX_SUITE_BYTES = 3 * 1024 * 1024 * 1024
DEFAULT_SUITE_ID = "value-uk-research-suite-v1"
# The suite ID names the installation folder (research-suites/<id>), so it is
# an immutable safe identifier like a pack ID (R7-2).
SUITE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ResearchSuiteError(ValueError):
    def __init__(self, code: str, message: str, revision_migration: Mapping[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.revision_migration = revision_migration


@dataclass(frozen=True)
class ValidatedResearchSuite:
    descriptor: Mapping[str, object]
    members: tuple[str, ...]
    suite_sha256: str
    suite_bytes: int
    uncompressed_bytes: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stream_member_hash(archive: zipfile.ZipFile, name: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with archive.open(name) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or name.startswith(("/", "\\")) or "\\" in name:
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_PATH", f"Unsafe suite member: {name}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_PATH", f"Unsafe suite member: {name}")
    return path.as_posix()


def _read_json_bytes(data: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_JSON", f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_JSON", f"{label} must contain one JSON object")
    return value


def validate_research_suite(path: Path) -> ValidatedResearchSuite:
    source = Path(path).resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_MISSING", "Select a non-empty VALUE research suite")
    if source.stat().st_size > MAX_SUITE_BYTES:
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_SIZE", "VALUE research suite exceeds the 3 GiB limit")
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            names = [_safe_name(item.filename) for item in infos if not item.is_dir()]
            if len(names) != len(set(names)):
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_DUPLICATE", "Research suite contains duplicate members")
            undeclared = sorted(set(names) - ALLOWED_MEMBERS)
            if undeclared:
                label = "executable or undeclared" if any(Path(name).suffix.lower() in {".exe", ".dll", ".py", ".js", ".ps1", ".bat", ".cmd"} for name in undeclared) else "undeclared"
                raise ResearchSuiteError(
                    "VALUE_RESEARCH_SUITE_MEMBER",
                    f"Research suite contains {label} content: {', '.join(undeclared)}",
                )
            missing = sorted(ALLOWED_MEMBERS - set(names))
            if missing:
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_LAYOUT", "Research suite is missing: " + ", ".join(missing))
            for item in infos:
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ResearchSuiteError("VALUE_RESEARCH_SUITE_LINK", f"Links are not allowed: {item.filename}")
            total = sum(item.file_size for item in infos)
            if total > MAX_SUITE_BYTES:
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_EXPANSION", "Research suite expands beyond 3 GiB")
            descriptor = _read_json_bytes(archive.read(DESCRIPTOR), DESCRIPTOR)
            if descriptor.get("schema_version") != SCHEMA_VERSION:
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_SCHEMA", f"Expected {SCHEMA_VERSION}")
            if not SUITE_ID.fullmatch(str(descriptor.get("suite_id") or "")):
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_ID", "Research suite has no safe immutable suite_id")
            inventory_rows = descriptor.get("files")
            if not isinstance(inventory_rows, list):
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_INVENTORY", "Research suite has no file inventory")
            inventory = {
                str(row.get("path")): row
                for row in inventory_rows
                if isinstance(row, Mapping)
            }
            expected = set(names) - {DESCRIPTOR}
            if set(inventory) != expected:
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_INVENTORY", "Research-suite inventory does not match archive members")
            for name in sorted(expected):
                size, digest = _stream_member_hash(archive, name)
                row = inventory[name]
                if row.get("bytes") != size or row.get("sha256") != digest:
                    raise ResearchSuiteError("VALUE_RESEARCH_SUITE_HASH", f"Research-suite member failed SHA-256 verification: {name}")
            components = descriptor.get("components")
            if not isinstance(components, Mapping):
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_COMPONENTS", "Research suite has no component identities")
            for key, member in (("base", BASE_MEMBER), ("network", NETWORK_MEMBER)):
                component = components.get(key)
                if not isinstance(component, Mapping) or component.get("member") != member:
                    raise ResearchSuiteError("VALUE_RESEARCH_SUITE_COMPONENTS", f"Research suite has an invalid {key} component")
                if component.get("bundle_sha256") != inventory[member].get("sha256"):
                    raise ResearchSuiteError("VALUE_RESEARCH_SUITE_COMPONENTS", f"Research suite {key} identity does not match its member")
    except zipfile.BadZipFile as exc:
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_ZIP", "VALUE research suite is not a readable ZIP") from exc
    return ValidatedResearchSuite(
        descriptor=descriptor,
        members=tuple(sorted(names)),
        suite_sha256=_sha256(source),
        suite_bytes=source.stat().st_size,
        uncompressed_bytes=total,
    )


def _deterministic_write(archive: zipfile.ZipFile, name: str, source: Path, *, stored: bool = False) -> dict[str, object]:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            writer.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return {"path": name, "bytes": size, "sha256": digest.hexdigest()}


def build_research_suite(
    *,
    base_bundle: Path,
    network_bundle: Path,
    studies_path: Path,
    rights_paths: Sequence[Path],
    destination: Path,
    suite_id: str = DEFAULT_SUITE_ID,
) -> dict[str, object]:
    if not SUITE_ID.fullmatch(str(suite_id)):
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_ID", f"Unsafe research-suite ID: {suite_id!r}")
    base = validate_data_bundle(Path(base_bundle))
    network = validate_data_bundle(Path(network_bundle))
    rights = {Path(path).name: Path(path) for path in rights_paths}
    if set(rights) != set(RIGHTS_MEMBERS):
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_RIGHTS", "Research suite needs RIGHTS.json and ATTRIBUTION.md")
    studies = _read_json_bytes(Path(studies_path).read_bytes(), STUDIES_MEMBER)
    if studies.get("schema_version") != "value.study-templates/v1" or not isinstance(studies.get("studies"), list):
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_STUDIES", "Study templates use an unsupported schema")
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    inputs = {
        BASE_MEMBER: Path(base_bundle),
        NETWORK_MEMBER: Path(network_bundle),
        STUDIES_MEMBER: Path(studies_path),
        **rights,
    }
    inventory = [
        {"path": name, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        for name, path in sorted(inputs.items())
    ]
    descriptor = {
        "schema_version": SCHEMA_VERSION,
        "suite_id": str(suite_id),
        "components": {
            "base": {"member": BASE_MEMBER, "pack_id": base.descriptor["pack_id"], "bundle_sha256": base.bundle_sha256},
            "network": {"member": NETWORK_MEMBER, "pack_id": network.descriptor["pack_id"], "bundle_sha256": network.bundle_sha256},
        },
        "study_templates": {"member": STUDIES_MEMBER, "sha256": _sha256(Path(studies_path))},
        "rights_files": list(RIGHTS_MEMBERS),
        "files": inventory,
        "installation_boundary": "local_data_and_declarative_studies_no_executable_content",
    }
    with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
        info = zipfile.ZipInfo(DESCRIPTOR, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, json.dumps(descriptor, indent=2, sort_keys=True).encode("utf-8"))
        for name, source in sorted(inputs.items()):
            _deterministic_write(archive, name, source, stored=name.startswith("components/"))
    os.replace(temporary, destination)
    validated = validate_research_suite(destination)
    return {
        "schema_version": SCHEMA_VERSION,
        "suite_id": descriptor["suite_id"],
        "path": str(destination),
        "bytes": validated.suite_bytes,
        "sha256": validated.suite_sha256,
        "component_pack_ids": [base.descriptor["pack_id"], network.descriptor["pack_id"]],
    }


def _remove_new_directory(path: Path, parent: Path) -> None:
    resolved = path.resolve()
    resolved.relative_to(parent.resolve())
    if resolved.is_dir():
        shutil.rmtree(resolved)


def _existing_suite_study(current: Mapping[str, object], template: Mapping[str, object], study_id: str,
                          registry: ModuleRegistryV2, manifest: Mapping[str, object]) -> None:
    """Accept an installed suite Study whose hash differs only because VALUE changed (X0 S11).

    * same content as the template, migrated with the methodology written
      explicitly: already installed, accepted;
    * same content, saved by an earlier VALUE (code, method or data identity
      changed): refused with a migration code and the classification, so the
      user confirms it through /api/projects/<id>/revision-migration;
    * otherwise a real collision.
    """

    current_now = project_fingerprint(current, registry, manifest)
    template_explicit = project_fingerprint(
        with_profile(template, profile_of_parameters(dict(template.get("parameters") or {}))), registry, manifest,
    )
    if current_now == template_explicit and current.get("revision_sha256") == current_now:
        return
    if current_now in {project_fingerprint(template, registry, manifest), template_explicit}:
        classification = classify_revision_mismatch(current, registry, manifest)
        if classification.get("classification") not in {"content_changed", "none", "unsaved"}:
            raise ResearchSuiteError(
                "VALUE_RESEARCH_SUITE_STUDY_MIGRATION_REQUIRED",
                f"Study {study_id} was installed by an earlier VALUE version; review its revision migration "
                f"(/api/projects/{study_id}/revision-migration), then install the suite again.",
                revision_migration=classification,
            )
    raise ResearchSuiteError("VALUE_RESEARCH_SUITE_STUDY_COLLISION", f"Study ID already exists with different content: {study_id}")


def install_research_suite(
    path: Path,
    *,
    packs_root: Path,
    network_packs_root: Path,
    projects_root: Path,
    base_dataset_slots: Sequence[Mapping[str, object]],
    network_dataset_slots: Sequence[Mapping[str, object]],
    registry: ModuleRegistryV2,
    validate_project: Callable[[dict[str, object]], dict[str, object]],
    revision_manifest: Callable[[dict[str, object], dict[str, object]], dict[str, object]],
    rights_acknowledged: bool,
    minimum_free_space_bytes: int,
) -> dict[str, object]:
    if not rights_acknowledged:
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_RIGHTS_ACK", "Acknowledge the suite rights and attribution before installation")
    validated = validate_research_suite(Path(path))
    descriptor = validated.descriptor
    components = dict(descriptor["components"])  # type: ignore[arg-type]
    suite_id = str(descriptor.get("suite_id") or "")
    state_root = Path(packs_root).resolve().parent
    installation_path = state_root / "research-suites" / suite_id / "installation.json"
    if installation_path.is_file():
        existing = json.loads(installation_path.read_text(encoding="utf-8"))
        if existing.get("suite_sha256") == validated.suite_sha256:
            return {**existing, "idempotent": True}
        raise ResearchSuiteError("VALUE_RESEARCH_SUITE_COLLISION", "That research-suite ID already exists with different bytes")
    staging_root = state_root / "research-suite-staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="suite-", dir=staging_root)).resolve()
    base_archive = staging / "base.zip"
    network_archive = staging / "network.zip"
    templates_path = staging / STUDIES_MEMBER
    newly_created: list[tuple[Path, Path]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for member, target in ((BASE_MEMBER, base_archive), (NETWORK_MEMBER, network_archive), (STUDIES_MEMBER, templates_path)):
                with archive.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        base = validate_data_bundle(base_archive)
        network = validate_data_bundle(network_archive)
        base_id = str(base.descriptor["pack_id"])
        network_id = str(network.descriptor["pack_id"])
        if base_id != dict(components["base"])["pack_id"] or network_id != dict(components["network"])["pack_id"]:
            raise ResearchSuiteError("VALUE_RESEARCH_SUITE_COMPONENTS", "Component pack IDs do not match the suite descriptor")
        required = base.uncompressed_bytes + network.uncompressed_bytes + max(0, minimum_free_space_bytes)
        available = shutil.disk_usage(state_root).free
        if available < required:
            raise ResearchSuiteError("VALUE_RESEARCH_SUITE_DISK_HEADROOM", f"Research-suite installation needs {required} free bytes; {available} are available")
        templates = _read_json_bytes(templates_path.read_bytes(), STUDIES_MEMBER)
        studies = templates.get("studies")
        if templates.get("schema_version") != "value.study-templates/v1" or not isinstance(studies, list) or len(studies) != 2:
            raise ResearchSuiteError("VALUE_RESEARCH_SUITE_STUDIES", "Research suite must declare exactly two Study templates")
        for item in studies:
            if not isinstance(item, Mapping) or item.get("data_pack_id") != base_id:
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_STUDIES", "Study template does not reference the suite base pack")
            configuration = dict(item.get("market_configuration") or {})
            modules = dict(item.get("modules") or {})
            if modules.get("balancing") == "value-zonal-redispatch-balancing" and configuration.get("network_pack_id") != network_id:
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_STUDIES", "Zonal Study template does not reference the suite Network Pack")

        base_target = Path(packs_root).resolve() / base_id
        network_target = Path(network_packs_root).resolve() / network_id
        base_existed = base_target.exists()
        network_existed = network_target.exists()
        base_installation = install_data_bundle(
            base_archive,
            packs_root=Path(packs_root),
            dataset_slots=base_dataset_slots,
            rights_acknowledged=True,
            minimum_free_space_bytes=0,
        )
        if not base_existed:
            newly_created.append((base_target, Path(packs_root)))
        network_installation = install_data_bundle(
            network_archive,
            packs_root=Path(network_packs_root),
            dataset_slots=network_dataset_slots,
            rights_acknowledged=True,
            minimum_free_space_bytes=0,
        )
        if not network_existed:
            newly_created.append((network_target, Path(network_packs_root)))

        base_manifest = json.loads((base_target / "manifest.json").read_text(encoding="utf-8"))
        study_ids: list[str] = []
        for raw in studies:
            candidate = dict(raw)
            validation = validate_project(candidate)
            if not validation.get("valid"):
                errors = validation.get("errors") or ["Study template failed validation"]
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_STUDIES", str(errors[0]))
            candidate = dict(validation.get("normalised_project") or candidate)
            study_id = str(candidate.get("id") or "")
            if not study_id:
                raise ResearchSuiteError("VALUE_RESEARCH_SUITE_STUDIES", "Study template has no ID")
            project_dir = Path(projects_root).resolve() / study_id
            manifest = revision_manifest(candidate, base_manifest)
            expected = attach_revision_identity(candidate, registry, manifest)
            current_path = project_dir / "project.json"
            if current_path.is_file():
                current = json.loads(current_path.read_text(encoding="utf-8"))
                if current.get("revision_sha256") != expected.get("revision_sha256"):
                    _existing_suite_study(current, candidate, study_id, registry, manifest)
            else:
                save_project_revision(project_dir, candidate, registry, manifest)
                newly_created.append((project_dir, Path(projects_root)))
            study_ids.append(study_id)

        record = {
            "schema_version": INSTALLATION_SCHEMA,
            "suite_id": suite_id,
            "suite_sha256": validated.suite_sha256,
            "suite_bytes": validated.suite_bytes,
            "component_pack_ids": [base_id, network_id],
            "component_bundle_sha256": [base_installation["bundle_sha256"], network_installation["bundle_sha256"]],
            "study_ids": study_ids,
            "rights_files": list(RIGHTS_MEMBERS),
            "installation_boundary": "local_data_and_declarative_studies_no_executable_content",
            "idempotent": False,
        }
        installation_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = installation_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, installation_path)
        return record
    except ResearchSuiteError:
        for target, parent in reversed(newly_created):
            _remove_new_directory(target, parent)
        raise
    except (DataBundleError, OSError, ValueError, KeyError, TypeError) as exc:
        for target, parent in reversed(newly_created):
            _remove_new_directory(target, parent)
        raise ResearchSuiteError(getattr(exc, "code", "VALUE_RESEARCH_SUITE_INSTALL"), str(exc)) from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
