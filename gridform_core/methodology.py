"""Methodology profiles: the catalogue, its resolver and the combination whitelist.

Plan X0 3.4 (S8) with decisions Q1, Q2, Q3, Q12 and Q14.  A *profile* is a
named methodology: the frozen doctoral reproduction
(``doctoral-lineage-0.6.0a2``) or the corrected default (``value-corrected``).
A *correction* is one entry of ``data/methodology/corrections/<pkg>.json``:
``universal`` corrections apply to every profile, ``profile_gated`` ones only
to profiles that enable them.

Rules (P0_CONVENTIONS section 10, C15):

* Rule sets never compare profile ids.  They ask
  :meth:`ResolvedMethodology.enabled` for a correction id.
* The default profile and the allowed values of the ``methodology.profile``
  parameter come only from ``profiles.json``.
* The combination whitelist (supported modules, extensions, data packs and the
  external-code policy) is checked in one place, :func:`combination_violations`,
  and reported with the single code ``VALUE_PROFILE_COMBINATION_UNSUPPORTED``
  and a sub-reason (C16).

This module has no import-time side effects beyond reading the packaged JSON
catalogue lazily; it imports nothing from the model.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from . import pack_source_identity
from .errors import PublicFailure, VALUEError

PROFILE_PARAMETER = "methodology.profile"
# The frozen thesis-lineage profile.  Only the reference routes (modular_run,
# reference_comparison) and tests name it; rule sets never compare profile ids
# (C15).  scripts/check_methodology_catalog.py rejects this literal elsewhere.
REFERENCE_PROFILE_ID = "doctoral-lineage-0.6.0a2"
COMBINATION_ERROR_CODE = "VALUE_PROFILE_COMBINATION_UNSUPPORTED"
CATALOGUE_ROOT = Path(__file__).resolve().parent / "data" / "methodology"
PROFILES_SCHEMA = "value.methodology-profiles/v1"
CORRECTIONS_SCHEMA = "value.methodology-corrections/v1"
RESOLVED_SCHEMA = "value.methodology/v1"
CORRECTION_ID_PATTERN = re.compile(r"^[a-z0-9]+(\.[a-z0-9-]+)+$")
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")
TRACKS = ("universal", "profile_gated")
SEVERITIES = ("info", "low", "medium", "high", "critical")
AFFECTS = ("trajectory", "accounting", "identity", "presentation")
APPLIES_WHEN_KEYS = ("modules_any", "modes_any", "data_packs_any", "engines_any")
EXTERNAL_CODE_POLICIES = ("allow", "refuse_when_enabled")
PUBLICATION_RULES = ("standard", "raw_invariants_must_pass")
PACK_CLASSES = ("scientific_reference", "teaching", "synthetic", "user_workspace")
SUB_REASONS = ("module", "extension", "data_pack", "external_code", "reference_path")

# Packs whose class is known without a manifest field (P0-5 "truth registry";
# P0-5 S3 owns the full data-method policy and extends this table).
# ``synthetic`` is never inferred from a manifest field (``country:
# SYNTHETIC`` is self-declared and survives a Data Pack copy): only the shipped
# contract packs listed here are synthetic.
KNOWN_PACK_CLASSES: Mapping[str, str] = {
    "value-uk-open-data-pack-v1": "scientific_reference",      # GBP1
    "value-uk-calendar-vx-trade001": "scientific_reference",   # R029
    # GBP1 public2: local registration only (decision A16-7); built by
    # scripts/build_value_uk_pack_revision.py, not published.
    "value-uk-open-data-pack-public2": "scientific_reference",
    "value-uk-1000twh-reproduction": "scientific_reference",
    "value-synthetic-contract-pack-v1": "synthetic",           # thesis-era contract pack
}

# Fields of a profile covered by its definition hash (the frozen-profile
# tripwire, tests/test_methodology_profiles.py).  supported_data_packs entries
# enter it through their semantic fields only (_PACK_ENTRY_SEMANTIC_FIELDS);
# label and pin_note are presentation.
_PACK_ENTRY_SEMANTIC_FIELDS = ("id", "pack_class", "manifest_sha256")
_DEFINITION_FIELDS = (
    "id", "version", "frozen", "gated_corrections", "supported_modules",
    "supported_extensions", "supported_data_packs", "external_code_policy",
    "reference_configuration", "result_publication",
)


class MethodologyCatalogError(ValueError):
    """The packaged methodology catalogue is malformed (a build error)."""


# The methodology errors are VALUEErrors so a Run that fails on them (the
# run-entry backstop in the worker) carries their own code, category and
# public message instead of a generic contract/runtime failure (plan X0 3.4).
METHODOLOGY_ERROR_CATEGORY = "methodology"


class UnknownProfileError(VALUEError, ValueError):
    code = "VALUE_PROFILE_UNKNOWN"
    category = METHODOLOGY_ERROR_CATEGORY
    public_message = "The Study selects a methodology profile this VALUE does not know."


class UnknownCorrectionError(KeyError):
    """A rule set asked for a correction id that is not in the catalogue."""


class ProfileCombinationError(VALUEError, ValueError):
    """The selected profile does not support this module/data/code combination."""

    code = COMBINATION_ERROR_CODE
    category = METHODOLOGY_ERROR_CATEGORY
    public_message = (
        "The selected methodology profile does not support this combination of modules, "
        "extensions, data packs or enabled external code."
    )

    def __init__(self, profile_id: str, violations: Sequence[Mapping[str, object]]):
        self.profile_id = profile_id
        self.violations = [dict(item) for item in violations]
        self.sub_reasons = sorted({str(item["sub_reason"]) for item in self.violations})
        detail = "; ".join(str(item["message"]) for item in self.violations)
        super().__init__(
            f"Methodology profile {profile_id} does not support this combination "
            f"({', '.join(self.sub_reasons)}): {detail}"
        )

    def public_failure(self) -> PublicFailure:
        """The public message names the sub-reasons (never paths or digests)."""

        return PublicFailure(
            self.code, self.category,
            f"{self.public_message} Sub-reason: {', '.join(self.sub_reasons) or 'unspecified'}. "
            "Open the diagnostic artifact for details.",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "error_code": self.code,
            "profile_id": self.profile_id,
            "sub_reasons": list(self.sub_reasons),
            "violations": [dict(item) for item in self.violations],
        }


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Correction:
    id: str
    package: str
    findings: tuple[str, ...]
    track: str
    scope: str
    affects: tuple[str, ...]
    applies_when: Mapping[str, tuple[str, ...]]
    advisory: Mapping[str, object] | None
    trigger_fixture: Mapping[str, object] | None
    introduced_in: str
    deviation_signature: Mapping[str, object] | None
    description: str
    record: Mapping[str, object] = field(repr=False, compare=False, default_factory=dict)

    @property
    def gated(self) -> bool:
        return self.track == "profile_gated"

    def semantic_identity(self) -> dict[str, object]:
        """The fields of a correction that belong to the method identity.

        Description, advisory text, applies_when and deviation_signature are
        presentation: editing them must not turn every saved Study or Run into
        a method change (applied_corrections_sha256 covers only these fields).
        """

        return {"id": self.id, "track": self.track, "scope": self.scope, "affects": list(self.affects)}


@dataclass(frozen=True)
class Profile:
    id: str
    version: str
    label: str
    note: str
    frozen: bool
    default: bool
    gated_corrections: object  # "*" or tuple of ids
    supported_modules: object  # "*" or {module_id: (scientific_version, ...)}
    supported_extensions: object  # "*" or tuple of ids
    supported_data_packs: object  # "*" or tuple of entries
    external_code_policy: str
    reference_configuration: Mapping[str, Mapping[str, object]]
    result_publication: Mapping[str, object]
    golden_family: str
    record: Mapping[str, object] = field(repr=False, compare=False, default_factory=dict)

    def definition(self) -> dict[str, object]:
        """The method-defining fields (what ``profile_definition_sha256`` covers).

        Data-pack entries are reduced to id, pack_class and the (sorted) pins
        and sorted, so editing an entry's label or pin_note, or reordering
        entries or pins, does not change the definition (and so does not turn
        every saved Study of the profile into a method change, Q13).
        """

        value = {key: copy.deepcopy(self.record[key]) for key in _DEFINITION_FIELDS}
        packs = value["supported_data_packs"]
        if packs != "*":
            entries = []
            for entry in packs:  # type: ignore[union-attr]
                semantic = {key: copy.deepcopy(entry[key]) for key in _PACK_ENTRY_SEMANTIC_FIELDS}
                if semantic["manifest_sha256"] != "*":
                    semantic["manifest_sha256"] = sorted(semantic["manifest_sha256"])
                entries.append(semantic)
            value["supported_data_packs"] = sorted(entries, key=_sha256_json)
        return value

    @property
    def definition_sha256(self) -> str:
        return _sha256_json(self.definition())

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id, "version": self.version, "label": self.label, "note": self.note,
            "frozen": self.frozen, "default": self.default,
            "profile_definition_sha256": self.definition_sha256,
            "gated_corrections": copy.deepcopy(self.record["gated_corrections"]),
            "supported_modules": copy.deepcopy(self.record["supported_modules"]),
            "supported_extensions": copy.deepcopy(self.record["supported_extensions"]),
            "supported_data_packs": copy.deepcopy(self.record["supported_data_packs"]),
            "external_code_policy": self.external_code_policy,
            "reference_configuration": copy.deepcopy(self.record["reference_configuration"]),
            "result_publication": copy.deepcopy(self.record["result_publication"]),
            "golden_family": self.golden_family,
        }


@dataclass(frozen=True)
class Catalogue:
    profiles: Mapping[str, Profile]
    corrections: Mapping[str, Correction]
    default_profile_id: str
    catalogue_sha256: str

    def profile(self, profile_id: str) -> Profile:
        try:
            return self.profiles[profile_id]
        except KeyError:
            raise UnknownProfileError(
                f"Unknown methodology profile {profile_id!r}; known profiles: "
                + ", ".join(sorted(self.profiles))
            ) from None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MethodologyCatalogError(message)


def _string_list(value: object, where: str) -> tuple[str, ...]:
    _require(isinstance(value, list) and all(isinstance(item, str) and item for item in value),
             f"{where} must be a list of non-empty strings")
    return tuple(value)  # type: ignore[arg-type]


def _parse_correction(row: object, package: str, where: str) -> Correction:
    _require(isinstance(row, Mapping), f"{where} must be an object")
    assert isinstance(row, Mapping)
    required = ("id", "package", "findings", "track", "scope", "affects", "applies_when",
                "advisory", "trigger_fixture", "introduced_in")
    missing = [key for key in required if key not in row]
    _require(not missing, f"{where} lacks {', '.join(missing)}")
    correction_id = row["id"]
    _require(isinstance(correction_id, str) and bool(CORRECTION_ID_PATTERN.match(correction_id)),
             f"{where}: correction id {correction_id!r} does not match {CORRECTION_ID_PATTERN.pattern}")
    _require(correction_id.split(".", 1)[0] == package and row["package"] == package,
             f"{where}: {correction_id} must belong to package {package}")
    _require(row["track"] in TRACKS, f"{where}: track must be one of {TRACKS}")
    affects = _string_list(row["affects"], f"{where}.affects")
    _require(all(item in AFFECTS for item in affects), f"{where}: affects must use {AFFECTS}")
    applies_when = row["applies_when"]
    _require(isinstance(applies_when, Mapping), f"{where}: applies_when must be an object")
    unknown = sorted(set(applies_when).difference(APPLIES_WHEN_KEYS))  # type: ignore[arg-type]
    _require(not unknown, f"{where}: unknown applies_when keys {unknown}")
    predicates = {
        str(key): _string_list(value, f"{where}.applies_when.{key}")
        for key, value in applies_when.items()  # type: ignore[union-attr]
    }
    advisory = row["advisory"]
    if advisory is not None:
        _require(isinstance(advisory, Mapping), f"{where}: advisory must be null or an object")
        assert isinstance(advisory, Mapping)
        _require(advisory.get("severity") in SEVERITIES, f"{where}: advisory.severity must be one of {SEVERITIES}")
        _require(isinstance(advisory.get("title"), str) and bool(advisory.get("title")), f"{where}: advisory.title is required")
        _require(isinstance(advisory.get("summary"), str) and bool(advisory.get("summary")), f"{where}: advisory.summary is required")
        _string_list(advisory.get("affected_metrics", []), f"{where}.advisory.affected_metrics")
    fixture = row["trigger_fixture"]
    if row["track"] == "profile_gated":
        _require(isinstance(fixture, Mapping) and isinstance(fixture.get("test"), str) and bool(fixture.get("test")),
                 f"{where}: profile_gated correction {correction_id} needs trigger_fixture.test (plan X0 3.3)")
    else:
        _require(fixture is None or isinstance(fixture, Mapping), f"{where}: trigger_fixture must be null or an object")
    signature = row.get("deviation_signature")
    _require(signature is None or isinstance(signature, Mapping), f"{where}: deviation_signature must be null or an object")
    return Correction(
        id=correction_id, package=package,
        findings=_string_list(row["findings"], f"{where}.findings") if row["findings"] else (),
        track=str(row["track"]), scope=str(row["scope"]), affects=affects,
        applies_when=predicates, advisory=copy.deepcopy(advisory), trigger_fixture=copy.deepcopy(fixture),
        introduced_in=str(row["introduced_in"]), deviation_signature=copy.deepcopy(signature),
        description=str(row.get("description") or ""), record=copy.deepcopy(dict(row)),
    )


def _parse_profile(row: object, corrections: Mapping[str, Correction], where: str) -> Profile:
    _require(isinstance(row, Mapping), f"{where} must be an object")
    assert isinstance(row, Mapping)
    required = ("id", "version", "label", "note", "frozen", "default", "gated_corrections",
                "supported_modules", "supported_extensions", "supported_data_packs",
                "external_code_policy", "reference_configuration", "result_publication", "golden_family")
    missing = [key for key in required if key not in row]
    _require(not missing, f"{where} lacks {', '.join(missing)}")
    profile_id = row["id"]
    _require(isinstance(profile_id, str) and bool(PROFILE_ID_PATTERN.match(profile_id)), f"{where}: invalid profile id")
    for key in ("version", "label", "note", "golden_family"):
        _require(isinstance(row[key], str) and bool(row[key]), f"{where}: {key} must be a non-empty string")
    _require(isinstance(row["frozen"], bool) and isinstance(row["default"], bool), f"{where}: frozen/default must be booleans")
    gated = row["gated_corrections"]
    if gated != "*":
        gated_ids = _string_list(gated, f"{where}.gated_corrections")
        for correction_id in gated_ids:
            _require(correction_id in corrections, f"{where}: unknown gated correction {correction_id}")
            _require(corrections[correction_id].gated, f"{where}: {correction_id} is universal, not profile_gated")
        gated = tuple(sorted(gated_ids))
    _require(not (row["frozen"] and gated == "*"), f"{where}: a frozen profile cannot enable every gated correction")
    modules = row["supported_modules"]
    if modules != "*":
        _require(isinstance(modules, Mapping) and bool(modules), f"{where}: supported_modules must be \"*\" or an object")
        modules = {str(key): _string_list(value, f"{where}.supported_modules.{key}") for key, value in modules.items()}  # type: ignore[union-attr]
    extensions = row["supported_extensions"]
    if extensions != "*":
        extensions = _string_list(extensions, f"{where}.supported_extensions") if extensions else ()
    packs = row["supported_data_packs"]
    if packs != "*":
        _require(isinstance(packs, list) and bool(packs), f"{where}: supported_data_packs must be \"*\" or a list")
        parsed = []
        for index, entry in enumerate(packs):  # type: ignore[arg-type]
            _require(isinstance(entry, Mapping) and isinstance(entry.get("id"), str)
                     and entry.get("pack_class") in PACK_CLASSES,
                     f"{where}.supported_data_packs[{index}] needs id and pack_class in {PACK_CLASSES}")
            sha = entry.get("manifest_sha256")
            _require(sha == "*" or (isinstance(sha, list) and all(isinstance(item, str) and len(item) == 64 for item in sha)),
                     f"{where}.supported_data_packs[{index}].manifest_sha256 must be \"*\" or a list of sha256")
            _require(not (row.get("frozen") is True and entry["id"] == "*"),
                     f"{where}.supported_data_packs[{index}]: a frozen profile names each data pack (no \"*\" id)")
            parsed.append(copy.deepcopy(dict(entry)))
        packs = tuple(parsed)
    _require(row["external_code_policy"] in EXTERNAL_CODE_POLICIES, f"{where}: external_code_policy must be one of {EXTERNAL_CODE_POLICIES}")
    reference = row["reference_configuration"]
    _require(isinstance(reference, Mapping) and set(reference) == {"modules", "parameters"}
             and all(isinstance(reference[key], Mapping) for key in ("modules", "parameters")),
             f"{where}: reference_configuration must be {{modules: {{}}, parameters: {{}}}}")
    publication = row["result_publication"]
    _require(isinstance(publication, Mapping) and publication.get("rule") in PUBLICATION_RULES,
             f"{where}: result_publication.rule must be one of {PUBLICATION_RULES}")
    return Profile(
        id=profile_id, version=str(row["version"]), label=str(row["label"]), note=str(row["note"]),
        frozen=bool(row["frozen"]), default=bool(row["default"]), gated_corrections=gated,
        supported_modules=modules, supported_extensions=extensions, supported_data_packs=packs,
        external_code_policy=str(row["external_code_policy"]),
        reference_configuration=copy.deepcopy(dict(reference)),  # type: ignore[arg-type]
        result_publication=copy.deepcopy(dict(publication)),  # type: ignore[arg-type]
        golden_family=str(row["golden_family"]), record=copy.deepcopy(dict(row)),
    )


def load_catalogue_from(root: Path) -> Catalogue:
    """Parse and validate a catalogue directory (tests use temporary copies)."""

    corrections: dict[str, Correction] = {}
    raw_corrections: dict[str, object] = {}
    correction_dir = root / "corrections"
    for path in sorted(correction_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        where = f"corrections/{path.name}"
        _require(isinstance(payload, Mapping) and payload.get("schema_version") == CORRECTIONS_SCHEMA,
                 f"{where}: schema_version must be {CORRECTIONS_SCHEMA}")
        package = payload.get("package")
        _require(isinstance(package, str) and package == path.stem and "-" not in package,
                 f"{where}: package must equal the file name ({path.stem}) and contain no hyphen")
        rows = payload.get("corrections")
        _require(isinstance(rows, list), f"{where}: corrections must be a list")
        for index, row in enumerate(rows):  # type: ignore[arg-type]
            correction = _parse_correction(row, str(package), f"{where}[{index}]")
            _require(correction.id not in corrections, f"{where}: duplicate correction id {correction.id}")
            corrections[correction.id] = correction
        raw_corrections[path.name] = payload
    payload = json.loads((root / "profiles.json").read_text(encoding="utf-8"))
    _require(isinstance(payload, Mapping) and payload.get("schema_version") == PROFILES_SCHEMA,
             f"profiles.json: schema_version must be {PROFILES_SCHEMA}")
    rows = payload.get("profiles")
    _require(isinstance(rows, list) and bool(rows), "profiles.json: profiles must be a non-empty list")
    profiles: dict[str, Profile] = {}
    for index, row in enumerate(rows):  # type: ignore[arg-type]
        profile = _parse_profile(row, corrections, f"profiles.json[{index}]")
        _require(profile.id not in profiles, f"profiles.json: duplicate profile id {profile.id}")
        profiles[profile.id] = profile
    defaults = [profile.id for profile in profiles.values() if profile.default]
    _require(len(defaults) == 1, f"profiles.json: exactly one default profile is required, found {defaults}")
    _require(not profiles[defaults[0]].frozen, "profiles.json: the default profile cannot be frozen")
    return Catalogue(
        profiles=profiles, corrections=corrections, default_profile_id=defaults[0],
        catalogue_sha256=_sha256_json({"profiles": payload, "corrections": raw_corrections}),
    )


@lru_cache(maxsize=1)
def load_catalogue() -> Catalogue:
    return load_catalogue_from(CATALOGUE_ROOT)


def default_profile_id() -> str:
    return load_catalogue().default_profile_id


def profile_ids() -> tuple[str, ...]:
    """Profile ids in catalogue order (the parameter's allowed values)."""

    return tuple(load_catalogue().profiles)


def frozen_profile_ids() -> tuple[str, ...]:
    return tuple(profile.id for profile in load_catalogue().profiles.values() if profile.frozen)


@dataclass(frozen=True)
class ResolvedMethodology:
    """The methodology a run executes under.  Immutable; hashable identity."""

    profile_id: str
    profile_version: str
    label: str
    note: str
    frozen: bool
    profile_definition_sha256: str
    applied_correction_ids: tuple[str, ...]
    applied_corrections_sha256: str
    catalogue_sha256: str
    external_code_policy: str
    reference_configuration: Mapping[str, Mapping[str, object]]
    result_publication: Mapping[str, object]
    golden_family: str
    _known_correction_ids: frozenset[str] = field(repr=False, default=frozenset())
    _applied_records: tuple[Mapping[str, object], ...] = field(repr=False, default=())

    def applied_correction_records(self) -> list[dict[str, object]]:
        """Semantic records of the applied corrections (what applied_corrections_sha256 covers)."""

        return [copy.deepcopy(dict(item)) for item in self._applied_records]

    def enabled(self, correction_id: str) -> bool:
        """Is this correction in force for the run?  Unknown ids raise (typos fail closed)."""

        if correction_id not in self._known_correction_ids:
            raise UnknownCorrectionError(
                f"Correction {correction_id!r} is not in the methodology catalogue"
            )
        return correction_id in self.applied_correction_ids

    def identity(self) -> dict[str, str]:
        """The method-dimension identity (comparison_identity, plan X0 3.5)."""

        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_definition_sha256": self.profile_definition_sha256,
            "applied_corrections_sha256": self.applied_corrections_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": RESOLVED_SCHEMA,
            **self.identity(),
            "label": self.label,
            "note": self.note,
            "frozen": self.frozen,
            "applied_correction_ids": list(self.applied_correction_ids),
            "catalogue_sha256": self.catalogue_sha256,
            "external_code_policy": self.external_code_policy,
            "reference_configuration": copy.deepcopy(dict(self.reference_configuration)),
            "result_publication": copy.deepcopy(dict(self.result_publication)),
            "golden_family": self.golden_family,
        }


