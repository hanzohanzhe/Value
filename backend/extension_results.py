"""Bounded historical extension summaries from frozen Run evidence only."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Mapping

from gridform_core.extension_framework import ExtensionManifest, canonical_hash, validate_extension_artifact
from gridform_core.run_policy import scope_runs_extensions

HEX = re.compile(r"[0-9a-f]{64}\Z")
LIMITS = {"status": 64 * 1024, "year_results": 16 * 1024 * 1024, "module_resolution": 2 * 1024 * 1024}
# F2-N1 (G4-05): a year-results file above LIMITS["year_results"] (any annual
# or longer Run: 17,520 period summaries a year) is not parsed whole; the
# extension artifacts are read line by line from the writer's indent-2 layout
# (gridform_core/application.py), hashing every byte, up to these bounds.
STREAM_YEAR_RESULTS_LIMIT = 4 * 1024 * 1024 * 1024
STREAM_ARTIFACTS_LIMIT = 2 * 1024 * 1024
_STREAM_CACHE: dict[tuple, tuple[list, str]] = {}
_STREAM_CACHE_SIZE = 4


class EvidenceError(ValueError):
    def __init__(self, status: str, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def _stat(path: Path) -> tuple:
    return _signature(path.stat())


def _signature(value) -> tuple:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _read(path: Path, root: Path, kind: str) -> tuple[object, str, tuple]:
    if not path.is_file():
        raise EvidenceError("unavailable", f"{kind}_missing", f"Recorded {kind} evidence is missing.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise EvidenceError("invalid", "source_path_outside_run", "Evidence path leaves the Run directory.")
    before = _stat(path)
    if before[2] > LIMITS[kind]:
        raise EvidenceError("unavailable", f"{kind}_size_limit", f"{kind} exceeds its bounded reader limit.")
    with path.open("rb") as stream:
        if _signature(os.fstat(stream.fileno())) != before:
            raise EvidenceError("invalid", "source_changed_during_read", "Evidence file identity changed before reading.")
        raw = stream.read(LIMITS[kind] + 1)
        if _signature(os.fstat(stream.fileno())) != before:
            raise EvidenceError("invalid", "source_changed_during_read", "Evidence file changed while reading.")
    if len(raw) > LIMITS[kind]:
        raise EvidenceError("unavailable", f"{kind}_size_limit", f"{kind} exceeds its bounded reader limit.")
    if before != _stat(path):
        raise EvidenceError("invalid", "source_changed_during_read", "Run evidence changed during reading; retry once stable.")
    try:
        payload = _finite_json(raw)
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError("invalid", f"{kind}_invalid_json", "Run evidence is not finite JSON.") from exc
    return payload, hashlib.sha256(raw).hexdigest(), before


def _finite_json(raw):
    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("nonfinite number")
        return value
    return json.loads(raw, parse_float=finite_float, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")))


_YEAR = re.compile(rb'^    "year": (-?\d+),?$')
_YEAR_SCHEMA = re.compile(rb'^    "schema_version": ("(?:[^"\\]|\\.)*"),?$')


def _stream_year_results(path: Path) -> tuple[list, str]:
    """Year identities and extension artifacts of a large year-results file, without parsing it whole.

    Relies on the one writer's ``json.dumps(..., indent=2)`` layout: a list of
    year objects whose ``"market"`` object holds ``"extensions"`` holding
    ``"extension_artifacts"``.  JSON strings cannot contain raw newlines, so
    each structural line is unambiguous.  Returns the same minimal shape the
    whole-file reader yields for this query, and the sha256 of every byte.
    A file in any other layout stays ``year_results_size_limit``.
    """

    def unsupported():
        return EvidenceError("unavailable", "year_results_size_limit",
                             "year_results exceeds its bounded reader limit and is not in the recorded indent-2 layout.")

    digest = hashlib.sha256()
    years: list = []
    current = None
    depth = None           # None outside a year; "year", "market", "extensions", "artifacts"
    captured: list[bytes] = []
    captured_bytes = 0
    first = True
    closed = False
    with path.open("rb") as stream:
        for line in stream:
            digest.update(line)
            text = line.rstrip(b"\r\n")
            if first:
                if text != b"[":
                    raise unsupported()
                first = False
                continue
            if closed:
                if text.strip():
                    raise unsupported()
                continue
            if depth is None:
                if text == b"  {":
                    current, depth = {"schema_version": None, "year": None, "market": None}, "year"
                elif text == b"]":
                    closed = True
                else:
                    raise unsupported()
            elif depth == "year":
                if text in (b"  }", b"  },"):
                    years.append(current); current, depth = None, None
                elif (match := _YEAR.match(text)):
                    current["year"] = int(match.group(1))
                elif (match := _YEAR_SCHEMA.match(text)):
                    current["schema_version"] = json.loads(match.group(1))
                elif text == b'    "market": {':
                    current["market"] = {"extensions": {}}; depth = "market"
                elif text in (b'    "market": {}', b'    "market": {},'):
                    current["market"] = {"extensions": {}}
            elif depth == "market":
                if text in (b"    }", b"    },"):
                    depth = "year"
                elif text == b'      "extensions": {':
                    depth = "extensions"
            elif depth == "extensions":
                if text in (b"      }", b"      },"):
                    depth = "market"
                elif text == b'        "extension_artifacts": [':
                    captured, captured_bytes, depth = [b"["], 1, "artifacts"
                elif text in (b'        "extension_artifacts": []', b'        "extension_artifacts": [],'):
                    current["market"]["extensions"]["extension_artifacts"] = []
            elif depth == "artifacts":
                if text in (b"        ]", b"        ],"):
                    captured.append(b"]")
                    try:
                        current["market"]["extensions"]["extension_artifacts"] = _finite_json(b"\n".join(captured))
                    except (ValueError, UnicodeError) as exc:
                        raise EvidenceError("invalid", "year_results_invalid_json", "Run evidence is not finite JSON.") from exc
                    captured, depth = [], "extensions"
                else:
                    captured.append(text)
                    captured_bytes += len(text) + 1
                    if captured_bytes > STREAM_ARTIFACTS_LIMIT:
                        raise EvidenceError("unavailable", "extension_artifacts_size_limit",
                                            "Recorded extension artifacts exceed their bounded reader limit.")
    if first or not closed or depth is not None:
        raise unsupported()
    return years, digest.hexdigest()


def _read_year_results(path: Path, root: Path) -> tuple[object, str, tuple]:
    """The whole-file reader up to its limit; above it, the bounded line reader (F2-N1)."""

    if not path.is_file() or path.stat().st_size <= LIMITS["year_results"]:
        return _read(path, root, "year_results")
    if not path.resolve().is_relative_to(root.resolve()):
        raise EvidenceError("invalid", "source_path_outside_run", "Evidence path leaves the Run directory.")
    before = _stat(path)
    if before[2] > STREAM_YEAR_RESULTS_LIMIT:
        raise EvidenceError("unavailable", "year_results_size_limit", "year_results exceeds its bounded reader limit.")
    key = (str(path.resolve()), before)
    cached = _STREAM_CACHE.get(key)
    if cached is None:
        years, digest = _stream_year_results(path)
        if before != _stat(path):
            raise EvidenceError("invalid", "source_changed_during_read", "Run evidence changed during reading; retry once stable.")
        while len(_STREAM_CACHE) >= _STREAM_CACHE_SIZE:
            _STREAM_CACHE.pop(next(iter(_STREAM_CACHE)))
        cached = _STREAM_CACHE[key] = (years, digest)
    return json.loads(json.dumps(cached[0])), cached[1], before


def _integer(query: Mapping, field: str, default=None):
    value = query.get(field, default)
    if value is None and default is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError(f"{field} must be a nonnegative integer")
    return int(value)


def _frozen(graph: Mapping) -> tuple[dict[str, ExtensionManifest], list[dict]]:
    if graph.get("schema_version") != "value.resolved-extension-graph/v1":
        raise EvidenceError("invalid", "frozen_extension_graph_schema_unsupported", "The frozen extension graph schema is unsupported.")
    identities, manifests, hooks = graph.get("extensions"), graph.get("manifests"), graph.get("hook_source_identities")
    if not isinstance(manifests, dict) or not isinstance(hooks, dict):
        raise EvidenceError("unavailable", "frozen_extension_declarations_missing", "This Run has no complete frozen extension declarations and hook source identities. Current registry definitions are not substituted.")
    if not isinstance(identities, list) or not identities:
        raise EvidenceError("unavailable", "frozen_extensions_missing", "No extensions are recorded in the frozen graph.")
    if len(identities) > 128:
        raise EvidenceError("unavailable", "frozen_extension_count_limit", "The frozen graph exceeds the extension summary limit.")
    parsed, metadata, ordered = {}, [], []
    for identity in identities:
        if not isinstance(identity, dict) or not all(isinstance(identity.get(field), str) for field in ("id", "version", "namespace", "manifest_sha256")):
            raise EvidenceError("invalid", "extension_identity_invalid", "Frozen extension identity is malformed.")
        extension_id = identity["id"]
        raw = manifests.get(extension_id)
        if not isinstance(raw, dict):
            raise EvidenceError("unavailable", "frozen_extension_manifest_missing", f"Frozen manifest is missing for {extension_id}.")
        if extension_id in parsed or canonical_hash(raw) != identity.get("manifest_sha256"):
            raise EvidenceError("invalid", "extension_manifest_identity_mismatch", "Frozen manifest hash does not match its recorded identity.")
        try:
            manifest = ExtensionManifest.from_dict(raw)
        except (TypeError, ValueError, KeyError) as exc:
            raise EvidenceError("invalid", "frozen_extension_manifest_invalid", "Frozen extension manifest is malformed.") from exc
        if (manifest.schema_version != "value.extension-bundle/v1" or manifest.id != extension_id or manifest.version != identity.get("version")
                or manifest.namespace != identity.get("namespace") or canonical_hash(manifest.to_dict()) != identity["manifest_sha256"]):
            raise EvidenceError("invalid", "extension_manifest_identity_mismatch", "Frozen manifest fields do not match its recorded identity.")
        source_rows = hooks.get(extension_id)
        if not isinstance(source_rows, list):
            raise EvidenceError("unavailable", "frozen_hook_source_identity_missing", f"Frozen hook source identities are missing for {extension_id}.")
        expected = {(hook.hook, hook.implementation) for hook in manifest.hooks}
        seen = set()
        for source in source_rows:
            if not isinstance(source, dict) or not isinstance(source.get("source_sha256"), str) or not HEX.fullmatch(source["source_sha256"]):
                raise EvidenceError("unavailable", "frozen_hook_source_identity_missing", "A frozen hook has no valid recorded source hash.")
            key = source.get("hook"), source.get("implementation")
            if key in seen or key not in expected:
                raise EvidenceError("invalid", "frozen_hook_identity_mismatch", "Hook source identity does not match the frozen declaration.")
            seen.add(key)
        if seen != expected:
            raise EvidenceError("unavailable", "frozen_hook_source_identity_missing", "Not every frozen hook has recorded source identity.")
        parsed[extension_id] = manifest
        metadata.append({key: identity[key] for key in ("id", "version", "namespace", "manifest_sha256")})
        ordered.append(raw)
    if set(manifests) != set(parsed) or set(hooks) != set(parsed):
        raise EvidenceError("invalid", "frozen_extension_members_mismatch", "Frozen graph membership does not match its declarations.")
    payload = {"extensions": ordered, "hook_source_identities": hooks,
               "parameters": graph.get("parameters"), "parameter_schema_hashes": graph.get("parameter_schema_hashes"), "hook_order": graph.get("hook_order")}
    if canonical_hash(payload) != graph.get("graph_sha256"):
        raise EvidenceError("invalid", "frozen_extension_graph_hash_mismatch", "Frozen extension graph hash does not match its contents.")
    return parsed, metadata


def _no_extensions_selected(run_root: Path) -> bool:
    """True when the Run's frozen Study selected no extensions (R5 R-低7).

    A Run without extensions records no extension graph by design; only when
    the frozen Study lists extensions is a missing graph an evidence gap.
    """

    try:
        snapshot = json.loads((run_root / "project-snapshot.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    selected = snapshot.get("selected_extensions") if isinstance(snapshot, dict) else None
    return isinstance(selected, list) and not selected


def query_extension_artifacts(run_root: Path, query: Mapping) -> dict:
    """Read a bounded page of declared scalar summaries; never load hook code."""
    if set(query) - {"extension_id", "year", "limit", "offset"}:
        raise ValueError("Unsupported extension result query field")
    extension_id = query.get("extension_id")
    if extension_id is not None and (not isinstance(extension_id, str) or not extension_id or len(extension_id) > 128 or not re.fullmatch(r"[A-Za-z0-9_.-]+", extension_id)):
        raise ValueError("extension_id must be a bounded extension identifier")
    year, limit, offset = _integer(query, "year"), _integer(query, "limit", 20), _integer(query, "offset", 0)
    if (year is not None and not 1 <= year <= 9999) or not 1 <= limit <= 100 or not 0 <= offset <= 1_000_000:
        raise ValueError("Extension result query bounds are invalid")
    result = {"schema_version": "value.extension-results/v1", "run_id": run_root.name,
              "status": "unavailable", "reason_code": None, "message": None,
              "source": {"year_results": {"path": "model-output/year-results-v2.json", "sha256": None},
                         "module_resolution": {"path": "model-output/module-resolution.json", "sha256": None}},
              "identity": {"container_run_id": None, "frozen_module_graph_sha256": None, "frozen_extension_graph_sha256": None},
              "scope": {"extension_id": extension_id, "year": year},
              "capabilities": {"summary_only": True, "extensions": [], "years": [], "unavailable_dimensions": ["period", "zone", "technology"]},
              "total": 0, "limit": limit, "offset": offset, "count": 0, "has_more": False, "items": []}
    snapshots = []
    try:
        status_path = run_root / "status.json"
        status, _, stamp = _read(status_path, run_root, "status")
        snapshots.append((status_path, stamp))
        if not isinstance(status, dict):
            raise EvidenceError("invalid", "run_status_invalid", "Run status must be an object.")
        result["identity"]["container_run_id"] = status.get("id")
        if not (status.get("status") == "completed" or (status.get("status") == "archived" and status.get("archived_from_status") == "completed")):
            raise EvidenceError("withheld", "run_not_completed", "Extension summaries are available only for completed Runs or Runs archived from completed.")
        graph_path = run_root / result["source"]["module_resolution"]["path"]
        graph, digest, stamp = _read(graph_path, run_root, "module_resolution")
        snapshots.append((graph_path, stamp)); result["source"]["module_resolution"]["sha256"] = digest
        if isinstance(graph, dict):
            # R5 R-低7: the module graph is recorded whether or not extensions were selected.
            result["identity"]["frozen_module_graph_sha256"] = graph.get("graph_sha256")
        if not isinstance(graph, dict) or not isinstance(graph.get("extension_graph"), dict):
            if _no_extensions_selected(run_root):
                raise EvidenceError("unavailable", "no_extensions_selected",
                                    "This Run selected no optional extensions, so it has no extension results.")
            raise EvidenceError("unavailable", "frozen_extension_graph_missing", "This Run has no frozen extension graph.")
        result["identity"]["frozen_extension_graph_sha256"] = graph["extension_graph"].get("graph_sha256")
        manifests, identities = _frozen(graph["extension_graph"])
        result["capabilities"]["extensions"] = identities
        if extension_id is not None and extension_id not in manifests:
            raise EvidenceError("unavailable", "extension_not_in_frozen_graph", "The selected extension was not frozen in this Run.")
        # F-D2 (DECISIONS A16-3): the one-day lesson runs the market step only;
        # name that as the reason instead of reporting missing year results.
        if not scope_runs_extensions(status.get("mode")):
            names = ", ".join(sorted(manifests))
            raise EvidenceError("unavailable", "extensions_not_executed_in_scope",
                                f"The one-day lesson runs the market step only, so the recorded extension(s) {names} did not execute in this Run. Re-run with two-period or a longer scope to obtain extension results.")
        years_path = run_root / result["source"]["year_results"]["path"]
        years, digest, stamp = _read_year_results(years_path, run_root)
        snapshots.append((years_path, stamp)); result["source"]["year_results"]["sha256"] = digest
        if not isinstance(years, list):
            raise EvidenceError("invalid", "year_results_invalid", "Year results must be a list.")
        rows, available_years = [], set()
        for year_row in years:
            if not isinstance(year_row, dict) or year_row.get("schema_version") != "value.year-result/v2" or isinstance(year_row.get("year"), bool) or not isinstance(year_row.get("year"), int):
                raise EvidenceError("invalid", "year_result_identity_invalid", "A year result has no valid year identity.")
            recorded_year = year_row["year"]
            market = year_row.get("market")
            if not isinstance(market, dict) or not isinstance(market.get("extensions", {}), dict):
                raise EvidenceError("invalid", "year_result_market_invalid", "A year result has no valid market extension object.")
            artifacts = market.get("extensions", {}).get("extension_artifacts", [])
            if not isinstance(artifacts, list):
                raise EvidenceError("invalid", "extension_artifacts_invalid", "Extension artifacts must be a list.")
            for artifact in artifacts:
                if not isinstance(artifact, dict) or artifact.get("producer_extension") not in manifests:
                    raise EvidenceError("invalid", "artifact_owner_invalid", "Artifact producer has no frozen declaration.")
                owner = artifact["producer_extension"]; manifest = manifests[owner]
                try:
                    validated = validate_extension_artifact(artifact, manifest)
                except ValueError as exc:
                    raise EvidenceError("invalid", "artifact_contract_invalid", str(exc)) from exc
                source_hash = validated.get("source_inputs_sha256")
                if not isinstance(source_hash, str) or not HEX.fullmatch(source_hash):
                    raise EvidenceError("invalid", "artifact_input_identity_invalid", "Artifact has no valid recorded input SHA-256.")
                if "year" in artifact and artifact["year"] != recorded_year:
                    raise EvidenceError("invalid", "artifact_year_identity_mismatch", "Artifact year differs from its enclosing year result.")
                declaration = next(item for item in manifest.artifacts if item.artifact_type == validated["artifact_type"])
                summary, missing = {}, []
                if len(declaration.summary_fields) > 32 or any(not field or len(field) > 128 for field in declaration.summary_fields):
                    raise EvidenceError("unavailable", "summary_field_count_limit", "The declaration exceeds the bounded summary field limit.")
                for field in declaration.summary_fields:
                    value = validated.get(field)
                    if value is None or not isinstance(value, (str, int, float, bool)) or (isinstance(value, float) and not math.isfinite(value)) or len(json.dumps(value)) > 1024:
                        summary[field] = None; missing.append(field)
                    else:
                        summary[field] = value
                if len(summary) > 32:
                    raise EvidenceError("unavailable", "summary_field_count_limit", "The declaration exceeds the bounded summary field limit.")
                available_years.add(recorded_year)
                if (year is None or recorded_year == year) and (extension_id is None or extension_id == owner):
                    rows.append({"year": recorded_year, "extension_id": owner, "extension_version": manifest.version,
                                 "namespace": manifest.namespace, "manifest_sha256": canonical_hash(manifest.to_dict()),
                                 "artifact_type": declaration.artifact_type, "schema_version": declaration.schema_version,
                                 "source_inputs_sha256": source_hash, "summary_fields": list(declaration.summary_fields),
                                 "summary": summary, "unavailable_summary_fields": missing})
        result["capabilities"]["years"] = sorted(available_years)
        for path, stamp in snapshots:
            if _stat(path) != stamp:
                raise EvidenceError("invalid", "source_changed_during_query", "Frozen evidence changed during querying; retry once stable.")
        total = len(rows); items = rows[offset:offset + limit]
        result.update(status="available" if total else "unavailable", reason_code=None if total else "extension_artifact_not_recorded",
                      message=None if total else "No declared extension artifact is recorded for this scope.",
                      total=total, count=len(items), items=items, has_more=offset + len(items) < total)
    except EvidenceError as exc:
        result.update(status=exc.status, reason_code=exc.code, message=str(exc))
    except (OSError, KeyError, TypeError, RecursionError) as exc:
        result.update(status="invalid", reason_code="extension_evidence_unreadable", message=f"Frozen extension evidence cannot be read: {type(exc).__name__}.")
    return result
