"""Reviewed CSV normalization into independent BASE packs; no model execution."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import time
from itertools import islice
from typing import Mapping, Sequence
import uuid
from datetime import datetime, timezone

from backend.data_pack_clone import SAFE_ID, guard_clone_upload
from gridform_core.data_adapters import AdapterSpec, ColumnRule, FX_CONVERSIONS, UNIT_FACTORS, execute_adapter, fx_factor
from gridform_core.data_contract_templates import CSV_TEMPLATES, runtime_supported_formats
from gridform_core.data_import import promote_binding_revision
from gridform_core.data_pack_validation import (
    CYCLIC_MARKET_ROLES, DEMAND_ROLES, VRE_PROFILE_ROLES, REQUIRED_CSV_COLUMNS,
    validate_data_pack,
)

MAX_UPLOAD_BYTES = 32 * 1024 * 1024
TOKEN = re.compile(r"^[0-9a-f]{32}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
FIELD_UNITS = {
    "projects.repd": {"capacity_mw": "MW"},
    "source.repd_raw": {"Installed Capacity (MWelec)": "MW"},
    "value.network.nodal-demand": {"demand_mwh": "MWh"},
    "value.network.ac.active-schedule": {"active_schedule_mwh": "MWh"},
    "value.network.ac.reactive-demand": {"reactive_demand_mvar": "MVAr"},
    "value.hydrology.site-catalogue": {"capacity_mw": "MW"},
}


MARKET_PROFILE_ROLES = {role for role in CYCLIC_MARKET_ROLES if role.endswith(".profile")}
MARKET_PRICE_ROLES = {role for role in CYCLIC_MARKET_ROLES if role.endswith(".price")}
# Roles whose MWh/period source converts to MW with the declared 30-minute interval.
PER_PERIOD_ENERGY_ROLES = DEMAND_ROLES | MARKET_PROFILE_ROLES


def _fx(value: object) -> dict[str, object] | None:
    """The explicit EUR->GBP rate of a mapping request (P0-5a S10); None when absent."""

    if value is None:
        return None
    if not isinstance(value, dict) or not {"eur_per_gbp", "fx_basis"} <= set(value) <= {"eur_per_gbp", "fx_basis", "price_year"}:
        raise DataMappingError("GF_MAPPING_FX", "fx must be {eur_per_gbp, fx_basis[, price_year]}.")
    try:
        fx_factor(value)
    except ValueError as exc:
        raise DataMappingError("GF_MAPPING_FX", str(exc)) from exc
    year = value.get("price_year")
    if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
        raise DataMappingError("GF_MAPPING_FX", "price_year must be an integer year.")
    return {"eur_per_gbp": float(value["eur_per_gbp"]), "fx_basis": str(value["fx_basis"]).strip(),
            **({"price_year": year} if year is not None else {})}


class DataMappingError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(message)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _write(path: Path, payload: object) -> None:
    path.write_bytes(_canonical(payload))


def _bytes(path: Path, root: Path) -> bytes:
    current = path
    path.absolute().relative_to(root.absolute())
    while current != root.parent:
        if current.is_symlink():
            raise DataMappingError("GF_MAPPING_UNSAFE_FILE", "Mapping files must not contain symbolic links.")
        current = current.parent
    if not path.is_file() or path.stat().st_nlink != 1:
        raise DataMappingError("GF_MAPPING_UNSAFE_FILE", "Mapping files must be independent regular files.")
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise DataMappingError("GF_MAPPING_SIZE", "CSV or mapping metadata exceeds 32 MiB.", 413)
    return path.read_bytes()


def _shape(raw: bytes) -> tuple[list[str], int]:
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise DataMappingError("GF_MAPPING_SIZE", "Provide a nonempty CSV no larger than 32 MiB.", 413)
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("NUL characters are not allowed")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if not header or any(not value.strip() for value in header) or len(set(header)) != len(header):
            raise ValueError("CSV requires a nonempty, unique header")
        rows = 0
        for row in reader:
            if len(row) != len(header):
                raise ValueError(f"CSV row {reader.line_num} does not match the header width")
            rows += 1
        if not rows:
            raise ValueError("CSV must contain data rows")
        return header, rows
    except (UnicodeError, csv.Error, ValueError, StopIteration) as exc:
        raise DataMappingError("GF_MAPPING_CSV", f"Invalid UTF-8 CSV: {exc}") from exc


class DataMappingService:
    def __init__(self, *, packs_root: Path, staging_root: Path, projects_root: Path,
                 trash_root: Path, dataset_slots: Sequence[Mapping[str, object]],
                 lifecycle_lock: object, ttl_seconds: int = 1800):
        self.packs_root, self.staging_root = Path(packs_root).absolute(), Path(staging_root).absolute()
        self.projects_root, self.trash_root = Path(projects_root), Path(trash_root)
        self.slots = {str(slot["role"]): dict(slot) for slot in dataset_slots}
        self.lock, self.ttl_seconds = lifecycle_lock, ttl_seconds

    def _target(self, pack_id: str, expected: str | None = None):
        if not isinstance(pack_id, str) or not SAFE_ID.fullmatch(pack_id):
            raise DataMappingError("GF_MAPPING_PACK", "Invalid data-pack identity.")
        root = self.packs_root / pack_id
        path = root / "manifest.json"
        raw = _bytes(path, self.packs_root)
        manifest = json.loads(raw)
        if (not isinstance(manifest, dict) or manifest.get("id") != pack_id
                or manifest.get("schema_version") != "value.data-pack/v1"
                or not isinstance(manifest.get("copy_origin"), dict)
                or manifest["copy_origin"].get("schema_version") != "value.data-pack-copy/v1"
                or manifest.get("data_pack_type") == "network_overlay" or manifest.get("network_overlay")):
            raise DataMappingError("GF_MAPPING_BASE_COPY_ONLY", "Copy a BASE pack before mapping; network overlays are not supported.", 409)
        digest = _hash(raw)
        if expected is not None and digest != expected:
            raise DataMappingError("GF_MAPPING_STALE_TARGET", "The target pack changed; stage and review again.", 409)
        guard_clone_upload(manifest, path, digest, self.projects_root, self.trash_root)
        return root, manifest, digest

    def _role(self, role: str) -> dict[str, object]:
        slot = self.slots.get(role)
        if not slot or "csv" not in runtime_supported_formats(role, tuple(slot.get("formats") or ())):
            raise DataMappingError("GF_MAPPING_ROLE", "Select a declared role with a shipped CSV parser.")
        single = role in DEMAND_ROLES | CYCLIC_MARKET_ROLES | VRE_PROFILE_ROLES
        if single:
            columns = [{"target": "value", "target_unit": slot.get("unit")}]
        elif role in CSV_TEMPLATES or role in REQUIRED_CSV_COLUMNS:
            header = CSV_TEMPLATES[role][0] if role in CSV_TEMPLATES else sorted(REQUIRED_CSV_COLUMNS[role])
            columns = [{"target": column, "target_unit": FIELD_UNITS.get(role, {}).get(column)} for column in header]
        else:
            raise DataMappingError("GF_MAPPING_ROLE", "This CSV role has no explicit canonical column contract.")
        demand = role in DEMAND_ROLES
        per_period = role in PER_PERIOD_ENERGY_ROLES
        price = role in MARKET_PRICE_ROLES
        return {"role": role, "columns": columns, "single_value": single,
                **({"interval_minutes": 30, "unit_contract": "value.demand-mw-half-hour/v1"} if demand else {}),
                **({"interval_minutes": 30} if role in MARKET_PROFILE_ROLES else {}),
                **({"fx_required_for": ["EUR/MWh"]} if price else {}),
                "conversion_pairs": [{"source_unit": source, "target_unit": target,
                                      **({"requires_fx": True} if (source, target) in FX_CONVERSIONS else {})}
                    for source, target in sorted(set(UNIT_FACTORS) | ({("MWh/period", "MW")} if per_period else set())
                                                 | (set(FX_CONVERSIONS) if price else set()) | {
                        (column["target_unit"], column["target_unit"]) for column in columns if column["target_unit"] is not None
                    }) if target in {column["target_unit"] for column in columns}]}

    def catalog(self, pack_id: str) -> dict[str, object]:
        with self.lock:
            _, _, digest = self._target(pack_id)
            roles = []
            for role in self.slots:
                try:
                    roles.append(self._role(role))
                except DataMappingError:
                    continue
            return {"schema_version": "value.data-mapping-catalog/v1", "pack_id": pack_id,
                    "target_manifest_sha256": digest, "roles": roles, "max_upload_bytes": MAX_UPLOAD_BYTES}

    def _new(self, kind: str) -> tuple[str, Path]:
        token = uuid.uuid4().hex
        root = self.staging_root / kind
        root.mkdir(parents=True, exist_ok=True)
        directory = root / token
        directory.mkdir()
        return token, directory

    def _load(self, kind: str, token: str):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise DataMappingError("GF_MAPPING_TOKEN", "Invalid mapping token.", 404)
        directory = self.staging_root / kind / token
        try:
            metadata = json.loads(_bytes(directory / "metadata.json", self.staging_root))
        except FileNotFoundError as exc:
            raise DataMappingError("GF_MAPPING_TOKEN", "Mapping review is unavailable; upload again.", 404) from exc
        if not isinstance(metadata, dict) or metadata.get("token") != token:
            raise DataMappingError("GF_MAPPING_IDENTITY", "Mapping metadata identity is inconsistent.", 409)
        expires = metadata.get("expires_epoch")
        if isinstance(expires, bool) or not isinstance(expires, (float, int)) or not math.isfinite(expires) or time.time() >= expires:
            raise DataMappingError("GF_MAPPING_EXPIRED", "Mapping review expired; upload and review again.", 409)
        return directory, metadata

    def stage(self, pack_id: str, role: str, raw: bytes, filename: str,
              expected_manifest_sha256: str) -> dict[str, object]:
        if not isinstance(expected_manifest_sha256, str) or not SHA.fullmatch(expected_manifest_sha256):
            raise DataMappingError("GF_MAPPING_IDENTITY", "Provide the exact target manifest checksum.")
        columns, rows = _shape(raw)
        if not isinstance(filename, str) or not filename.lower().endswith(".csv"):
            raise DataMappingError("GF_MAPPING_CSV", "Upload a .csv file.")
        with self.lock:
            self._role(role)
            _, _, digest = self._target(pack_id, expected_manifest_sha256)
            token, directory = self._new("stages")
            expires = time.time() + self.ttl_seconds
            report = {"schema_version": "value.data-mapping-stage/v1", "stage_id": token,
                      "pack_id": pack_id, "role": role, "source_sha256": _hash(raw), "source_bytes": len(raw),
                      "source_columns": columns, "rows": rows, "target_manifest_sha256": digest, "expires_at": _iso(expires)}
            try:
                (directory / "source.csv").write_bytes(raw)
                _write(directory / "metadata.json", {**report, "token": token, "expires_epoch": expires})
            except Exception:
                shutil.rmtree(directory)
                raise
            return report

    def _spec(self, role: str, columns: object, source_columns: list[str],
              fx: Mapping[str, object] | None = None) -> AdapterSpec:
        contract = self._role(role)
        targets = {column["target"]: column["target_unit"] for column in contract["columns"]}
        if not isinstance(columns, list) or len(columns) != len(targets):
            raise DataMappingError("GF_MAPPING_COLUMNS", "Map every canonical column exactly once.")
        rules = {}
        for item in columns:
            if not isinstance(item, dict) or set(item) != {"source", "target", "source_unit", "target_unit"}:
                raise DataMappingError("GF_MAPPING_COLUMNS", "Use explicit column and unit mappings only.")
            source, target = item["source"], item["target"]
            if not isinstance(source, str) or source not in source_columns or not isinstance(target, str) or target not in targets or target in rules:
                raise DataMappingError("GF_MAPPING_COLUMNS", "Unknown source/target column or repeated target.")
            source_unit, target_unit = item["source_unit"], item["target_unit"]
            if target_unit != targets[target] or (source_unit is not None and not isinstance(source_unit, str)):
                raise DataMappingError("GF_MAPPING_UNITS", "Target units must match the canonical field contract.")
            if target_unit is None:
                if source_unit is not None:
                    raise DataMappingError("GF_MAPPING_UNITS", "This field has no declared unit conversion.")
            elif (source_unit, target_unit) in FX_CONVERSIONS and role in MARKET_PRICE_ROLES:
                if fx is None:
                    raise DataMappingError("GF_MAPPING_FX", "EUR prices need an explicit eur_per_gbp and fx_basis.")
            elif source_unit is None or (source_unit != target_unit and (source_unit, target_unit) not in UNIT_FACTORS
                    and not (role in PER_PERIOD_ENERGY_ROLES and source_unit == "MWh/period" and target_unit == "MW")):
                raise DataMappingError("GF_MAPPING_UNITS", "Select an explicit supported source unit.")
            rules[target] = ColumnRule(source, target, source_unit, target_unit)
        uses_fx = any((rule.source_unit, rule.target_unit) in FX_CONVERSIONS for rule in rules.values())
        if fx is not None and not uses_fx:
            raise DataMappingError("GF_MAPPING_FX", "fx is only accepted for an EUR/MWh price column.")
        return AdapterSpec("value.explicit-column-mapping", "2" if role in DEMAND_ROLES else "1", "csv", role, "csv",
                           tuple(rules[column["target"]] for column in contract["columns"]),
                           interval_minutes=30 if role in PER_PERIOD_ENERGY_ROLES else None,
                           source=dict(fx or {}))

    def preview(self, stage_id: str, request: Mapping[str, object]) -> dict[str, object]:
        base_fields = {"schema_version", "source_sha256", "target_manifest_sha256", "columns"}
        if set(request) not in (base_fields, base_fields | {"fx"}) or request.get("schema_version") != "value.data-mapping-preview-request/v1":
            raise DataMappingError("GF_MAPPING_REQUEST", "Invalid mapping preview request.")
        fx = _fx(request.get("fx"))
        stage_dir, stage = self._load("stages", stage_id)
        raw = _bytes(stage_dir / "source.csv", self.staging_root)
        columns, rows = _shape(raw)
        if _hash(raw) != stage["source_sha256"] or request["source_sha256"] != stage["source_sha256"] or request["target_manifest_sha256"] != stage["target_manifest_sha256"]:
            raise DataMappingError("GF_MAPPING_IDENTITY", "Source or target identity changed; upload again.", 409)
        spec = self._spec(stage["role"], request["columns"], columns, fx)
        with self.lock:
            _, manifest, _ = self._target(stage["pack_id"], stage["target_manifest_sha256"])
            token, directory = self._new("reviews")
            _write(directory / "spec.json", spec.to_dict())
            errors = []
            validation = None
            sample = []
            digest = None
            size = 0
            try:
                result = execute_adapter(stage_dir / "source.csv", spec, directory / "normalized.csv")
                normalized = _bytes(directory / "normalized.csv", self.staging_root)
                _shape(normalized)
                digest, size = _hash(normalized), len(normalized)
                candidate = copy.deepcopy(manifest)
                candidate["bindings"] = {stage["role"]: {"uri": "normalized.csv", "format": "csv", "sha256": digest, "unit": self.slots[stage["role"]].get("unit")}}
                report = validate_data_pack(directory, candidate, [self.slots[stage["role"]]])
                validation = report["bindings"][0]
                errors = list(validation["errors"])
                sample = list(islice(csv.DictReader(io.StringIO(normalized.decode("utf-8"))), 20))
                if result.source_sha256 != stage["source_sha256"]:
                    raise DataMappingError("GF_MAPPING_IDENTITY", "Source changed during normalization.", 409)
            except (ValueError, OSError) as exc:
                errors = [str(exc)]
            expires = stage["expires_epoch"]
            review = {"schema_version": "value.data-mapping-review/v1", "review_id": token, "stage_id": stage_id,
                      "pack_id": stage["pack_id"], "role": stage["role"], "valid": not errors and validation is not None,
                      "errors": errors, "warnings": list(validation["warnings"]) if validation else [],
                      "source_sha256": stage["source_sha256"], "spec_sha256": _hash(_canonical(spec.to_dict())),
                      "normalized_sha256": digest, "target_manifest_sha256": stage["target_manifest_sha256"],
                      "source_bytes": len(raw), "normalized_bytes": size, "rows": rows,
                      "columns": spec.to_dict()["columns"], "sample_rows": sample, "validation": validation,
                      "interval_minutes": spec.interval_minutes,
                      "expires_at": _iso(expires)}
            _write(directory / "metadata.json", {**review, "token": token, "expires_epoch": expires})
            return review

    def commit(self, review_id: str, request: Mapping[str, object]) -> dict[str, object]:
        expected_fields = {"schema_version", "source_sha256", "spec_sha256", "normalized_sha256", "target_manifest_sha256"}
        if set(request) != expected_fields or request.get("schema_version") != "value.data-mapping-commit-request/v1":
            raise DataMappingError("GF_MAPPING_REQUEST", "Invalid mapping commit request.")
        with self.lock:
            directory, review = self._load("reviews", review_id)
            if review.get("valid") is not True or review.get("errors"):
                raise DataMappingError("GF_MAPPING_NOT_VALIDATED", "Review and validate this mapping before committing.", 409)
            for field in expected_fields - {"schema_version"}:
                if request[field] != review.get(field):
                    raise DataMappingError("GF_MAPPING_IDENTITY", "Reviewed mapping identity changed; review again.", 409)
            root, manifest, _ = self._target(review["pack_id"], review["target_manifest_sha256"])
            stage_dir, stage = self._load("stages", review["stage_id"])
            source = _bytes(stage_dir / "source.csv", self.staging_root)
            headers, _ = _shape(source)
            spec_payload = json.loads(_bytes(directory / "spec.json", self.staging_root))
            if not isinstance(spec_payload, dict):
                raise DataMappingError("GF_MAPPING_IDENTITY", "Mapping specification is corrupt; review again.", 409)
            spec = self._spec(review["role"], spec_payload.get("columns"), headers,
                              _fx(spec_payload.get("source") or None))
            if _canonical(spec_payload) != _canonical(spec.to_dict()) or _hash(_canonical(spec_payload)) != review["spec_sha256"] or _hash(source) != review["source_sha256"]:
                raise DataMappingError("GF_MAPPING_IDENTITY", "Source or mapping specification changed; review again.", 409)
            normalized = _bytes(directory / "normalized.csv", self.staging_root)
            if _hash(normalized) != review["normalized_sha256"] or stage["pack_id"] != review["pack_id"] or stage["role"] != review["role"]:
                raise DataMappingError("GF_MAPPING_IDENTITY", "Normalized bytes or target identity changed; review again.", 409)
            # Recompute to prove the reviewed bytes still derive from this exact source/spec.
            rebuilt = directory / "rechecked.csv"
            result = execute_adapter(stage_dir / "source.csv", spec, rebuilt)
            if result.normalized_sha256 != review["normalized_sha256"] or result.source_sha256 != review["source_sha256"]:
                rebuilt.unlink(missing_ok=True)
                raise DataMappingError("GF_MAPPING_IDENTITY", "Normalization no longer matches the reviewed bytes.", 409)
            self._target(review["pack_id"], review["target_manifest_sha256"])
            provenance_root = root / "mapping-provenance"
            if provenance_root.is_symlink():
                rebuilt.unlink(missing_ok=True)
                raise DataMappingError("GF_MAPPING_UNSAFE_FILE", "Mapping provenance must remain inside the pack.")
            provenance = provenance_root / review_id
            if provenance.exists():
                rebuilt.unlink(missing_ok=True)
                raise DataMappingError("GF_MAPPING_ALREADY_COMMITTED", "This review has already been committed.", 409)
            provenance.mkdir(parents=True)
            try:
                (provenance / "source.csv").write_bytes(source)
                _write(provenance / "spec.json", spec_payload)
                _write(provenance / "review.json", review)
                single = review["role"] in DEMAND_ROLES | CYCLIC_MARKET_ROLES | VRE_PROFILE_ROLES
                metadata = {"unit": self.slots[review["role"]].get("unit"),
                            **({"input_unit_contract": "value.demand-mw-half-hour/v1", "interval_minutes": 30}
                               if review["role"] in DEMAND_ROLES else {}),
                            # P0-5a S10: the normalized file declares how it is read.
                            **({"csv_header": True, "csv_column": "value"} if single else {}),
                            **({"interval_minutes": 30} if review["role"] in MARKET_PROFILE_ROLES else {}),
                            **({"currency": "GBP"} if review["role"] in MARKET_PRICE_ROLES else {}),
                            **({"source_currency": "EUR", **dict(spec.source)} if spec.source else {}),
                            "redistribution_class": "not_declared",
                            "owner_extension": self.slots[review["role"]].get("owner_extension"),
                            "capability": self.slots[review["role"]].get("capability"),
                            "mapping_provenance": {"schema_version": "value.data-mapping-provenance/v1",
                                "source_uri": (provenance / "source.csv").relative_to(root).as_posix(),
                                "spec_uri": (provenance / "spec.json").relative_to(root).as_posix(),
                                "review_uri": (provenance / "review.json").relative_to(root).as_posix(),
                                "source_sha256": review["source_sha256"], "spec_sha256": review["spec_sha256"],
                                "normalized_sha256": review["normalized_sha256"]}}
                binding, validation = promote_binding_revision(pack_root=root, manifest=manifest,
                    role=review["role"], staged_file=rebuilt, filename="mapped.csv", file_format="csv",
                    dataset_slots=[self.slots[review["role"]]], imported_at=_iso(time.time()), metadata=metadata)
            except Exception:
                shutil.rmtree(provenance)
                rebuilt.unlink(missing_ok=True)
                raise
            return {"schema_version": "value.data-mapping-commit/v1", "ok": True,
                    "pack_id": review["pack_id"], "role": review["role"], "binding": binding,
                    "validation": validation, "manifest_sha256": _hash((root / "manifest.json").read_bytes()),
                    "run_started": False}