def _applied(profile: Profile, catalogue: Catalogue) -> tuple[Correction, ...]:
    rows = []
    for correction in catalogue.corrections.values():
        if not correction.gated:
            rows.append(correction)
        elif profile.gated_corrections == "*" or correction.id in profile.gated_corrections:  # type: ignore[operator]
            rows.append(correction)
    return tuple(sorted(rows, key=lambda item: item.id))


def resolve_methodology(profile_id: str | None = None, *, catalogue: Catalogue | None = None) -> ResolvedMethodology:
    """Resolve a profile id (``None`` = the catalogue default)."""

    catalogue = catalogue or load_catalogue()
    profile = catalogue.profile(profile_id or catalogue.default_profile_id)
    applied = _applied(profile, catalogue)
    return ResolvedMethodology(
        profile_id=profile.id,
        profile_version=profile.version,
        label=profile.label,
        note=profile.note,
        frozen=profile.frozen,
        profile_definition_sha256=profile.definition_sha256,
        applied_correction_ids=tuple(item.id for item in applied),
        applied_corrections_sha256=_sha256_json([item.semantic_identity() for item in applied]),
        catalogue_sha256=catalogue.catalogue_sha256,
        external_code_policy=profile.external_code_policy,
        reference_configuration=copy.deepcopy(dict(profile.reference_configuration)),
        result_publication=copy.deepcopy(dict(profile.result_publication)),
        golden_family=profile.golden_family,
        _known_correction_ids=frozenset(catalogue.corrections),
        _applied_records=tuple(item.semantic_identity() for item in applied),
    )


