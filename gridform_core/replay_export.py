"""Bounded, on-demand exports from authoritative VALUE market ledgers."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import uuid
import zipfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping

from .market_ledger import _read_only_connection, validate_market_ledger_file
from .module_context import RunStaticContext, YearContext, canonical_context_sha256
from .run_policy import resolve_run_policy
from .run_snapshot import SnapshotError, verify_run_input_snapshot
from .v2.module_manifest import workspace_registry
from .zonal_contracts import load_zonal_network_pack
from .zonal_solver_contract import validate_solver_settings


REPLAY_EXPORT_SCHEMA = "value.replay-export/v1"
REPLAY_EXPORT_MANIFEST_SCHEMA = "value.replay-export-manifest/v1"
_SUPPORTED_RANGES = {"period", "24_hours", "168_hours", "year", "complete"}
_SUPPORTED_FORMATS = {"zip", "jsonl", "csv"}
_REDISTRIBUTABLE = {
    "redistributable",
    "redistributable_cc0",
    "redistributable_open",
    "redistributable_with_attribution",
    "redistributable_cc_by_4_with_attribution",
    "redistributable_derived_data_with_attribution",
    "redistributable_neso_open_licence_with_attribution",
    "redistributable_ogl_uk_3_with_attribution",
    "redistributable_owner_licensed",
    "public_domain",
    "open",
}


@dataclass(frozen=True)
class ReplayExportRequest:
    range_kind: str
    year: int | None
    period_from: int | None
    period_to: int | None
    output_format: str

    def __post_init__(self) -> None:
        if self.range_kind not in _SUPPORTED_RANGES:
            raise ValueError(
                "range_kind must be period, 24_hours, 168_hours, year or complete"
            )
        if self.output_format not in _SUPPORTED_FORMATS:
            raise ValueError("output_format must be zip, jsonl or csv")
        if self.year is not None and int(self.year) < 0:
            raise ValueError("year cannot be negative")
        for name in ("period_from", "period_to"):
            value = getattr(self, name)
            if value is not None and int(value) < 0:
                raise ValueError(f"{name} cannot be negative")
        if (
            self.period_from is not None
            and self.period_to is not None
            and int(self.period_to) < int(self.period_from)
        ):
            raise ValueError("period_to must be at least period_from")


def _layout(database: Path) -> tuple[Path, Path, Path]:
    database = database.resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Market ledger is not available: {database}")
    if database.parent.name == "market" and database.parent.parent.name == "model-output":
        model_output = database.parent.parent
        run_root = model_output.parent
    else:
        model_output = database.parent
        run_root = database.parent
    return run_root, model_output, model_output / "exports"


def _confined_destination(database: Path, destination: Path) -> tuple[Path, Path]:
    _, _, export_root = _layout(database)
    export_root = export_root.resolve()
    candidate = destination.resolve()
    try:
        candidate.relative_to(export_root)
    except ValueError as exc:
        raise ValueError("Replay export destination must be inside the run export root") from exc
    if candidate == export_root or candidate.exists():
        raise ValueError("Replay export destination must be a new file")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate, export_root


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _metadata(connection: sqlite3.Connection) -> dict[str, object]:
    if "metadata" not in _tables(connection):
        return {}
    result: dict[str, object] = {}
    for key, value in connection.execute("SELECT key, value FROM metadata"):
        try:
            result[str(key)] = json.loads(str(value))
        except json.JSONDecodeError:
            result[str(key)] = str(value)
    return result


def _read_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is missing or invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is missing or invalid")
    return payload


def _validate_complete_run(
    run_root: Path, connection: sqlite3.Connection, tables: set[str]
) -> None:
    status = _read_object(run_root / "status.json", "Official Run status")
    if (
        status.get("status") != "completed"
        or status.get("execution_status") not in {"passed", "completed"}
    ):
        raise ValueError("Complete replay export requires an officially completed Run")
    project = _read_object(
        run_root / "input-snapshot" / "project.json", "Frozen Study project"
    )
    try:
        start_year = int(project["start_year"])
        end_year = int(project["end_year"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Frozen Study project does not declare planned years") from exc
    if end_year < start_year:
        raise ValueError("Frozen Study project does not declare valid planned years")
    planned_years = set(range(start_year, end_year + 1))
    actual_years = {
        int(row[0])
        for row in connection.execute(
            "SELECT DISTINCT year FROM period_summary ORDER BY year"
        )
    }
    if actual_years != planned_years or "year_integrity" not in tables:
        raise ValueError("Complete replay export requires all planned years")
    integrity = {
        int(row[0]): (int(row[1]), int(row[2]))
        for row in connection.execute(
            "SELECT year, period_count, complete FROM year_integrity ORDER BY year"
        )
    }
    if set(integrity) != planned_years:
        raise ValueError("Complete replay export requires all planned years")
    for year in sorted(planned_years):
        declared_count, complete = integrity[year]
        observed_count, minimum, maximum = connection.execute(
            "SELECT COUNT(DISTINCT period), MIN(period), MAX(period) "
            "FROM period_summary WHERE year=?",
            (year,),
        ).fetchone()
        observed_count = int(observed_count)
        if complete != 1:
            raise ValueError(f"Replay export requires completed ledger year {year}")
        if (
            declared_count != observed_count
            or observed_count < 1
            or int(minimum) != 0
            or int(maximum) != observed_count - 1
        ):
            raise ValueError(f"Replay export year {year} has invalid period closure")


def _where(
    request: ReplayExportRequest,
    connection: sqlite3.Connection,
    run_root: Path,
) -> tuple[str, tuple[object, ...], int]:
    tables = _tables(connection)
    if request.range_kind == "complete":
        if any(value is not None for value in (request.year, request.period_from, request.period_to)):
            raise ValueError("complete range does not accept year or period bounds")
        if request.output_format != "zip":
            raise ValueError("complete-run export is available only as a replay ZIP")
        _validate_complete_run(run_root, connection, tables)
        count = int(connection.execute(
            "SELECT COUNT(DISTINCT CAST(year AS TEXT) || ':' || CAST(period AS TEXT)) FROM period_summary"
        ).fetchone()[0])
        return "", (), count
    if request.year is None:
        raise ValueError(f"{request.range_kind} range requires year")
    year = int(request.year)
    minimum, maximum = connection.execute(
        "SELECT MIN(period), MAX(period) FROM period_summary WHERE year=?", (year,)
    ).fetchone()
    if minimum is None:
        raise ValueError("Requested replay year is not available")
    if "year_integrity" in tables:
        completed = connection.execute(
            "SELECT complete FROM year_integrity WHERE year=?", (year,)
        ).fetchone()
        if completed is None or int(completed[0]) != 1:
            raise ValueError(f"Replay export requires completed ledger year {year}")
    if request.range_kind == "year":
        if request.period_from is not None or request.period_to is not None:
            raise ValueError("year range does not accept period bounds")
        start, end = int(minimum), int(maximum)
    else:
        if request.period_from is None:
            raise ValueError(f"{request.range_kind} range requires period_from")
        start = int(request.period_from)
        lengths = {"period": 1, "24_hours": 48, "168_hours": 336}
        expected_end = start + lengths[request.range_kind] - 1
        if request.period_to is not None and int(request.period_to) != expected_end:
            raise ValueError(
                f"{request.range_kind} range requires period_to={expected_end}"
            )
        end = expected_end
    count = int(connection.execute(
        "SELECT COUNT(DISTINCT period) FROM period_summary "
        "WHERE year=? AND period BETWEEN ? AND ?",
        (year, start, end),
    ).fetchone()[0])
    required = {"period": 1, "24_hours": 48, "168_hours": 336}.get(request.range_kind)
    if required is not None and count != required:
        raise ValueError(
            f"Requested {request.range_kind} range is incomplete: expected {required} periods, found {count}"
        )
    return " WHERE year=? AND period BETWEEN ? AND ?", (year, start, end), count


def _selected_periods(
    connection: sqlite3.Connection,
    where: str,
    values: tuple[object, ...],
) -> Iterator[tuple[int, int]]:
    for row in connection.execute(
        "SELECT DISTINCT year, period FROM period_summary" + where + " ORDER BY year, period",
        values,
    ):
        yield int(row[0]), int(row[1])


def _json_bytes(payload: object) -> bytes:
    def thaw(value: object) -> object:
        if isinstance(value, Mapping):
            return {str(key): thaw(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [thaw(item) for item in value]
        return value

    return json.dumps(
        thaw(payload), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rows(connection: sqlite3.Connection, table: str, year: int, period: int) -> list[dict[str, object]]:
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    if not columns or not {"year", "period"}.issubset(columns):
        return []
    connection.row_factory = sqlite3.Row
    return [
        dict(row)
        for row in connection.execute(
            f"SELECT * FROM {table} WHERE year=? AND period=? ORDER BY rowid",
            (year, period),
        )
    ]


def _period_input(connection: sqlite3.Connection, year: int, period: int) -> dict[str, object]:
    connection.row_factory = sqlite3.Row
    declared = [dict(row) for row in connection.execute(
        "SELECT * FROM clearing_inputs WHERE year=? AND period=? ORDER BY stage, input_sha256",
        (year, period),
    )]
    outcomes: dict[str, dict[str, object]] = {}
    for row in connection.execute(
        "SELECT o.* FROM clearing_outcomes o JOIN clearing_inputs i "
        "ON i.input_sha256=o.input_sha256 WHERE i.year=? AND i.period=? "
        "ORDER BY i.stage, i.input_sha256",
        (year, period),
    ):
        outcomes[str(row["input_sha256"])] = dict(row)
    if not declared or len(outcomes) != len(declared):
        raise ValueError(
            f"Full replay declarations/outcomes are incomplete for {year}:{period}"
        )
    return {
        "schema_version": "value.replay-period-input/v1",
        "year": year,
        "period": period,
        "declarations": declared,
        "outcomes_by_input_sha256": outcomes,
    }


def _period_outcome(
    connection: sqlite3.Connection,
    tables: set[str],
    year: int,
    period: int,
) -> dict[str, object]:
    common = (
        "period_summary", "dispatch_summary", "storage_summary", "redispatch_summary",
        "zonal_period_accounting", "zone_period_summary", "boundary_period_summary",
        "vre_curtailment_period", "zonal_demand_alignment", "solver_declaration_link",
    )
    return {
        "schema_version": "value.replay-period-outcome/v1",
        "year": year,
        "period": period,
        "tables": {table: _rows(connection, table, year, period) for table in common if table in tables},
    }


def _context_path(model_output: Path, run_root: Path, artifact_path: str) -> Path:
    relative = Path(artifact_path.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Context registry artifact path is not confined")
    candidates = (model_output / relative, run_root / relative)
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(run_root.resolve())
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    raise ValueError(f"Registered context artifact is missing: {artifact_path}")


def _validated_context(
    *,
    source: Path,
    scope: str,
    registry_year: int,
    schema_version: str,
    declared_sha256: str,
    run_context_sha256: str | None,
) -> tuple[bytes, RunStaticContext | YearContext]:
    raw = source.read_bytes()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("context payload must be an object")
        if scope == "run":
            if registry_year != -1:
                raise ValueError("run context registry year must be -1")
            context: RunStaticContext | YearContext = RunStaticContext(**payload)
        elif scope == "year":
            context = YearContext(**payload)
            if context.year != registry_year:
                raise ValueError("year context registry year mismatch")
            if context.run_context_sha256 != run_context_sha256:
                raise ValueError("year context run identity mismatch")
        else:
            raise ValueError("unsupported context scope")
        if context.schema_version != schema_version:
            raise ValueError("context schema mismatch")
        if canonical_context_sha256(context) != declared_sha256:
            raise ValueError("context hash mismatch")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Registered {scope} context identity does not match its artifact"
        ) from exc
    return raw, context


def _verified_snapshot(run_root: Path) -> tuple[dict[str, object], object]:
    registry = workspace_registry()
    try:
        snapshot = verify_run_input_snapshot(
            run_root / "input-snapshot", registry
        )
    except (OSError, ValueError, SnapshotError) as exc:
        raise ValueError(f"frozen snapshot identity validation failed: {exc}") from exc
    status = _read_object(run_root / "status.json", "Official Run status")
    if (
        str(status.get("input_snapshot_id") or "")
        != str(snapshot.get("snapshot_id") or "")
        or str(status.get("input_tree_sha256") or "")
        != str(snapshot.get("input_tree_sha256") or "")
    ):
        raise ValueError("frozen snapshot identity does not match the official Run")
    return snapshot, registry


def _validate_snapshot_context_identity(
    *,
    run_root: Path,
    snapshot: Mapping[str, object],
    registry: object,
    project: Mapping[str, object],
    run_context: RunStaticContext,
) -> None:
    pack = _read_object(
        run_root / "input-snapshot" / "pack" / "manifest.json",
        "Frozen data-pack manifest",
    )
    data_pack = dict(run_context.data_pack)
    expected_data_pack = {
        "data_pack_id": pack.get("id"),
        "manifest_sha256": snapshot.get("pack_manifest_sha256"),
        "scientific_sha256": pack.get("scientific_sha256"),
        "bindings": pack.get("bindings"),
    }
    if str(project.get("data_pack_id") or "") != str(pack.get("id") or ""):
        raise ValueError("Frozen Study data pack does not match the snapshot manifest")
    if _json_bytes(data_pack) != _json_bytes(expected_data_pack):
        raise ValueError("Frozen snapshot identity does not match Run context data pack")
    if _json_bytes(run_context.module_graph) != _json_bytes(
        snapshot.get("module_resolution_graph") or {}
    ):
        raise ValueError("Frozen snapshot identity does not match Run context module graph")

    modules = [
        row for row in snapshot.get("modules", ()) if isinstance(row, Mapping)
    ]
    selected_modules = {
        str(row.get("slot")): str(row.get("module_id")) for row in modules
    }
    if selected_modules != {
        str(slot): str(module_id)
        for slot, module_id in dict(project.get("modules") or {}).items()
    }:
        raise ValueError("Frozen Study modules do not match the snapshot identity")
    balancing = next(
        (row for row in modules if str(row.get("slot")) == "balancing"), None
    )
    expected_solver: Mapping[str, object] = {}
    if balancing is not None:
        # Resolve the declaration to prove the selected module exists, then
        # compare against the canonical settings actually frozen by the Study.
        registry.manifest(
            str(balancing.get("module_id")), expected_slot="balancing"
        )
        expected_solver = validate_solver_settings(
            project.get("solver_contract")
        ).to_dict()
    if _json_bytes(run_context.solver_contract) != _json_bytes(expected_solver):
        raise ValueError("Frozen snapshot identity does not match Run context solver")
    network_hash = snapshot.get("network_pack_manifest_sha256")
    if network_hash is None:
        if run_context.network_pack is not None:
            raise ValueError("Run context declares a network pack absent from the snapshot")
        return
    network = _read_object(
        run_root / "input-snapshot" / "network-pack" / "manifest.json",
        "Frozen network-pack manifest",
    )
    try:
        frozen_network = load_zonal_network_pack(
            run_root / "input-snapshot" / "network-pack", network,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"Frozen network-pack identity validation failed: {exc}") from exc
    if (
        str(frozen_network.network_pack_id)
        != str(snapshot.get("network_pack_id") or "")
        or _json_bytes(run_context.network_pack or {}) != _json_bytes(
            frozen_network.to_dict()
        )
    ):
        raise ValueError("Frozen network-pack identity does not match Run context")


def _validate_complete_policy(
    *,
    run_root: Path,
    project: Mapping[str, object],
    run_context: RunStaticContext,
    connection: sqlite3.Connection,
) -> None:
    status = _read_object(run_root / "status.json", "Official Run status")
    mode = str(status.get("mode") or "")
    frozen_policy = status.get("run_policy")
    if not isinstance(frozen_policy, Mapping):
        raise ValueError("Complete replay export requires a frozen Study run policy")
    try:
        policy = resolve_run_policy(mode)
        canonical_policy = policy.to_dict(project)
        if _json_bytes(frozen_policy) != _json_bytes(canonical_policy):
            raise ValueError("Frozen Study run policy is not canonical")
        planned_start = int(frozen_policy["start_year"])
        planned_end = int(frozen_policy["end_year"])
        expected = int(frozen_policy["periods_per_year"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Complete replay export requires a frozen Study run policy") from exc
    if (
        run_context.start_year != planned_start
        or run_context.end_year != planned_end
    ):
        raise ValueError("Complete replay Run context does not match the frozen Study policy")
    if mode in {"full", "two_year"}:
        clock_expected = int(round(8760.0 / run_context.period_hours))
        if expected != clock_expected:
            raise ValueError(
                "Complete replay Study policy does not match the frozen Run clock"
            )
    for year in range(planned_start, planned_end + 1):
        row = connection.execute(
            "SELECT period_count FROM year_integrity WHERE year=?", (year,)
        ).fetchone()
        observed = int(connection.execute(
            "SELECT COUNT(DISTINCT period) FROM period_summary WHERE year=?", (year,)
        ).fetchone()[0])
        if row is None or int(row[0]) != expected or observed != expected:
            raise ValueError(
                f"Complete replay export expected {expected} periods for {year}"
            )


def _rights(run_root: Path) -> tuple[str, list[dict[str, object]], list[tuple[str, bytes]]]:
    manifests: list[tuple[str, bytes]] = []
    references: list[dict[str, object]] = []
    restricted = False
    project = _read_object(run_root / "input-snapshot" / "project.json", "Frozen Study project")
    snapshot = _read_object(run_root / "input-snapshot" / "snapshot.json", "Frozen input snapshot")

    def has_network_selection(value: object) -> bool:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key) in {"network_pack", "network_pack_id"} and item:
                    return True
                if has_network_selection(item):
                    return True
        if isinstance(value, (list, tuple)):
            return any(has_network_selection(item) for item in value)
        return False

    required = {"pack"}
    if has_network_selection(project) or has_network_selection(snapshot):
        required.add("network-pack")
    for name in ("pack", "network-pack"):
        path = run_root / "input-snapshot" / name / "manifest.json"
        if not path.is_file():
            if name in required:
                restricted = True
            continue
        payload = _read_object(path, f"Frozen {name} manifest")
        bindings = payload.get("bindings")
        if not isinstance(bindings, Mapping) or not bindings:
            restricted = True
            bindings = {}
        safe_bindings: dict[str, object] = {}
        for role, raw in sorted(bindings.items()):
            if not isinstance(raw, Mapping):
                restricted = True
                continue
            binding = dict(raw)
            policy = str(
                binding.get("redistribution_policy")
                or binding.get("redistribution_class")
                or binding.get("redistribution_decision")
                or "not_declared"
            ).lower()
            if policy not in _REDISTRIBUTABLE:
                restricted = True
            sha256 = str(binding.get("sha256") or "")
            uri = str(binding.get("uri") or "")
            if (
                len(sha256) != 64
                or any(character not in "0123456789abcdef" for character in sha256)
                or not uri.strip()
            ):
                restricted = True
            references.append({
                "pack": str(payload.get("id") or name),
                "role": str(role),
                "sha256": sha256 or None,
                "local_reference": uri or None,
                "redistribution_policy": policy,
                "source_bytes_included": False,
            })
            safe_binding = {
                key: binding[key]
                for key in (
                    "uri", "sha256", "source_sha256", "normalized_sha256",
                    "redistribution_policy", "redistribution_class",
                    "redistribution_decision",
                )
                if key in binding
            }
            if isinstance(binding.get("bytes"), int):
                safe_binding["bytes"] = binding["bytes"]
            safe_bindings[str(role)] = safe_binding
        safe_manifest = {
            key: payload[key]
            for key in (
                "schema_version", "id", "version", "manifest_sha256",
                "scientific_sha256", "source_sha256", "revision_sha256",
                "canonical_sha256", "content_sha256", "pack_sha256",
            )
            if key in payload
        }
        safe_manifest["bindings"] = safe_bindings
        manifests.append((f"study/{name}-manifest.json", _json_bytes(safe_manifest)))
    return (
        "reference_only_not_portable" if restricted else "portable",
        references,
        manifests,
    )


def _write_zip(
    database: Path,
    temporary: Path,
    request: ReplayExportRequest,
    where: str,
    values: tuple[object, ...],
    period_count: int,
) -> dict[str, object]:
    run_root, model_output, _ = _layout(database)
    snapshot_identity, snapshot_registry = _verified_snapshot(run_root)
    portability, data_references, pack_manifests = _rights(run_root)
    members: dict[str, dict[str, object]] = {}

    def add(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
        archive.writestr(name, payload)
        members[name] = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}

    with _read_only_connection(database) as connection, zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
    ) as archive:
        tables = _tables(connection)
        metadata = _metadata(connection)
        trace_level = str(metadata.get("trace_level") or "unknown")
        if trace_level != "full":
            raise ValueError("Replay ZIP requires a completed Full market replay ledger")
        observed_count = int(connection.execute(
            "SELECT COUNT(DISTINCT CAST(year AS TEXT) || ':' || CAST(period AS TEXT)) "
            "FROM period_summary" + where,
            values,
        ).fetchone()[0])
        if observed_count != period_count:
            raise ValueError("Replay range changed while export was being prepared")
        selected_years = {
            int(row[0])
            for row in connection.execute(
                "SELECT DISTINCT year FROM period_summary" + where + " ORDER BY year",
                values,
            )
        }
        if "year_integrity" in tables:
            for year in sorted(selected_years):
                row = connection.execute(
                    "SELECT complete FROM year_integrity WHERE year=?", (year,)
                ).fetchone()
                if row is None or int(row[0]) != 1:
                    raise ValueError(f"Replay export requires completed ledger year {year}")
        registry = []
        run_context_contract: RunStaticContext | None = None
        year_context_contracts: dict[int, YearContext] = {}
        if "context_registry" in tables:
            registry_rows = connection.execute(
                "SELECT context_scope, year, schema_version, sha256, artifact_path "
                "FROM context_registry ORDER BY context_scope, year"
            ).fetchall()
            run_rows = [row for row in registry_rows if str(row[0]) == "run"]
            if len(run_rows) != 1:
                raise ValueError("Replay export requires exactly one registered run context identity")
            ordered_rows = run_rows + [
                row for row in registry_rows
                if str(row[0]) == "year" and int(row[1]) in selected_years
            ]
            for row in ordered_rows:
                scope, year, schema_version, sha256, artifact_path = row
                source = _context_path(model_output, run_root, str(artifact_path))
                raw, context_contract = _validated_context(
                    source=source,
                    scope=str(scope),
                    registry_year=int(year),
                    schema_version=str(schema_version),
                    declared_sha256=str(sha256),
                    run_context_sha256=(
                        canonical_context_sha256(run_context_contract)
                        if run_context_contract is not None else None
                    ),
                )
                if isinstance(context_contract, RunStaticContext):
                    run_context_contract = context_contract
                else:
                    year_context_contracts[context_contract.year] = context_contract
                target = (
                    "contexts/run-context.json" if str(scope) == "run"
                    else f"contexts/year-{int(year)}.json"
                )
                add(archive, target, raw)
                registry.append({
                    "scope": str(scope), "year": int(year),
                    "schema_version": str(schema_version), "sha256": str(sha256),
                    "member": target,
                })
            if run_context_contract is None or set(year_context_contracts) != selected_years:
                raise ValueError("Replay export requires registered context identity for every selected year")
            run_digest = canonical_context_sha256(run_context_contract)
            if "year_integrity" in tables:
                for selected_year, year_context_contract in year_context_contracts.items():
                    integrity_contexts = connection.execute(
                        "SELECT run_context_sha256, year_context_sha256 "
                        "FROM year_integrity WHERE year=?",
                        (selected_year,),
                    ).fetchone()
                    if (
                        integrity_contexts is None
                        or str(integrity_contexts[0]) != run_digest
                        or str(integrity_contexts[1])
                        != canonical_context_sha256(year_context_contract)
                    ):
                        raise ValueError(
                            f"Ledger context identity does not match year integrity for {selected_year}"
                        )
        else:
            raise ValueError("Replay export requires a context registry")
        project = run_root / "input-snapshot" / "project.json"
        snapshot = run_root / "input-snapshot" / "snapshot.json"
        if not project.is_file() or not snapshot.is_file():
            raise ValueError("Study revision or frozen input manifest is missing")
        add(archive, "study/project.json", project.read_bytes())
        add(archive, "study/input-snapshot.json", snapshot.read_bytes())
        for target, payload in pack_manifests:
            add(archive, target, payload)
        project_payload = _read_object(project, "Frozen Study project")
        if (
            run_context_contract is None
            or run_context_contract.study_revision_sha256
            != str(project_payload.get("revision_sha256") or "")
            or run_context_contract.start_year != int(project_payload.get("start_year", -1))
            or run_context_contract.end_year != int(project_payload.get("end_year", -1))
        ):
            raise ValueError("Run context identity does not match the frozen Study project")
        official_status = _read_object(run_root / "status.json", "Official Run status")
        if (
            str(official_status.get("id") or "") != run_context_contract.run_id
            or str(metadata.get("run_id") or "") != run_context_contract.run_id
            or (
                official_status.get("project_id") is not None
                and str(official_status.get("project_id"))
                != str(project_payload.get("id") or "")
            )
        ):
            raise ValueError("Run context identity does not match Run or ledger metadata")
        _validate_snapshot_context_identity(
            run_root=run_root,
            snapshot=snapshot_identity,
            registry=snapshot_registry,
            project=project_payload,
            run_context=run_context_contract,
        )
        if request.range_kind == "complete":
            _validate_complete_policy(
                run_root=run_root,
                project=project_payload,
                run_context=run_context_contract,
                connection=connection,
            )
        snapshot_payload = json.loads(snapshot.read_text("utf-8"))
        add(archive, "identity/module-solver.json", _json_bytes({
            "schema_version": "value.replay-module-solver-identity/v1",
            "modules": snapshot_payload.get("modules", []),
            "module_resolution_graph": snapshot_payload.get("module_resolution_graph"),
            "run_context_module_graph": dict(run_context_contract.module_graph),
            "solver_contract": dict(run_context_contract.solver_contract),
        }))
        roots = []
        if "year_integrity" in tables:
            roots = [dict(zip(
                ("year", "run_context_sha256", "year_context_sha256", "science_root", "evidence_root", "period_count", "complete"),
                row,
            )) for row in connection.execute(
                "SELECT year, run_context_sha256, year_context_sha256, science_root, evidence_root, period_count, complete "
                "FROM year_integrity ORDER BY year"
            ) if int(row[0]) in selected_years]
        add(archive, "integrity/roots.json", _json_bytes({
            "schema_version": "value.replay-integrity-roots/v1",
            "contexts": registry,
            "years": roots,
            "ledger_sha256": _sha256_file(database),
        }))
        for year, period in _selected_periods(connection, where, values):
            prefix = f"periods/{year}/{period:06d}"
            add(archive, f"{prefix}/input.json", _json_bytes(_period_input(connection, year, period)))
            add(archive, f"{prefix}/outcome.json", _json_bytes(
                _period_outcome(connection, tables, year, period)
            ))
        manifest = {
            "schema_version": REPLAY_EXPORT_MANIFEST_SCHEMA,
            "request": {
                "range_kind": request.range_kind,
                "year": request.year,
                "period_from": request.period_from,
                "period_to": request.period_to,
                "output_format": request.output_format,
            },
            "ledger_schema_version": metadata.get("schema_version"),
            "trace_level": trace_level,
            "period_count": period_count,
            "portability": portability,
            "data_references": data_references,
            "members": members,
        }
        archive.writestr("manifest.json", _json_bytes(manifest))
    return {"portability": portability, "members": len(members) + 1}


def _write_flat(
    database: Path,
    temporary: Path,
    output_format: str,
    where: str,
    values: tuple[object, ...],
) -> int:
    rows_written = 0
    with _read_only_connection(database) as connection, temporary.open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            "SELECT * FROM period_summary" + where + " ORDER BY year, period, stage",
            values,
        )
        writer: csv.DictWriter[str] | None = None
        for row in cursor:
            payload = dict(row)
            if output_format == "jsonl":
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            else:
                if writer is None:
                    writer = csv.DictWriter(handle, fieldnames=list(payload))
                    writer.writeheader()
                writer.writerow(payload)
            rows_written += 1
        handle.flush()
        os.fsync(handle.fileno())
    return rows_written


def create_replay_export(
    database: Path,
    request: ReplayExportRequest,
    destination: Path,
) -> Mapping[str, object]:
    """Create one explicit range export without mutating or copying the ledger."""

    if not isinstance(request, ReplayExportRequest):
        raise TypeError("request must be a ReplayExportRequest")
    destination, _ = _confined_destination(database, destination)
    with _read_only_connection(database) as connection:
        tables = _tables(connection)
        if "period_summary" not in tables:
            raise ValueError("Market ledger has no period summaries")
        run_root, _, _ = _layout(database)
        where, values, period_count = _where(request, connection, run_root)
        metadata = _metadata(connection)
    if metadata.get("schema_version") == "value.market-ledger/v8":
        ledger_validation = validate_market_ledger_file(database)
        if not bool(ledger_validation.get("valid")):
            errors = ", ".join(str(item) for item in ledger_validation.get("errors", ()))
            raise ValueError(f"Replay export ledger integrity validation failed: {errors}")
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        if request.output_format == "zip":
            extra = _write_zip(database, temporary, request, where, values, period_count)
            rows = period_count
        else:
            rows = _write_flat(database, temporary, request.output_format, where, values)
            extra = {"portability": "local_bounded_tabular_export"}
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        # Same-directory hard-link publication is atomic and refuses an
        # already-created destination instead of overwriting another job.
        os.link(temporary, destination)
        temporary.unlink()
        return {
            "schema_version": REPLAY_EXPORT_SCHEMA,
            "range_kind": request.range_kind,
            "format": request.output_format,
            "period_count": period_count,
            "rows": rows,
            "bytes": destination.stat().st_size,
            "sha256": _sha256_file(destination),
            "uri": str(destination),
            **extra,
        }
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