def profile_of_parameters(parameters: Mapping[str, object] | None) -> str:
    """The profile id a Study's parameters select (absent = default)."""

    value = dict(parameters or {}).get(PROFILE_PARAMETER)
    return str(value) if value else default_profile_id()


def resolve_project_methodology(project: Mapping[str, object]) -> ResolvedMethodology:
    return resolve_methodology(profile_of_parameters(
        project.get("parameters") or project.get("parameter_overrides") or {}  # type: ignore[arg-type]
    ))


def with_profile(project: Mapping[str, object], profile_id: str) -> dict[str, object]:
    """A copy of ``project`` pinned to ``profile_id`` (test and preset helper).

    Tests that encode 35aadb3 numbers pin the frozen profile with
    ``with_profile(project, "doctoral-lineage-0.6.0a2")`` so a later change of
    the default cannot silently move them (P0_CONVENTIONS section 10).
    """

    load_catalogue().profile(profile_id)
    result = copy.deepcopy(dict(project))
    key = "parameters" if "parameters" in result or "parameter_overrides" not in result else "parameter_overrides"
    parameters = dict(result.get(key) or {})  # type: ignore[arg-type]
    parameters[PROFILE_PARAMETER] = profile_id
    result[key] = parameters
    return result


def apply_reference_preset(project: Mapping[str, object], profile_id: str) -> dict[str, object]:
    """Pin the profile and write its reference configuration explicitly (Q3)."""

    result = with_profile(project, profile_id)
    reference = load_catalogue().profile(profile_id).reference_configuration
    modules = dict(result.get("modules") or {})  # type: ignore[arg-type]
    modules.update(dict(reference.get("modules") or {}))
    result["modules"] = modules
    key = "parameters" if "parameters" in result else "parameter_overrides"
    parameters = dict(result.get(key) or {})  # type: ignore[arg-type]
    parameters.update(dict(reference.get("parameters") or {}))
    result[key] = parameters
    return result


def reference_deviations(
    methodology: ResolvedMethodology,
    *,
    modules: Mapping[str, str],
    scientific_parameters: Mapping[str, object],
) -> list[dict[str, object]]:
    """Recorded (not refused) differences from the profile's reference preset (Q3)."""

    rows: list[dict[str, object]] = []
    reference = methodology.reference_configuration
    for slot, expected in sorted(dict(reference.get("modules") or {}).items()):
        actual = modules.get(slot)
        if actual != expected:
            rows.append({"kind": "module", "key": slot, "reference": expected, "actual": actual})
    for key, expected in sorted(dict(reference.get("parameters") or {}).items()):
        actual = scientific_parameters.get(key)
        if actual != expected:
            rows.append({"kind": "parameter", "key": key, "reference": expected, "actual": actual})
    return rows


# --- data packs -------------------------------------------------------------

def _inferred_pack_class(manifest: Mapping[str, object]) -> str:
    known = KNOWN_PACK_CLASSES.get(str(manifest.get("id") or ""))
    if known:
        return known
    if manifest.get("teaching_only") is True:
        return "teaching"
    return "user_workspace"


def classify_data_pack(manifest: Mapping[str, object]) -> str:
    """pack_class from verifiable facts: known registry -> teaching_only -> user_workspace.

    A self-declared ``pack_class`` is never trusted on its own (otherwise a
    real GB pack could whitelist itself as synthetic for the frozen profile):
    it is accepted only when it equals the inferred class; a conflicting
    declaration makes the pack ``user_workspace``, the strictest class.
    P0-5 S3 takes over the data-method policy.
    """

    inferred = _inferred_pack_class(manifest)
    declared = manifest.get("pack_class")
    if declared is None or declared == inferred:
        return inferred
    return "user_workspace"


def whitelist_manifest(manifest: Mapping[str, object]) -> Mapping[str, object]:
    """The manifest the whitelist identifies (``pack_source_identity.resolve_pack_identity``).

    A Run executes on its input snapshot, whose pack manifest ``run_snapshot``
    rewrote; a recovered Study runs on a pack recovery rewrote.  The whitelist
    identifies such a copy by the verified manifest it was made from;
    otherwise by the manifest itself (a frozen copy no profile pins).
    """

    return pack_source_identity.resolve_pack_identity(manifest).manifest


def manifest_sha256_candidates(manifest: Mapping[str, object], manifest_bytes: bytes | None = None) -> set[str]:
    """File-byte and canonical-JSON sha256 of the identified manifest (either may be whitelisted).

    The same two candidates for a source pack (given its file bytes) and for
    its frozen copy or recovered pack (whose verified source record carries
    the source file bytes), so preflight and the worker agree.
    """

    return set(pack_source_identity.resolve_pack_identity(manifest, manifest_bytes).sha256_candidates)


def read_pack_manifest(pack_root: Path) -> tuple[dict[str, object], bytes]:
    raw = (pack_root / "manifest.json").read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Data Pack manifest is not an object: {pack_root}")
    return payload, raw


def _pack_supported(profile: Profile, identity: "pack_source_identity.PackIdentity") -> bool:
    if profile.supported_data_packs == "*":
        return True
    manifest = identity.manifest
    pack_id = str(manifest.get("id") or "")
    pack_class = classify_data_pack(manifest)
    for entry in profile.supported_data_packs:  # type: ignore[union-attr]
        if entry["id"] not in {"*", pack_id} or entry["pack_class"] != pack_class:
            continue
        if entry["manifest_sha256"] == "*" or identity.sha256_candidates.intersection(entry["manifest_sha256"]):
            return True
    return False


_UNVERIFIED_PACK_NOTES = {
    "snapshot": " (its run-input snapshot carries no verifiable source manifest identity)",
    "recovery": " (its recovered inputs carry no verifiable source manifest identity, or differ from that source)",
    "recovery_id_keyed": (" (its recovered inputs hold the verified content of a pack whose id selects model behaviour "
                          "(VALUE-UK nuclear policy, doctoral site weather); model behaviour keys on the pack id, so "
                          "the recovered copy under a new id does not behave as that pack)"),
}


# --- external code ----------------------------------------------------------

def external_code_entries(registry: object) -> list[str]:
    """Enabled local (non built-in) modules and extensions, from P0-2's evidence.

    The worker imports every enabled external implementation in process, so
    the frozen profile refuses to run while any is enabled, selected or not
    (P0-2 Q7 / C16).  Quarantined entries are not imported and not listed.
    """

    from .module_quarantine import external_code_evidence

    evidence = external_code_evidence(registry)
    return (
        [f"module:{item}" for item in evidence["enabled_external_modules"]]  # type: ignore[union-attr]
        + [f"extension:{item}" for item in evidence["enabled_external_extensions"]]  # type: ignore[union-attr]
    )


# --- combination whitelist --------------------------------------------------

def _violation(sub_reason: str, message: str, **detail: object) -> dict[str, object]:
    return {"sub_reason": sub_reason, "message": message, **detail}


def module_supported(profile_id: str, module_id: str, scientific_version: str | None) -> tuple[bool, str | None]:
    """Is one module (id, scientific_version) admissible under the profile?  Reason when not."""

    profile = load_catalogue().profile(profile_id)
    if profile.supported_modules == "*":
        return True, None
    accepted = profile.supported_modules.get(module_id)  # type: ignore[union-attr]
    if accepted is None:
        return False, f"{module_id} is not a thesis-lineage module of {profile.label}"
    if scientific_version not in accepted:
        return False, (f"{module_id} scientific version {scientific_version} is not the frozen "
                       f"lineage version ({', '.join(accepted)})")
    return True, None


def extension_supported(profile_id: str, extension_id: str) -> tuple[bool, str | None]:
    profile = load_catalogue().profile(profile_id)
    if profile.supported_extensions == "*" or extension_id in profile.supported_extensions:  # type: ignore[operator]
        return True, None
    return False, f"extension {extension_id} is not part of {profile.label}"


def combination_violations(
    methodology: ResolvedMethodology | str,
    *,
    modules: Mapping[str, tuple[str, str | None]] | None = None,
    extensions: Iterable[str] = (),
    data_packs: Sequence[tuple[Mapping[str, object], bytes | None]] = (),
    external_code: Sequence[str] = (),
) -> list[dict[str, object]]:
    """All whitelist violations; empty when the combination is supported.

    ``modules`` maps slot -> (module id, scientific_version); ``data_packs`` is
    a list of (manifest, manifest file bytes or None) for the base pack and any
    network overlay; ``external_code`` lists enabled non-built-in entries.
    """

    profile_id = methodology if isinstance(methodology, str) else methodology.profile_id
    profile = load_catalogue().profile(profile_id)
    rows: list[dict[str, object]] = []
    for slot, (module_id, scientific_version) in sorted(dict(modules or {}).items()):
        ok, reason = module_supported(profile.id, module_id, scientific_version)
        if not ok:
            rows.append(_violation("module", f"slot {slot}: {reason}", slot=slot, module_id=module_id,
                                   scientific_version=scientific_version))
    for extension_id in sorted(set(extensions)):
        ok, reason = extension_supported(profile.id, extension_id)
        if not ok:
            rows.append(_violation("extension", str(reason), extension_id=extension_id))
    for manifest, raw in data_packs:
        identity = pack_source_identity.resolve_pack_identity(manifest, raw)
        if not _pack_supported(profile, identity):
            pack_class = classify_data_pack(identity.manifest)
            rows.append(_violation(
                "data_pack",
                f"data pack {manifest.get('id')} ({pack_class}) is not a thesis-era pack of {profile.label}"
                + _UNVERIFIED_PACK_NOTES.get(identity.unverified or "", ""),
                data_pack_id=manifest.get("id"), pack_class=pack_class,
                manifest_sha256=sorted(identity.sha256_candidates),
                identified_data_pack_id=identity.manifest.get("id"), identity_chain=list(identity.chain),
            ))
    if profile.external_code_policy == "refuse_when_enabled" and external_code:
        rows.append(_violation(
            "external_code",
            f"{profile.label} does not run while external code is enabled: {', '.join(external_code)}",
            entries=list(external_code),
        ))
    return rows


def assert_combination(methodology: ResolvedMethodology | str, **kwargs: Any) -> None:
    violations = combination_violations(methodology, **kwargs)
    if violations:
        profile_id = methodology if isinstance(methodology, str) else methodology.profile_id
        raise ProfileCombinationError(profile_id, violations)


def catalogue_payload() -> dict[str, object]:
    """Public API payload: profiles, the default and the correction ids."""

    catalogue = load_catalogue()
    return {
        "schema_version": "value.methodology-catalogue/v1",
        "default_profile_id": catalogue.default_profile_id,
        "catalogue_sha256": catalogue.catalogue_sha256,
        "parameter_id": PROFILE_PARAMETER,
        "profiles": [profile.public_dict() for profile in catalogue.profiles.values()],
        "corrections": [
            {
                "id": item.id, "package": item.package, "track": item.track, "findings": list(item.findings),
                "scope": item.scope, "affects": list(item.affects), "introduced_in": item.introduced_in,
            }
            for item in sorted(catalogue.corrections.values(), key=lambda row: row.id)
        ],
    }


def pack_entry(pack_root: Path | None, manifest: Mapping[str, object] | None = None) -> tuple[Mapping[str, object], bytes | None] | None:
    """(manifest, manifest file bytes) for the whitelist; bytes None when unreadable."""

    if pack_root is not None:
        try:
            payload, raw = read_pack_manifest(Path(pack_root))
            return payload, raw
        except (OSError, ValueError):
            pass
    return (dict(manifest), None) if manifest else None


def selection_combination_violations(
    methodology: ResolvedMethodology | str,
    *,
    registry: object,
    modules: Mapping[str, str],
    extensions: Iterable[str] = (),
    data_packs: Sequence[tuple[Mapping[str, object], bytes | None] | None] = (),
) -> list[dict[str, object]]:
    """Whitelist check of a Study selection resolved through ``registry``.

    The one check used by Study resolution, preflight and the run entry (C16).
    """

    module_rows: dict[str, tuple[str, str | None]] = {}
    for slot, module_id in dict(modules).items():
        scientific_version = None
        try:
            scientific_version = registry.manifest(str(module_id), expected_slot=str(slot)).scientific_version  # type: ignore[attr-defined]
        except (KeyError, ValueError, AttributeError):
            scientific_version = None
        module_rows[str(slot)] = (str(module_id), scientific_version)
    return combination_violations(
        methodology,
        modules=module_rows,
        extensions=tuple(str(item) for item in extensions),
        data_packs=[item for item in data_packs if item is not None],
        external_code=external_code_entries(registry),
    )


# --- activation (X0 S9) ----------------------------------------------------
#
# A run executes inside ``activate(m)``: the entry point (run_project_application,
# the reference routes) activates the resolved profile, and every PSM.run is
# ``@methodology_scoped``, so a PSM called directly (resource calibration,
# tests) activates the profile its input declares.  Switches are passed to
# kernel objects explicitly where possible; only deep functions that cannot take
# a parameter read ``current_methodology()``.  A future thread pool must run
# tasks under ``contextvars.copy_context()``.

_ACTIVE: ContextVar[ResolvedMethodology | None] = ContextVar("value_methodology", default=None)


class MethodologyNotActiveError(RuntimeError):
    """Code that needs the run's methodology ran outside an activated run."""

    code = "VALUE_METHODOLOGY_NOT_ACTIVE"


class MethodologyMismatchError(VALUEError, RuntimeError):
    """A nested call asked for a different methodology than the active one."""

    code = "VALUE_PROFILE_MISMATCH"
    category = METHODOLOGY_ERROR_CATEGORY
    public_message = "The run's methodology profile differs from the profile its inputs declare."


def active_methodology() -> ResolvedMethodology | None:
    return _ACTIVE.get()


def current_methodology() -> ResolvedMethodology:
    value = _ACTIVE.get()
    if value is None:
        raise MethodologyNotActiveError(
            "No methodology profile is active; run through run_project_application, "
            "a @methodology_scoped PSM.run, or methodology.profile_scope()."
        )
    return value


@contextmanager
def activate(methodology: ResolvedMethodology) -> Iterator[ResolvedMethodology]:
    """Make ``methodology`` current; re-entering with the same identity is a no-op."""

    current = _ACTIVE.get()
    if current is not None and current.identity() != methodology.identity():
        raise MethodologyMismatchError(
            f"Methodology {methodology.profile_id} requested inside an active "
            f"{current.profile_id} run"
        )
    token = _ACTIVE.set(methodology)
    try:
        yield methodology
    finally:
        _ACTIVE.reset(token)


def profile_scope(profile_id: str | None = None) -> Any:
    """``with profile_scope(REFERENCE_PROFILE_ID):`` - activate a profile by id (tests, reference routes)."""

    return activate(resolve_methodology(profile_id))


def _declared_profile(model_input: object) -> str | None:
    parameters = getattr(model_input, "parameters", None)
    if isinstance(parameters, Mapping):
        value = parameters.get(PROFILE_PARAMETER)
        return str(value) if value else None
    return None


def methodology_scoped(run: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator for ``PSM.run(self, model_input, ...)``.

    Inside an active run the input's declared profile (if any) must match the
    active one.  Outside a run the declared profile (absent = default) is
    activated for the duration of the call.
    """

    @functools.wraps(run)
    def wrapper(self: object, model_input: object, *args: Any, **kwargs: Any) -> Any:
        declared = _declared_profile(model_input)
        current = _ACTIVE.get()
        if current is not None:
            if declared is not None and declared != current.profile_id:
                raise MethodologyMismatchError(
                    f"{type(self).__name__}.run received methodology {declared} inside an active "
                    f"{current.profile_id} run"
                )
            return run(self, model_input, *args, **kwargs)
        with activate(resolve_methodology(declared)):
            return run(self, model_input, *args, **kwargs)

    wrapper.__methodology_scoped__ = True  # type: ignore[attr-defined]
    return wrapper


def methodology_record(project: Mapping[str, object]) -> dict[str, object]:
    """Status/provenance record of a Study's methodology; never raises."""

    try:
        return resolve_project_methodology(project).to_dict()
    except ValueError as exc:
        return {"schema_version": RESOLVED_SCHEMA, "status": "unresolved", "error": str(exc)}
