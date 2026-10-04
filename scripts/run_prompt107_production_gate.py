"""Run the fail-closed Prompt 107 real-period production gates.

The command resolves only immutable manifests installed below ``user_data_root``.
It never substitutes the retained VALUE pack or a synthetic pack for the
required VALUE UK public-data pack, and it never starts Prompt 105.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]


def ensure_source_root() -> Path:
    """Prefer this script's checkout over an editable install from another tree."""

    root_text = str(ROOT)
    sys.path[:] = [
        entry
        for entry in sys.path
        if Path(entry or ".").resolve() != ROOT
    ]
    sys.path.insert(0, root_text)
    return ROOT


ensure_source_root()
BASE_PACK_ID = "value-uk-open-data-pack-v1"
NETWORK_PACK_ID = "force-gb-zonal-network-v1-c9e841112c40"
NETWORK_SCIENTIFIC_SHA256 = (
    "73866744184560532ad89f8c1d933941153269c977ea54039a6309973765f791"
)
EXPECTED_FAILED_PERIOD: Mapping[str, object] = {
    "year": 2025,
    "period": 6,
    "period_id": "2022-01-01:07",
    "redispatch_avoided_curtailment_mwh": 1693.7812375732246,
    "total_curtailment_mwh": 0.0,
}
STAGE_ORDER = ("smoke", "exact-periods", "24h", "168h", "annual", "two-year")
THROUGH_INDEX = {stage_id: index for index, stage_id in enumerate(STAGE_ORDER)}
SOLVER_STACK_VALIDATION_STATUS = "solver_stack_not_yet_validated"
MINIMUM_PRODUCTION_FREE_BYTES = 20 * 1024**3
PROMPT104_SOURCE_HASHES: Mapping[str, str] = {
    "prompt104-copperplate-preflight.json": "93e74ad18772ad99bda9c141210094d1909fa0b13a672961f25f9c1ddfb66b25",
    "prompt104-staged-copperplate-study.json": "37096955e425c9c350a8ae8a5e7c9958b29c45629f5d714ef70969d4fbe00f43",
    "prompt104-zonal-preflight.json": "ba3c410909cbe5a3bfe2a4c497928589a7857329e4527c184608db2284839d62",
    "prompt104-zonal-study.json": "9c3c5cea12a67a25fcb8309fde1c1b11be76fafdfb4ef8abfbbc6a0f4492bea3",
}
STAGE_MODES = {
    "smoke": ("smoke", 2, 1),
    "24h": ("validation_24h", 48, 1),
    "168h": ("validation_168h", 336, 1),
    "annual": ("full", 17_520, 1),
    "two-year": ("two_year", 17_520, 2),
}
EXACT_PERIOD_CASES: tuple[Mapping[str, str], ...] = (
    {
        "fixture": "period-2025-14.json.gz",
        "fixture_sha256": "1e0f453ec01427d90ce3801eae62ccb67f9d8be375f26e00896131dc90f995bd",
        "declared_input_sha256": "88d613706bd1400bd16cc0210526a864c0ea93acd6d4262ffa058811dd77068a",
        "scientific_result_sha256": "94b4bb1ee6cfcb7a46a7cd74260c4cfd5adda71f539cdb2a53c703906f801320",
    },
    {
        "fixture": "period-bound-noise.json",
        "fixture_sha256": "4f8a8da200812138433dda9b0e2775e6c69f2daaff442a2cfc8e269a4378ca17",
        "declared_input_sha256": "92d90fdf2a9b17e6599e09f0f8456108efe14a8293a4f58208d86f4b40602184",
        "scientific_result_sha256": "41b63c822f0cc5969485097a81a52a556f2daf0ef1f1565b1ac8b1aca6093374",
    },
)


class ProductionGateError(RuntimeError):
    """A stable Prompt 107 stop code plus machine-readable evidence."""

    def __init__(self, code: str, evidence: Mapping[str, object]) -> None:
        self.code = str(code)
        self.evidence = dict(evidence)
        super().__init__(f"{self.code}: {json.dumps(self.evidence, sort_keys=True)}")


def _lexical_absolute(path: Path) -> Path:
    """Return an absolute path without following any filesystem redirect."""

    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _redirect_component(path: Path) -> Path | None:
    """Return the first existing symlink/junction/reparse component, if any."""

    lexical = _lexical_absolute(path)
    components = [lexical]
    components.extend(lexical.parents)
    for component in reversed(components):
        if not os.path.lexists(component):
            continue
        information = os.lstat(component)
        attributes = int(getattr(information, "st_file_attributes", 0))
        reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        if stat.S_ISLNK(information.st_mode) or attributes & reparse_flag:
            return component
    return None


def _validated_output_root(path: Path) -> Path:
    lexical = _lexical_absolute(path)
    redirect = _redirect_component(lexical)
    if redirect is not None:
        raise ProductionGateError(
            "GF_PROMPT107_OUTPUT_ROOT_REDIRECTED",
            {
                "declared_output_root": str(lexical),
                "redirect_component": str(redirect),
            },
        )
    return lexical


def _runtime_source_lineage(source_root: Path = ROOT) -> dict[str, object]:
    """Require and identify the complete visible Git tree used for launch."""

    repository = _lexical_absolute(source_root)

    def git_bytes(*arguments: str) -> bytes:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={repository.as_posix()}",
                *arguments,
            ],
            cwd=repository,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise ProductionGateError(
                "GF_PROMPT107_SOURCE_LINEAGE_UNAVAILABLE",
                {
                    "source_root": str(repository),
                    "git_arguments": list(arguments),
                    "git_return_code": result.returncode,
                    "git_stderr": result.stderr.decode(errors="replace").strip(),
                },
            )
        return result.stdout

    head = git_bytes("rev-parse", "HEAD").decode().strip()
    tree_id = git_bytes("rev-parse", "HEAD^{tree}").decode().strip()
    status_bytes = git_bytes(
        "status", "--porcelain=v1", "--untracked-files=all"
    )
    diff_bytes = git_bytes("diff", "--binary", "HEAD")
    tracked_manifest = git_bytes("ls-files", "--stage", "-z")
    status = status_bytes.decode(errors="replace").splitlines()
    lineage = {
        "head": head,
        "tree_id": tree_id,
        "worktree_clean": not status,
        "worktree_status": status,
        "git_diff_sha256": hashlib.sha256(diff_bytes).hexdigest(),
        "git_status_sha256": hashlib.sha256(status_bytes).hexdigest(),
        "worktree_state_sha256": hashlib.sha256(
            status_bytes + b"\0" + diff_bytes
        ).hexdigest(),
        "tracked_source_manifest_sha256": hashlib.sha256(
            tracked_manifest
        ).hexdigest(),
        "tracked_file_count": tracked_manifest.count(b"\0"),
        "lineage_status": "clean_runtime_tree" if not status else "dirty_runtime_tree",
    }
    if status:
        raise ProductionGateError("GF_PROMPT107_WORKTREE_DIRTY", lineage)
    return lineage


@dataclass(frozen=True)
class RequiredPacks:
    base_root: Path
    base_manifest: Mapping[str, object]
    network_root: Path
    network_manifest: Mapping[str, object]


def _read_manifest(
    path: Path,
    *,
    required_id: str,
    missing_code: str,
    mismatch_code: str,
) -> dict[str, object]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ProductionGateError(
            missing_code,
            {
                "required_pack_id": required_id,
                "required_manifest": str(resolved),
            },
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionGateError(
            mismatch_code,
            {
                "expected_pack_id": required_id,
                "observed_pack_id": None,
                "manifest": str(resolved),
                "read_error": f"{type(exc).__name__}: {exc}",
            },
        ) from exc
    if not isinstance(payload, dict):
        payload = {}
    observed_id = str(payload.get("id") or "")
    if observed_id != required_id:
        raise ProductionGateError(
            mismatch_code,
            {
                "expected_pack_id": required_id,
                "observed_pack_id": observed_id,
                "manifest": str(resolved),
            },
        )
    return payload


def resolve_required_packs(data_root: Path) -> RequiredPacks:
    """Resolve the exact approved manifests from the mutable VALUE data root."""

    root = Path(data_root).expanduser().resolve()
    base_root = (root / "data-packs" / BASE_PACK_ID).resolve()
    network_root = (
        root / "data-workbench" / "installed-packs" / NETWORK_PACK_ID
    ).resolve()
    base_manifest = _read_manifest(
        base_root / "manifest.json",
        required_id=BASE_PACK_ID,
        missing_code="GF_PROMPT107_BASE_PACK_MISSING",
        mismatch_code="GF_PROMPT107_BASE_PACK_ID_MISMATCH",
    )
    network_manifest = _read_manifest(
        network_root / "manifest.json",
        required_id=NETWORK_PACK_ID,
        missing_code="GF_PROMPT107_NETWORK_PACK_MISSING",
        mismatch_code="GF_PROMPT107_NETWORK_PACK_ID_MISMATCH",
    )
    network_identity = dict(network_manifest.get("zonal_network_pack") or {})
    approval = dict(network_manifest.get("owner_approval") or {})
    observed_scientific_hash = str(
        network_identity.get("scientific_sha256") or ""
    )
    approved_install_hash = str(
        approval.get("installed_scientific_sha256") or ""
    )
    embedded_network_id = str(network_identity.get("network_pack_id") or "")
    approved_network_id = str(approval.get("network_pack_id") or "")
    if embedded_network_id != NETWORK_PACK_ID or approved_network_id != NETWORK_PACK_ID:
        raise ProductionGateError(
            "GF_PROMPT107_NETWORK_PACK_ID_MISMATCH",
            {
                "expected_pack_id": NETWORK_PACK_ID,
                "observed_pack_id": str(network_manifest.get("id") or ""),
                "embedded_network_pack_id": embedded_network_id,
                "approved_network_pack_id": approved_network_id,
                "manifest": str((network_root / "manifest.json").resolve()),
            },
        )
    if (
        observed_scientific_hash != NETWORK_SCIENTIFIC_SHA256
        or approved_install_hash != NETWORK_SCIENTIFIC_SHA256
    ):
        raise ProductionGateError(
            "GF_PROMPT107_NETWORK_PACK_HASH_MISMATCH",
            {
                "network_pack_id": NETWORK_PACK_ID,
                "required_scientific_sha256": NETWORK_SCIENTIFIC_SHA256,
                "observed_scientific_sha256": observed_scientific_hash,
                "owner_approved_installed_scientific_sha256": approved_install_hash,
                "manifest": str((network_root / "manifest.json").resolve()),
            },
        )
    if network_manifest.get("data_pack_type") != "network_overlay":
        raise ProductionGateError(
            "GF_PROMPT107_NETWORK_PACK_TYPE_MISMATCH",
            {
                "network_pack_id": NETWORK_PACK_ID,
                "expected_data_pack_type": "network_overlay",
                "observed_data_pack_type": network_manifest.get("data_pack_type"),
            },
        )
    return RequiredPacks(
        base_root=base_root,
        base_manifest=base_manifest,
        network_root=network_root,
        network_manifest=network_manifest,
    )


_FAILED_PERIOD_COLUMNS = (
    "year",
    "period",
    "period_id",
    "realised_available_vre_mwh",
    "perfect_reference_dispatch_mwh",
    "copperplate_reference_dispatch_mwh",
    "zonal_final_dispatch_mwh",
    "economic_curtailment_mwh",
    "forecast_added_curtailment_mwh",
    "forecast_avoided_curtailment_mwh",
    "redispatch_added_curtailment_mwh",
    "redispatch_avoided_curtailment_mwh",
    "redispatch_net_impact_mwh",
    "total_curtailment_mwh",
    "identity_residual_mwh",
    "validation_tolerance_mwh",
    "accounting_status",
)


def _finite(value: object, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ProductionGateError(
            "GF_PROMPT107_FAILED_PERIOD_INVALID",
            {"field": field, "observed": value, "reason": "not_numeric"},
        ) from exc
    if not math.isfinite(numeric):
        raise ProductionGateError(
            "GF_PROMPT107_FAILED_PERIOD_INVALID",
            {"field": field, "observed": value, "reason": "not_finite"},
        )
    return numeric


def read_exact_failed_period_evidence(database: Path) -> dict[str, object]:
    """Read and validate only the original period-6/period-7 boundary row."""

    resolved = Path(database).resolve()
    if not resolved.is_file():
        raise ProductionGateError(
            "GF_PROMPT107_FAILED_PERIOD_EVIDENCE_MISSING",
            {"database": str(resolved), **dict(EXPECTED_FAILED_PERIOD)},
        )
    query = (
        f"SELECT {', '.join(_FAILED_PERIOD_COLUMNS)} "
        "FROM vre_curtailment_period WHERE year = ? AND period = ? AND period_id = ?"
    )
    try:
        with sqlite3.connect(resolved) as connection:
            rows = connection.execute(
                query,
                (
                    EXPECTED_FAILED_PERIOD["year"],
                    EXPECTED_FAILED_PERIOD["period"],
                    EXPECTED_FAILED_PERIOD["period_id"],
                ),
            ).fetchall()
    except sqlite3.Error as exc:
        raise ProductionGateError(
            "GF_PROMPT107_FAILED_PERIOD_EVIDENCE_MISSING",
            {"database": str(resolved), "sqlite_error": str(exc)},
        ) from exc
    if len(rows) != 1:
        raise ProductionGateError(
            "GF_PROMPT107_FAILED_PERIOD_EVIDENCE_MISSING",
            {
                "database": str(resolved),
                "matching_rows": len(rows),
                **dict(EXPECTED_FAILED_PERIOD),
            },
        )
    raw = dict(zip(_FAILED_PERIOD_COLUMNS, rows[0]))
    numeric_fields = _FAILED_PERIOD_COLUMNS[3:-1]
    values = {field: _finite(raw[field], field) for field in numeric_fields}
    tolerance = max(values["validation_tolerance_mwh"], 1e-9)

    expected_avoided = float(
        EXPECTED_FAILED_PERIOD["redispatch_avoided_curtailment_mwh"]
    )
    checks = {
        "redispatch_avoided_expected": abs(
            values["redispatch_avoided_curtailment_mwh"] - expected_avoided
        ) <= max(tolerance, 1e-6),
        "zero_dispatch_gap": abs(
            values["realised_available_vre_mwh"]
            - values["zonal_final_dispatch_mwh"]
            - values["total_curtailment_mwh"]
        ) <= tolerance,
        "economic_split": abs(
            values["realised_available_vre_mwh"]
            - values["perfect_reference_dispatch_mwh"]
            - values["economic_curtailment_mwh"]
        ) <= tolerance,
        "forecast_split": abs(
            values["perfect_reference_dispatch_mwh"]
            - values["copperplate_reference_dispatch_mwh"]
            - values["forecast_added_curtailment_mwh"]
            + values["forecast_avoided_curtailment_mwh"]
        ) <= tolerance,
        "redispatch_split": abs(
            values["copperplate_reference_dispatch_mwh"]
            - values["zonal_final_dispatch_mwh"]
            - values["redispatch_added_curtailment_mwh"]
            + values["redispatch_avoided_curtailment_mwh"]
        ) <= tolerance,
        "signed_redispatch_net": abs(
            values["redispatch_added_curtailment_mwh"]
            - values["redispatch_avoided_curtailment_mwh"]
            - values["redispatch_net_impact_mwh"]
        ) <= tolerance,
        "identity_residual_bounded": abs(values["identity_residual_mwh"])
        <= tolerance,
        "accounting_status_reconciled": raw["accounting_status"] == "reconciled",
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise ProductionGateError(
            "GF_PROMPT107_FAILED_PERIOD_INVALID",
            {
                "database": str(resolved),
                "failed_checks": failed_checks,
                "observed": raw,
                "expected": dict(EXPECTED_FAILED_PERIOD),
            },
        )
    case_split_fields = (
        "perfect_reference_dispatch_mwh",
        "copperplate_reference_dispatch_mwh",
        "zonal_final_dispatch_mwh",
        "economic_curtailment_mwh",
        "forecast_added_curtailment_mwh",
        "forecast_avoided_curtailment_mwh",
        "redispatch_added_curtailment_mwh",
        "redispatch_avoided_curtailment_mwh",
    )
    return {
        **raw,
        "case_split": {field: values[field] for field in case_split_fields},
        "checks": checks,
    }


def _nested_solver_gate_failures(value: object) -> list[str]:
    failure_statuses = {
        "GO_WITH_NUMERICAL_WARNING",
        "COMPLETED_WITH_NUMERICAL_WARNING",
    }
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "solver_validation_gate_status" and str(nested) in failure_statuses:
                found.append(str(nested))
            if key == "solver_validation_summary" and isinstance(nested, Mapping):
                annual_status = str(nested.get("annual_status") or "")
                if annual_status in failure_statuses:
                    found.append(annual_status)
            found.extend(_nested_solver_gate_failures(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found.extend(_nested_solver_gate_failures(nested))
    return list(dict.fromkeys(found))


def run_stage_sequence(
    through: str,
    execute_stage: Callable[[str], Mapping[str, object]],
) -> dict[str, object]:
    """Execute ordered gates and stop before every stage after the first failure."""

    if through not in THROUGH_INDEX:
        raise ValueError(f"through must be one of {', '.join(STAGE_ORDER)}")
    required = STAGE_ORDER[: THROUGH_INDEX[through] + 1]
    records: list[dict[str, object]] = []
    stopped_after: str | None = None
    for stage_id in required:
        try:
            record = dict(execute_stage(stage_id))
        except ProductionGateError as exc:
            record = {
                "stage_id": stage_id,
                "status": "failed",
                "error_code": exc.code,
                "error_evidence": exc.evidence,
            }
        if record.get("stage_id") != stage_id:
            record = {
                **record,
                "stage_id": stage_id,
                "status": "failed",
                "error_code": "GF_PROMPT107_STAGE_ID_MISMATCH",
            }
        solver_gate_failures = _nested_solver_gate_failures(record)
        if solver_gate_failures:
            record = {
                **record,
                "reported_status": record.get("status"),
                "status": "failed",
                "error_code": "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO",
                "solver_gate_failures": solver_gate_failures,
            }
        if record.get("status") != "passed":
            records.append(record)
            stopped_after = stage_id
            break
        records.append(record)
    started = [str(record["stage_id"]) for record in records]
    not_started = [stage_id for stage_id in required if stage_id not in started]
    return {
        "through": through,
        "required_stages": list(required),
        "status": "failed" if stopped_after is not None else "passed",
        "stopped_after": stopped_after,
        "not_started": not_started,
        "stages": records,
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="",
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _sqlite_evidence_connection(
    database: Path,
) -> Iterator[sqlite3.Connection]:
    from gridform_core.market_ledger import _read_only_connection

    with _read_only_connection(database) as connection:
        yield connection


def _copy_approved_study(source: Path, destination: Path) -> str:
    source_bytes = source.read_bytes()
    if destination.exists():
        if destination.read_bytes() != source_bytes:
            raise ProductionGateError(
                "GF_PROMPT107_STUDY_COPY_MISMATCH",
                {"source": str(source), "destination": str(destination)},
            )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return hashlib.sha256(source_bytes).hexdigest()


def _changed_leaf_paths(
    original: object, derived: object, prefix: str = ""
) -> set[str]:
    if isinstance(original, Mapping) and isinstance(derived, Mapping):
        changes: set[str] = set()
        for key in set(original) | set(derived):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in original or key not in derived:
                changes.add(path)
            else:
                changes.update(
                    _changed_leaf_paths(original[key], derived[key], path)
                )
        return changes
    return set() if original == derived else {prefix}


def _write_immutable_json(path: Path, payload: Mapping[str, object]) -> str:
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise ProductionGateError(
                "GF_PROMPT107_DERIVED_STUDY_EXISTS",
                {"path": str(path)},
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(encoded)
        temporary.replace(path)
    return hashlib.sha256(encoded).hexdigest()


def derive_execution_studies(
    output_root: Path, packs: RequiredPacks
) -> dict[str, dict[str, object]]:
    """Derive current-identity execution copies under the approved Option A ruling."""

    from gridform_core.project_revision import (
        attach_revision_identity,
        derive_zonal_execution_project,
    )
    from gridform_core.v2.module_manifest import workspace_registry
    from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection

    root = _validated_output_root(output_root)
    registry = workspace_registry()
    sources = {
        "copperplate": ROOT / "publication" / "prompt104-staged-copperplate-study.json",
        "zonal": ROOT / "publication" / "prompt104-zonal-study.json",
    }
    old_ack = "module:value-zonal-redispatch-balancing@1.0.0"
    new_ack = "module:value-zonal-redispatch-balancing@2.0.0"
    expected_changes = {
        "copperplate": {"revision_sha256"},
        "zonal": {
            "revision_sha256",
            "solver_contract",
            f"maturity_acknowledgements.{old_ack}",
            f"maturity_acknowledgements.{new_ack}",
        },
    }
    evidence: dict[str, dict[str, object]] = {}
    for kind, source in sources.items():
        if not source.is_file():
            raise ProductionGateError(
                "GF_PROMPT107_APPROVED_STUDY_MISSING",
                {"study_kind": kind, "source": str(source)},
            )
        source_before = source.read_bytes()
        source_hash = hashlib.sha256(source_before).hexdigest()
        source_copy = root / "studies" / "source" / source.name
        copied_hash = _copy_approved_study(source, source_copy)
        original = json.loads(source_before.decode("utf-8"))
        candidate = json.loads(source_before.decode("utf-8"))
        exact_derivation = ["recompute revision_sha256 with project revision helper"]
        derivation = None
        if kind == "zonal":
            selection = resolve_zonal_pack_selection(
                candidate,
                base_pack_root=packs.base_root,
                base_manifest=packs.base_manifest,
                explicit_network_pack_root=packs.network_root,
            )
            revision_manifest = selection.revision_manifest
            try:
                derived, derivation = derive_zonal_execution_project(
                    source_before,
                    registry=registry,
                    data_pack_manifest=revision_manifest,
                )
            except ValueError as exc:
                raise ProductionGateError(
                    "GF_PROMPT107_ZONAL_DERIVATION_INVALID",
                    {"source": str(source), "message": str(exc)},
                ) from exc
            exact_derivation.insert(
                0,
                f"rename maturity acknowledgement {old_ack} to {new_ack}",
            )
            exact_derivation.insert(1, "add built-in v1 solver contract defaults")
        else:
            revision_manifest = packs.base_manifest
            derived = attach_revision_identity(candidate, registry, revision_manifest)
        changes = _changed_leaf_paths(original, derived)
        if changes != expected_changes[kind]:
            raise ProductionGateError(
                "GF_PROMPT107_DERIVED_STUDY_DELTA_INVALID",
                {
                    "study_kind": kind,
                    "expected_changed_leaf_paths": sorted(expected_changes[kind]),
                    "observed_changed_leaf_paths": sorted(changes),
                },
            )
        execution_copy = root / "studies" / "execution" / source.name
        execution_hash = _write_immutable_json(execution_copy, derived)
        if source.read_bytes() != source_before:
            raise ProductionGateError(
                "GF_PROMPT107_APPROVED_STUDY_SOURCE_CHANGED",
                {"study_kind": kind, "source": str(source)},
            )
        evidence[kind] = {
            "source": str(source),
            "source_copy": str(source_copy),
            "execution_copy": str(execution_copy),
            "source_sha256": source_hash,
            "source_copy_sha256": copied_hash,
            "execution_sha256": execution_hash,
            "source_revision_sha256": original.get("revision_sha256"),
            "execution_revision_sha256": derived.get("revision_sha256"),
            "changed_leaf_paths": sorted(changes),
            "exact_derivation": exact_derivation,
        }
        if derivation is not None:
            evidence[kind]["derivation"] = derivation
    return evidence


def derive_two_year_execution_studies(
    output_root: Path,
    packs: RequiredPacks,
    annual_evidence: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, dict[str, object]]:
    """Create immutable 2025--2026 revisions from the approved annual studies."""

    from gridform_core.project_revision import attach_revision_identity
    from gridform_core.v2.module_manifest import workspace_registry
    from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection

    root = _validated_output_root(output_root)
    annual = dict(annual_evidence or derive_execution_studies(root, packs))
    registry = workspace_registry()
    evidence: dict[str, dict[str, object]] = {}
    expected_changes = {
        "end_year",
        "id",
        "name",
        "parent_revision_sha256",
        "revision_number",
        "revision_sha256",
    }
    for kind in ("copperplate", "zonal"):
        source = Path(str(annual[kind]["execution_copy"]))
        source_bytes = source.read_bytes()
        parent = json.loads(source_bytes.decode("utf-8"))
        candidate = json.loads(source_bytes.decode("utf-8"))
        parent_revision = str(parent.get("revision_sha256") or "")
        if not parent_revision:
            raise ProductionGateError(
                "GF_PROMPT107_TWO_YEAR_PARENT_REVISION_MISSING",
                {"study_kind": kind, "source": str(source)},
            )
        candidate.update(
            {
                "id": f"prompt107-{kind}-2025-2026",
                "name": f"Prompt 107 {kind} causal 2025-2026 gate",
                "start_year": 2025,
                "end_year": 2026,
                "parent_revision_sha256": parent_revision,
                "revision_number": int(parent.get("revision_number", 0)) + 1,
            }
        )
        revision_manifest = packs.base_manifest
        if kind == "zonal":
            revision_manifest = resolve_zonal_pack_selection(
                candidate,
                base_pack_root=packs.base_root,
                base_manifest=packs.base_manifest,
                explicit_network_pack_root=packs.network_root,
            ).revision_manifest
        derived = attach_revision_identity(candidate, registry, revision_manifest)
        changes = _changed_leaf_paths(parent, derived)
        if changes != expected_changes:
            raise ProductionGateError(
                "GF_PROMPT107_TWO_YEAR_DERIVATION_INVALID",
                {
                    "study_kind": kind,
                    "expected_changed_leaf_paths": sorted(expected_changes),
                    "observed_changed_leaf_paths": sorted(changes),
                },
            )
        destination = (
            root / "studies" / "execution" / f"prompt107-{kind}-two-year-study.json"
        )
        digest = _write_immutable_json(destination, derived)
        if source.read_bytes() != source_bytes:
            raise ProductionGateError(
                "GF_PROMPT107_APPROVED_STUDY_SOURCE_CHANGED",
                {"study_kind": kind, "source": str(source)},
            )
        evidence[kind] = {
            "source": str(source),
            "execution_copy": str(destination),
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "execution_sha256": digest,
            "source_revision_sha256": parent_revision,
            "execution_revision_sha256": derived["revision_sha256"],
            "changed_leaf_paths": sorted(changes),
            "exact_derivation": [
                "freeze approved annual execution revision as parent",
                "extend end_year from 2025 to 2026",
                "advance revision_number and recompute revision_sha256",
            ],
        }
    return evidence


@lru_cache(maxsize=1)
def _approved_solver_gate_contract() -> dict[str, object]:
    """Resolve the one manifest/registry/runtime identity approved for Task 8."""

    from gridform_core.v2.module_manifest import workspace_registry
    from gridform_core.zonal_solver_contract import (
        load_solver_validation_registry,
        solver_stack_identity,
    )

    manifest = workspace_registry().manifest(
        "value-zonal-redispatch-balancing"
    ).to_dict()
    defaults = dict(dict(manifest.get("solver_contract") or {}).get("defaults") or {})
    stack = solver_stack_identity()
    matching = [
        entry
        for entry in load_solver_validation_registry()
        if entry.module_id == manifest.get("id")
        and entry.module_version == manifest.get("version")
        and entry.solver_contract_version == defaults.get("contract_version")
        and entry.scipy_version == stack.scipy_version
        and entry.highs_binary_sha256 == stack.highs_binary_sha256
        and entry.highs_identity == stack.highs_identity
        and entry.status == "candidate"
    ]
    if len(matching) != 1:
        raise ProductionGateError(
            "GF_PROMPT107_SOLVER_CONTRACT_MISMATCH",
            {
                "reason": "approved_manifest_registry_runtime_identity_missing",
                "module_id": manifest.get("id"),
                "module_version": manifest.get("version"),
                "solver_contract_version": defaults.get("contract_version"),
                "runtime_stack": stack.to_dict(),
                "matching_registry_entries": [vars(entry) for entry in matching],
            },
        )
    entry = matching[0]
    phase_contracts = {
        "primary_bid_cost": {
            "objective_key": "primary_bid_cost_gbp",
            "objective_unit": "GBP",
            "unit_floor": 1e-8,
        },
        "secondary_schedule_deviation": {
            "objective_key": "secondary_schedule_deviation_mwh",
            "objective_unit": "MWh",
            "unit_floor": 1e-9,
        },
        "physical_throughput": {
            "objective_key": "physical_throughput_mwh",
            "objective_unit": "MWh",
            "unit_floor": 1e-9,
        },
    }
    return {
        "manifest": manifest,
        "defaults": defaults,
        "stack": stack.to_dict(),
        "registry": vars(entry),
        "phase_contracts": phase_contracts,
    }


def _summary_value_matches(observed: object, expected: object) -> bool:
    if isinstance(expected, float):
        try:
            return math.isclose(float(observed), expected, rel_tol=1e-12, abs_tol=1e-15)
        except (TypeError, ValueError):
            return False
    return observed == expected


def _validate_solver_gate_evidence(
    database: Path,
    *,
    expected_periods: int,
) -> dict[str, object]:
    """Fail closed on v7 diagnostics and their independently queried summary."""

    from gridform_core.market_ledger import validate_market_ledger_file
    from gridform_core.zonal_results import (
        query_solver_validation_summary,
    )
    from gridform_core.zonal_solver_contract import (
        classify_lock,
        degradation_identity_matches,
    )

    public_ledger_validation = validate_market_ledger_file(database)

    expected_phases = {
        "primary_bid_cost",
        "secondary_schedule_deviation",
        "physical_throughput",
    }
    with _sqlite_evidence_connection(database) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='network_solver_diagnostics'"
        ).fetchone()
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM network_solver_diagnostics "
                "ORDER BY run_id, year, period, phase_id"
            )
        ] if table else []
        link_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='solver_declaration_link'"
        ).fetchone()
        solver_links = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM solver_declaration_link ORDER BY year, period"
            )
        ] if link_table else []

    authority = _approved_solver_gate_contract()
    manifest = dict(authority["manifest"])
    defaults = dict(authority["defaults"])
    stack = dict(authority["stack"])
    registry = dict(authority["registry"])
    phase_contracts = {
        str(key): dict(value)
        for key, value in dict(authority["phase_contracts"]).items()
    }
    contract_mismatches: list[dict[str, object]] = []

    def require_contract_value(
        row: Mapping[str, object],
        identity: tuple[str, int, int],
        field: str,
        expected: object,
    ) -> None:
        observed = row.get(field)
        if field == "presolve":
            observed = bool(observed)
        matches = (
            _summary_value_matches(observed, expected)
            if field == "computed_tolerance"
            else observed == expected
        )
        if not matches:
            contract_mismatches.append(
                {
                    "identity": identity,
                    "phase_id": row.get("phase_id"),
                    "field": field,
                    "expected": expected,
                    "observed": observed,
                }
            )

    active_solver_tolerance = max(
        float(defaults["primal_feasibility_tolerance"]),
        float(defaults["dual_feasibility_tolerance"]),
    )
    for row in rows:
        identity = (str(row["run_id"]), int(row["year"]), int(row["period"]))
        phase_id = str(row.get("phase_id") or "")
        phase_contract = phase_contracts.get(phase_id, {})
        objective_key = str(phase_contract.get("objective_key") or "")
        expected_values = {
            "module_id": manifest.get("id"),
            "module_version": manifest.get("version"),
            "solver_contract_version": defaults.get("contract_version"),
            "scipy_version": registry.get("scipy_version"),
            "highs_identity": registry.get("highs_identity"),
            "highs_binary_sha256": registry.get("highs_binary_sha256"),
            "method": "highs-ds",
            "presolve": True,
            "primal_feasibility_tolerance": defaults.get(
                "primal_feasibility_tolerance"
            ),
            "dual_feasibility_tolerance": defaults.get(
                "dual_feasibility_tolerance"
            ),
            "ipm_optimality_tolerance": None,
            "objective_unit": phase_contract.get("objective_unit"),
            "warning_ceiling": (
                float(defaults["warning_fraction"])
                * float(dict(defaults["validated_ceilings"])[objective_key])
                if objective_key else None
            ),
            "validated_ceiling": (
                dict(defaults["validated_ceilings"]).get(objective_key)
            ),
            "absolute_ceiling": (
                dict(defaults["absolute_ceilings"]).get(objective_key)
            ),
            "error_code": None,
        }
        for field, expected in expected_values.items():
            require_contract_value(row, identity, field, expected)
        nonzero_terms = int(row.get("nonzero_term_count") or 0)
        absolute_scale = float(row.get("absolute_term_scale") or 0.0)
        epsilon = sys.float_info.epsilon
        denominator = 1.0 - nonzero_terms * epsilon
        expected_tolerance = max(
            float(phase_contract.get("unit_floor") or 0.0),
            active_solver_tolerance * max(1.0, absolute_scale),
            (
                nonzero_terms * epsilon / denominator * absolute_scale
                if denominator > 0.0 else math.inf
            ),
        )
        require_contract_value(
            row, identity, "computed_tolerance", expected_tolerance
        )

    link_identities = {
        (int(row["year"]), int(row["period"])): row for row in solver_links
    }
    diagnostic_identities = {
        (int(row["year"]), int(row["period"])) for row in rows
    }
    if len(solver_links) != expected_periods or set(link_identities) != diagnostic_identities:
        contract_mismatches.append(
            {
                "field": "solver_declaration_link_identity",
                "expected_periods": expected_periods,
                "observed_links": len(solver_links),
                "diagnostic_identities": sorted(diagnostic_identities),
                "link_identities": sorted(link_identities),
            }
        )
    for identity, link in link_identities.items():
        if str(link.get("solver_status") or "") != "optimal":
            contract_mismatches.append(
                {
                    "identity": identity,
                    "field": "solver_status",
                    "expected": "optimal",
                    "observed": link.get("solver_status"),
                }
            )
    if contract_mismatches:
        raise ProductionGateError(
            "GF_PROMPT107_SOLVER_CONTRACT_MISMATCH",
            {
                "database": str(database),
                "registry_id": registry.get("registry_id"),
                "registry_status": registry.get("status"),
                "contract_mismatches": contract_mismatches,
            },
        )

    groups: dict[tuple[str, int, int], list[dict[str, object]]] = {}
    numerical_errors: list[dict[str, object]] = []
    for row in rows:
        identity = (str(row["run_id"]), int(row["year"]), int(row["period"]))
        groups.setdefault(identity, []).append(row)
        if not degradation_identity_matches(
            optimum=row["optimum"],
            achieved_final_value=row["achieved_final_value"],
            degradation=row["degradation"],
            computed_tolerance=row["computed_tolerance"],
        ):
            numerical_errors.append(
                {
                    "identity": identity,
                    "phase_id": row.get("phase_id"),
                    "error": (
                        "degradation does not equal max(0, "
                        "achieved_final_value - optimum)"
                    ),
                }
            )
            continue
        try:
            classification = classify_lock(
                float(row["degradation"]),
                float(row["computed_tolerance"]),
                float(row["validated_ceiling"]),
                float(row["warning_ceiling"]) / float(row["validated_ceiling"]),
                float(row["absolute_ceiling"]),
            ).status
        except (TypeError, ValueError, ArithmeticError, RuntimeError) as exc:
            numerical_errors.append(
                {"identity": identity, "phase_id": row.get("phase_id"), "error": str(exc)}
            )
            continue
        observed_class = str(row.get("validation_class") or "")
        if observed_class != classification:
            numerical_errors.append(
                {
                    "identity": identity,
                    "phase_id": row.get("phase_id"),
                    "observed_validation_class": observed_class,
                    "computed_validation_class": classification,
                    "degradation": row.get("degradation"),
                    "computed_tolerance": row.get("computed_tolerance"),
                    "validated_ceiling": row.get("validated_ceiling"),
                }
            )

    structural_errors = []
    if not public_ledger_validation.get("valid"):
        structural_errors.append(
            {
                "public_market_ledger_validation": public_ledger_validation,
            }
        )
    if len(groups) != expected_periods or len(rows) != expected_periods * 3:
        structural_errors.append(
            {
                "expected_periods": expected_periods,
                "observed_periods": len(groups),
                "expected_rows": expected_periods * 3,
                "observed_rows": len(rows),
            }
        )
    for identity, group_rows in groups.items():
        phases = {str(row.get("phase_id")) for row in group_rows}
        if len(group_rows) != 3 or phases != expected_phases:
            structural_errors.append(
                {"identity": identity, "row_count": len(group_rows), "phases": sorted(phases)}
            )
    if structural_errors or numerical_errors:
        raise ProductionGateError(
            "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO",
            {
                "database": str(database),
                "structural_errors": structural_errors,
                "numerical_errors": numerical_errors,
            },
        )

    summary = query_solver_validation_summary(database)
    if not isinstance(summary, dict):
        raise ProductionGateError(
            "GF_PROMPT107_SOLVER_SUMMARY_MISMATCH",
            {"database": str(database), "reason": "summary_missing"},
        )

    statuses = [str(row["validation_class"]) for row in rows]
    annual_status = (
        "COMPLETED_WITH_NUMERICAL_WARNING"
        if "COMPLETED_WITH_NUMERICAL_WARNING" in statuses
        else "GO_WITH_NUMERICAL_WARNING"
        if "GO_WITH_NUMERICAL_WARNING" in statuses
        else "GO"
    )
    expected_summary: dict[str, object] = {
        "schema_version": "value.solver-validation-summary/v1",
        "row_count": len(rows),
        "warning_periods": sum(
            any(str(row["validation_class"]) != "GO" for row in group_rows)
            for group_rows in groups.values()
        ),
        "unvalidated_periods": sum(
            any(
                str(row["validation_class"]) == "COMPLETED_WITH_NUMERICAL_WARNING"
                for row in group_rows
            )
            for group_rows in groups.values()
        ),
        "maximum_validated_ceiling_use": max(
            max(float(row["degradation"]), float(row["computed_tolerance"]))
            / float(row["validated_ceiling"])
            for row in rows
        ),
        "annual_status": annual_status,
        "method": "highs-ds",
        "solver_contract_version": defaults.get("contract_version"),
        "scipy_version": registry.get("scipy_version"),
        "highs_identity": registry.get("highs_identity"),
        "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
        "solver_validated": False,
    }
    expected_phase_summary: dict[str, dict[str, float | int]] = {}
    for row in rows:
        phase = expected_phase_summary.setdefault(
            str(row["phase_id"]),
            {
                "max_tolerance": 0.0,
                "max_degradation": 0.0,
                "periods_above_warning_fraction": 0,
                "periods_above_validated_ceiling": 0,
                "cumulative_absolute_degradation": 0.0,
            },
        )
        tolerance = float(row["computed_tolerance"])
        degradation = float(row["degradation"])
        ceiling_value = max(degradation, tolerance)
        phase["max_tolerance"] = max(float(phase["max_tolerance"]), tolerance)
        phase["max_degradation"] = max(
            float(phase["max_degradation"]), degradation
        )
        phase["periods_above_warning_fraction"] = int(
            phase["periods_above_warning_fraction"]
        ) + int(ceiling_value > 0.1 * float(row["validated_ceiling"]))
        phase["periods_above_validated_ceiling"] = int(
            phase["periods_above_validated_ceiling"]
        ) + int(ceiling_value > float(row["validated_ceiling"]))
        phase["cumulative_absolute_degradation"] = float(
            phase["cumulative_absolute_degradation"]
        ) + abs(degradation)
    mismatches = {
        key: {"expected": value, "observed": summary.get(key)}
        for key, value in expected_summary.items()
        if not _summary_value_matches(summary.get(key), value)
    }
    if summary.get("evidence_status") != "valid":
        mismatches["evidence_status"] = {
            "expected": "valid",
            "observed": summary.get("evidence_status"),
            "evidence_errors": summary.get("evidence_errors"),
        }
    observed_phases = dict(summary.get("phases") or {})
    for phase_id, expected_phase in expected_phase_summary.items():
        observed_phase = dict(observed_phases.get(phase_id) or {})
        for key, value in expected_phase.items():
            if not _summary_value_matches(observed_phase.get(key), value):
                mismatches[f"phases.{phase_id}.{key}"] = {
                    "expected": value,
                    "observed": observed_phase.get(key),
                }
    unexpected_phases = sorted(set(observed_phases) - set(expected_phase_summary))
    if unexpected_phases:
        mismatches["phases.unexpected"] = {
            "expected": [],
            "observed": unexpected_phases,
        }
    if mismatches:
        raise ProductionGateError(
            "GF_PROMPT107_SOLVER_SUMMARY_MISMATCH",
            {"database": str(database), "mismatches": mismatches},
        )
    if annual_status != "GO" or int(expected_summary["warning_periods"]):
        raise ProductionGateError(
            "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO",
            {
                "database": str(database),
                "gate_status": annual_status,
                "warning_periods": expected_summary["warning_periods"],
                "unvalidated_periods": expected_summary["unvalidated_periods"],
                "solver_validation_summary": summary,
            },
        )
    return {
        "summary": summary,
        "gate_status": annual_status,
        "row_count": len(rows),
    }


def _validate_application_output(
    *,
    stage_id: str,
    kind: str,
    run_id: str,
    output_dir: Path,
    expected_periods: int,
    expected_years: int,
    project: Mapping[str, object],
    result: Mapping[str, object],
) -> dict[str, object]:
    """Validate a completed immutable application bundle and extract gate evidence."""

    from gridform_core.bundle_validator import validate_run_bundle

    database = output_dir / "market" / "market.sqlite"
    metadata_path = output_dir / "market" / "metadata.json"
    attribution_path = output_dir / "network" / "vre-curtailment-attribution.json"
    required = (database, metadata_path, attribution_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ProductionGateError(
            "GF_PROMPT107_RUN_ARTIFACT_MISSING",
            {"run_id": run_id, "missing": missing},
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    attribution = json.loads(attribution_path.read_text(encoding="utf-8"))
    expected_total_periods = expected_periods * expected_years
    observed_periods = int(dict(metadata.get("rows") or {}).get("period_summary", -1))
    if observed_periods != expected_total_periods:
        raise ProductionGateError(
            "GF_PROMPT107_PERIOD_COUNT_MISMATCH",
            {
                "run_id": run_id,
                "expected_periods": expected_total_periods,
                "observed_periods": observed_periods,
            },
        )
    with _sqlite_evidence_connection(database) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        row_counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in sorted(
                tables.intersection(
                    {
                        "period_summary",
                        "zonal_period_accounting",
                        "vre_curtailment_period",
                        "vre_curtailment_detail",
                        "storage_state",
                        "physical_dispatch",
                        "redispatch_settlement",
                        "reliability_event",
                    }
                )
            )
        }
    if integrity != "ok":
        raise ProductionGateError(
            "GF_PROMPT107_SQLITE_INTEGRITY_FAILED",
            {"run_id": run_id, "integrity_check": integrity},
        )
    bundle = validate_run_bundle(output_dir)
    if not bundle.get("valid"):
        raise ProductionGateError(
            "GF_PROMPT107_RUN_BUNDLE_INVALID",
            {"run_id": run_id, "errors": bundle.get("errors")},
        )
    failed_period = None
    solver_validation: dict[str, object] | None = None
    maximum_residual = attribution.get("maximum_absolute_period_residual_mwh")
    maximum_tolerance = attribution.get("maximum_period_tolerance_mwh")
    if kind == "zonal":
        solver_validation = _validate_solver_gate_evidence(
            database, expected_periods=expected_total_periods
        )
        if attribution.get("capability_status") != "reconciled":
            raise ProductionGateError(
                "GF_PROMPT107_ATTRIBUTION_NOT_RECONCILED",
                {
                    "run_id": run_id,
                    "capability_status": attribution.get("capability_status"),
                    "reason_code": attribution.get("reason_code"),
                },
            )
        proof = dict(attribution.get("matched_counterfactual_proof") or {})
        if int(proof.get("period_count", -1)) != expected_total_periods:
            raise ProductionGateError(
                "GF_PROMPT107_ATTRIBUTION_PERIOD_COUNT_MISMATCH",
                {
                    "run_id": run_id,
                    "expected_periods": expected_total_periods,
                    "observed_periods": proof.get("period_count"),
                },
            )
        if stage_id != "smoke":
            failed_period = read_exact_failed_period_evidence(database)
    disk_bytes = sum(
        path.stat().st_size for path in output_dir.rglob("*") if path.is_file()
    )
    return {
        "status": "passed",
        "run_id": run_id,
        "project_id": project.get("id"),
        "project_revision_sha256": project.get("revision_sha256"),
        "engine": result.get("engine"),
        "expected_periods": expected_total_periods,
        "observed_periods": observed_periods,
        "years": expected_years,
        "sqlite_integrity_check": integrity,
        "row_counts": row_counts,
        "database_bytes": database.stat().st_size,
        "run_directory_bytes": disk_bytes,
        "writer_seconds": metadata.get("writer_seconds"),
        "maximum_energy_balance_residual_mwh": metadata.get(
            "maximum_absolute_energy_balance_residual_mwh"
        ),
        "maximum_attribution_residual_mwh": maximum_residual,
        "maximum_attribution_tolerance_mwh": maximum_tolerance,
        "attribution_status": attribution.get("capability_status"),
        "annual_totals": attribution.get("annual_totals"),
        "exact_failed_period_evidence": failed_period,
        "bundle_validation": bundle,
        "database_sha256": _sha256(database),
        "attribution_sha256": _sha256(attribution_path),
        "output_dir": str(output_dir),
        "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
        "solver_validation_summary": (
            solver_validation["summary"] if solver_validation else None
        ),
        "solver_validation_gate_status": (
            solver_validation["gate_status"] if solver_validation else None
        ),
    }


def _fixture_payload(path: Path) -> dict[str, object]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProductionGateError(
            "GF_PROMPT107_EXACT_FIXTURE_INVALID",
            {"fixture": str(path), "reason": "payload_not_object"},
        )
    return payload


def _execute_exact_period_stage(output_root: Path) -> Mapping[str, object]:
    """Replay exactly the two retained declared inputs into normal v7 evidence."""

    from gridform_core.builtin.scheme_c_1000twh.staged_psm import (
        _network_solver_diagnostic_rows,
    )
    from gridform_core.market_ledger import (
        SQLiteMarketLedger,
        SolverDeclarationLinkRow,
        ZonalAccountingLedgerRow,
        validate_market_ledger_file,
    )
    from gridform_core.staged_market_contracts import (
        BalancingInput,
        FlexibilityBid,
        contract_sha256,
    )
    from gridform_core.zonal_redispatch import (
        TOLERANCE,
        ZonalRedispatchBalancing,
        normalized_zonal_scientific_result_sha256,
    )

    stage_id = "exact-periods"
    stage_root = _validated_output_root(output_root) / "runs" / stage_id
    if stage_root.exists():
        raise ProductionGateError(
            "GF_PROMPT107_IMMUTABLE_OUTPUT_EXISTS",
            {"stage_id": stage_id, "output": str(stage_root)},
        )
    market_root = stage_root / "market"
    market_root.mkdir(parents=True, exist_ok=False)
    database = market_root / "market.sqlite"
    ledger = SQLiteMarketLedger(
        database,
        trace_level="full",
        semantic_metadata={
            "run_id": "prompt107-exact-periods",
            "run_parent_id": "prompt107-zonal-solver-contract-v1",
            "data_pack_id": BASE_PACK_ID,
            "network_pack_id": NETWORK_PACK_ID,
            "module_ids": ["value-zonal-redispatch-balancing@2.0.0"],
        },
    )
    started = time.perf_counter()
    replays: list[dict[str, object]] = []
    detailed_rows: list[dict[str, object]] = []
    print(f"PROMPT107_PHASE_START={stage_id}", flush=True)
    try:
        fixture_root = ROOT / "tests" / "fixtures" / "zonal_solver_failures"
        for case in EXACT_PERIOD_CASES:
            fixture = fixture_root / str(case["fixture"])
            if not fixture.is_file():
                raise ProductionGateError(
                    "GF_PROMPT107_EXACT_FIXTURE_MISSING",
                    {"fixture": str(fixture)},
                )
            observed_fixture_hash = _sha256(fixture)
            if observed_fixture_hash != case["fixture_sha256"]:
                raise ProductionGateError(
                    "GF_PROMPT107_EXACT_FIXTURE_HASH_MISMATCH",
                    {
                        "fixture": str(fixture),
                        "expected_sha256": case["fixture_sha256"],
                        "observed_sha256": observed_fixture_hash,
                    },
                )
            fixture_data = _fixture_payload(fixture)
            declared = dict(fixture_data.get("declared_input") or {})
            declared["bids"] = tuple(
                FlexibilityBid(**dict(item)) for item in declared.get("bids") or ()
            )
            model_input = BalancingInput(**declared)
            declared_hash = contract_sha256(model_input)
            if (
                declared_hash != case["declared_input_sha256"]
                or fixture_data.get("source_sha256") != declared_hash
            ):
                raise ProductionGateError(
                    "GF_PROMPT107_EXACT_DECLARED_INPUT_MISMATCH",
                    {
                        "fixture": str(fixture),
                        "expected_sha256": case["declared_input_sha256"],
                        "fixture_declared_sha256": fixture_data.get("source_sha256"),
                        "observed_sha256": declared_hash,
                    },
                )
            case_root = stage_root / "replays" / fixture.name.replace(".json.gz", "")
            result = ZonalRedispatchBalancing(evidence_root=case_root).clear(model_input)
            scientific_hash = normalized_zonal_scientific_result_sha256(result)
            if scientific_hash != case["scientific_result_sha256"]:
                raise ProductionGateError(
                    "GF_PROMPT107_EXACT_NONDETERMINISTIC_RESULT",
                    {
                        "fixture": str(fixture),
                        "expected_scientific_result_sha256": case[
                            "scientific_result_sha256"
                        ],
                        "observed_scientific_result_sha256": scientific_hash,
                    },
                )
            solver = dict(result.extensions.get("solver") or {})
            phase_statuses = {
                str(phase): dict(payload).get("status")
                for phase, payload in dict(solver.get("phases") or {}).items()
            }
            if set(phase_statuses) != {"primary", "secondary", "physical", "stable"} or any(
                status != 0 for status in phase_statuses.values()
            ):
                raise ProductionGateError(
                    "GF_PROMPT107_EXACT_PHASE_FAILURE",
                    {"fixture": str(fixture), "phase_statuses": phase_statuses},
                )
            raw_diagnostics = [
                dict(row)
                for row in result.extensions.get("network_solver_diagnostics") or ()
            ]
            if len(raw_diagnostics) != 3 or any(
                float(row["degradation"]) > float(row["computed_tolerance"])
                or float(row["degradation"]) > float(row["absolute_ceiling"])
                for row in raw_diagnostics
            ):
                raise ProductionGateError(
                    "GF_PROMPT107_EXACT_SOLVER_EVIDENCE_INVALID",
                    {"fixture": str(fixture), "diagnostics": raw_diagnostics},
                )
            if abs(float(result.energy_balance_residual_mwh)) > TOLERANCE:
                raise ProductionGateError(
                    "GF_PROMPT107_EXACT_PHYSICAL_VALIDATION_FAILED",
                    {
                        "fixture": str(fixture),
                        "energy_balance_residual_mwh": result.energy_balance_residual_mwh,
                        "physical_tolerance_mwh": TOLERANCE,
                    },
                )
            rows = _network_solver_diagnostic_rows(
                result,
                module_id="value-zonal-redispatch-balancing",
                module_version="1.2.0",
            )
            ledger.record_network_solver_diagnostics(rows)
            resource_cost = math.fsum(
                float(value) for value in result.resource_cost_gbp_by_class.values()
            )
            redispatch_settlement = math.fsum(
                float(value)
                for value in result.settlement_cashflow_gbp_by_agent.values()
            )
            ledger.record_zonal_accounting(
                (
                    ZonalAccountingLedgerRow(
                        year=model_input.year,
                        period=model_input.period,
                        period_id=model_input.period_id,
                        system_resource_cost_gbp=resource_cost,
                        network_constraint_cost_gbp=0.0,
                        national_settlement_gbp=0.0,
                        redispatch_settlement_gbp=redispatch_settlement,
                        policy_transfer_gbp=0.0,
                        perfect_forecast_resource_cost_gbp=resource_cost,
                        realised_copperplate_resource_cost_gbp=resource_cost,
                        zonal_resource_cost_gbp=resource_cost,
                        forecast_error_cost_gbp=0.0,
                        total_deviation_cost_gbp=0.0,
                        blackout_mwh=float(result.blackout_mwh),
                        counterfactual_realised_input_sha256=declared_hash,
                        accounting_status="reconciled",
                    ),
                )
            )
            solver_artifact = next(
                (
                    artifact.uri
                    for artifact in result.artifacts
                    if artifact.kind == "solver-diagnostics"
                ),
                None,
            )
            ledger.record_solver_links(
                (
                    SolverDeclarationLinkRow(
                        model_input.year,
                        model_input.period,
                        declared_hash,
                        str(fixture),
                        solver_artifact,
                        None,
                        str(solver.get("status") or "optimal"),
                    ),
                )
            )
            detailed_rows.extend(vars(row) for row in rows)
            replays.append(
                {
                    "fixture": fixture.name,
                    "fixture_path": str(fixture),
                    "fixture_sha256": observed_fixture_hash,
                    "declared_input_sha256": declared_hash,
                    "scientific_result_sha256": scientific_hash,
                    "phase_statuses": phase_statuses,
                    "energy_balance_residual_mwh": result.energy_balance_residual_mwh,
                    "physical_tolerance_mwh": TOLERANCE,
                    "network_solver_diagnostics": raw_diagnostics,
                    "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
                }
            )
        metadata = ledger.close()
        _write_json(market_root / "metadata.json", metadata)
        details_path = market_root / "network-solver-diagnostics.json"
        _write_json(
            details_path,
            {
                "schema_version": "value.network-solver-diagnostics/v7",
                "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
                "rows": detailed_rows,
            },
        )
        with _sqlite_evidence_connection(database) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        public_ledger_validation = validate_market_ledger_file(database)
        if not public_ledger_validation.get("valid"):
            raise ProductionGateError(
                "GF_PROMPT107_RUN_BUNDLE_INVALID",
                {
                    "database": str(database),
                    "public_market_ledger_validation": public_ledger_validation,
                },
            )
        solver_validation = _validate_solver_gate_evidence(
            database,
            expected_periods=len(EXACT_PERIOD_CASES),
        )
        summary_path = market_root / "solver-validation-summary.json"
        _write_json(summary_path, solver_validation["summary"])
        stage_report = {
            "stage_id": stage_id,
            "status": "passed",
            "mode": "retained_declared_input_replay",
            "replays": replays,
            "v7_database": str(database),
            "v7_database_sha256": _sha256(database),
            "v7_detailed_json": str(details_path),
            "v7_detailed_json_sha256": _sha256(details_path),
            "sqlite_integrity_check": integrity,
            "public_market_ledger_validation": public_ledger_validation,
            "solver_validation_summary": solver_validation["summary"],
            "solver_validation_summary_path": str(summary_path),
            "solver_validation_summary_sha256": _sha256(summary_path),
            "solver_validation_gate_status": solver_validation["gate_status"],
            "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "prompt105_ten_year_started": False,
        }
        _write_json(stage_root / "stage-report.json", stage_report)
        print(f"PROMPT107_PHASE_PASSED={stage_id}", flush=True)
        return stage_report
    except BaseException as exc:
        try:
            if not getattr(ledger, "_closed", False):
                ledger.close()
        except BaseException:
            pass
        failure = {
            "stage_id": stage_id,
            "status": "failed",
            "mode": "retained_declared_input_replay",
            "replays": replays,
            "error_code": (
                exc.code
                if isinstance(exc, ProductionGateError)
                else "GF_PROMPT107_EXACT_PERIOD_REPLAY_FAILED"
            ),
            "error": f"{type(exc).__name__}: {exc}",
            "error_evidence": (
                exc.evidence if isinstance(exc, ProductionGateError) else {}
            ),
            "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "prompt105_ten_year_started": False,
        }
        _write_json(stage_root / "stage-report.json", failure)
        print(
            f"PROMPT107_PHASE_FAILED={stage_id}:{failure['error_code']}",
            flush=True,
        )
        return failure


def _normalise_fingerprint_value(value: object, output_dir: Path) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _normalise_fingerprint_value(item, output_dir)
            for key, item in sorted(value.items(), key=lambda row: str(row[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalise_fingerprint_value(item, output_dir) for item in value]
    if isinstance(value, str):
        normalised = value.replace("\\", "/")
        root_text = str(output_dir).replace("\\", "/")
        if root_text in normalised:
            return normalised.replace(root_text, "<RUN_ROOT>")
    return value


def _deterministic_scientific_fingerprint(output_dir: Path) -> str:
    """Hash typed annual results and reconciled scientific ledger rows."""

    typed_path = output_dir / "year-results-v2.json"
    if not typed_path.is_file():
        raise ProductionGateError(
            "GF_PROMPT107_RERUN_ARTIFACT_MISSING",
            {"missing": str(typed_path)},
        )
    payload: dict[str, object] = {
        "year_results": json.loads(typed_path.read_text(encoding="utf-8"))
    }
    attribution_path = output_dir / "network" / "vre-curtailment-attribution.json"
    if attribution_path.is_file():
        payload["vre_curtailment_attribution"] = json.loads(
            attribution_path.read_text(encoding="utf-8")
        )
    database = output_dir / "market" / "market.sqlite"
    if database.is_file():
        scientific_tables = {
            "period_summary",
            "zonal_period_accounting",
            "network_solver_diagnostics",
            "solver_declaration_link",
            "vre_curtailment_period",
            "vre_curtailment_detail",
            "storage_state",
            "physical_dispatch",
            "redispatch_settlement",
            "reliability_event",
        }
        table_payload: dict[str, object] = {}
        with _sqlite_evidence_connection(database) as connection:
            connection.row_factory = sqlite3.Row
            available = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for table in sorted(available.intersection(scientific_tables)):
                rows = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
                table_payload[table] = sorted(
                    rows,
                    key=lambda row: json.dumps(
                        _normalise_fingerprint_value(row, output_dir),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ),
                )
        payload["market_ledger"] = table_payload
    encoded = json.dumps(
        _normalise_fingerprint_value(payload, output_dir),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _two_year_causality_evidence(output_dir: Path) -> dict[str, object]:
    """Prove one 2025 investment reaches a commissioned 2026 clearing object."""

    path = output_dir / "year-results-v2.json"
    if not path.is_file():
        raise ProductionGateError(
            "GF_PROMPT107_TWO_YEAR_CAUSALITY_MISSING",
            {"reason": "year_results_missing", "path": str(path)},
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raw = []
    by_year = {
        int(row.get("year")): row
        for row in raw
        if isinstance(row, Mapping) and row.get("year") is not None
    }
    first = dict(by_year.get(2025) or {})
    second = dict(by_year.get(2026) or {})
    admission = dict(first.get("planning_admission") or {})
    admitted = {
        str(project.get("project_id")): dict(project)
        for project in admission.get("admitted_projects") or []
        if isinstance(project, Mapping) and project.get("project_id")
    }
    admitted_events = {
        str(event.get("project_id"))
        for event in admission.get("events") or []
        if isinstance(event, Mapping)
        and event.get("event_type") == "admitted_model_investment"
    }
    proposals = [
        dict(proposal)
        for proposal in dict(first.get("investment") or {}).get("proposals") or []
        if isinstance(proposal, Mapping)
    ]
    advance = dict(second.get("planning_advance") or {})
    commission_events = {
        str(event.get("project_id")): dict(event)
        for event in advance.get("events") or []
        if isinstance(event, Mapping) and event.get("event_type") == "commissioned"
    }
    commissioned = {
        str(project.get("project_id")): dict(project)
        for project in advance.get("commissioned_projects") or []
        if isinstance(project, Mapping) and project.get("project_id")
    }
    operating_assets = {
        str(asset.get("asset_id")): dict(asset)
        for asset in dict(advance.get("operating_state") or {}).get("assets") or []
        if isinstance(asset, Mapping) and asset.get("asset_id")
    }
    market = dict(second.get("market") or {})
    generation = dict(market.get("generation_mwh_by_asset") or {})
    final_dispatch = dict(
        dict(market.get("extensions") or {}).get(
            "final_dispatch_mwh_by_physical_asset"
        )
        or {}
    )
    economic_fields = (
        "total_capex_gbp",
        "annual_fixed_opex_gbp",
        "economic_lifetime_years",
    )
    rejected: list[dict[str, object]] = []
    for project_id in sorted(set(admitted).intersection(commissioned)):
        proposal = next(
            (
                row
                for row in proposals
                if str(row.get("proposal_id", "")).replace("proposal", "project")
                == project_id
            ),
            None,
        )
        event = commission_events.get(project_id)
        asset_id = str(
            dict((event or {}).get("extensions") or {}).get(
                "commissioned_asset_id", f"commissioned:{project_id}"
            )
        )
        asset = operating_assets.get(asset_id)
        reasons: list[str] = []
        if proposal is None:
            reasons.append("2025_investment_proposal_missing")
        if project_id not in admitted_events:
            reasons.append("2025_admission_event_missing")
        if event is None:
            reasons.append("2026_commissioning_event_missing")
        if asset is None:
            reasons.append("2026_operating_asset_missing")
        extensions = dict((asset or {}).get("extensions") or {})
        record = dict(extensions.get("commissioned_asset_record") or {})
        project_extensions = dict(admitted[project_id].get("extensions") or {})
        inherited: dict[str, float] = {}
        for field in economic_fields:
            values = (
                project_extensions.get(field),
                extensions.get(field),
                record.get(field),
            )
            try:
                numbers = tuple(float(value) for value in values)
            except (TypeError, ValueError):
                reasons.append(f"{field}_missing")
                continue
            if not all(math.isfinite(value) for value in numbers):
                reasons.append(f"{field}_nonfinite")
            elif field == "economic_lifetime_years" and numbers[2] <= 0:
                reasons.append(f"{field}_invalid")
            elif numbers[0] != numbers[1] or numbers[1] != numbers[2]:
                reasons.append(f"{field}_not_inherited")
            else:
                inherited[field] = numbers[2]
        if asset_id not in generation and asset_id not in final_dispatch:
            reasons.append("2026_live_clearing_object_missing")
        if reasons:
            rejected.append(
                {"project_id": project_id, "asset_id": asset_id, "reasons": reasons}
            )
            continue
        return {
            "schema_version": "value.prompt107-two-year-causality/v1",
            "status": "attributable",
            "investment_year": 2025,
            "commissioning_year": 2026,
            "clearing_year": 2026,
            "proposal_id": proposal["proposal_id"],
            "project_id": project_id,
            "asset_id": asset_id,
            "inherited_economics": inherited,
            "generation_mwh": generation.get(asset_id),
            "final_dispatch_mwh": final_dispatch.get(asset_id),
            "evidence_path": str(path),
        }
    raise ProductionGateError(
        "GF_PROMPT107_TWO_YEAR_CAUSALITY_MISSING",
        {
            "reason": "no_attributable_2025_investment_to_2026_clearing_chain",
            "admitted_project_ids": sorted(admitted),
            "commissioned_project_ids": sorted(commissioned),
            "rejected_candidates": rejected,
            "evidence_path": str(path),
        },
    )


def build_application_stage_executor(
    output_root: Path,
    *,
    application_runner: Callable[..., Mapping[str, object]] | None = None,
    output_validator: Callable[..., Mapping[str, object]] | None = None,
) -> Callable[[str, RequiredPacks], Mapping[str, object]]:
    """Build the matched copperplate/zonal executor used by the production CLI."""

    if application_runner is None:
        from gridform_core.application import run_project_application

        application_runner = run_project_application
    validator = output_validator or _validate_application_output
    root = _lexical_absolute(output_root)

    def execute(stage_id: str, packs: RequiredPacks) -> Mapping[str, object]:
        root = _validated_output_root(output_root)
        if stage_id == "exact-periods":
            return _execute_exact_period_stage(root)
        if stage_id not in STAGE_MODES:
            raise ProductionGateError(
                "GF_PROMPT107_UNKNOWN_STAGE", {"stage_id": stage_id}
            )
        mode, expected_periods, expected_years = STAGE_MODES[stage_id]
        annual_copies = derive_execution_studies(root, packs)
        copied = (
            derive_two_year_execution_studies(root, packs, annual_copies)
            if stage_id == "two-year"
            else annual_copies
        )
        projects = {
            kind: json.loads(
                Path(row["execution_copy"]).read_text(encoding="utf-8")
            )
            for kind, row in copied.items()
        }
        for kind, project in projects.items():
            if project.get("data_pack_id") != BASE_PACK_ID:
                raise ProductionGateError(
                    "GF_PROMPT107_STUDY_BASE_PACK_MISMATCH",
                    {
                        "study_kind": kind,
                        "expected": BASE_PACK_ID,
                        "observed": project.get("data_pack_id"),
                    },
                )
            copied[kind]["project_id"] = project.get("id")

        print(f"PROMPT107_PHASE_START={stage_id}", flush=True)
        stage_started = time.perf_counter()
        runs: list[dict[str, object]] = []
        for kind in ("copperplate", "zonal"):
            run_id = f"prompt107-{stage_id}-{kind}"
            run_output = root / "runs" / stage_id / kind
            if run_output.exists():
                raise ProductionGateError(
                    "GF_PROMPT107_IMMUTABLE_OUTPUT_EXISTS",
                    {"stage_id": stage_id, "study_kind": kind, "output": str(run_output)},
                )
            run_output.mkdir(parents=True, exist_ok=False)
            console_log = run_output / "console.log"
            print(f"PROMPT107_RUN_START={run_id}", flush=True)
            started = time.perf_counter()
            try:
                with console_log.open("w", encoding="utf-8", newline="") as console, \
                     redirect_stdout(console), redirect_stderr(console):
                    result = application_runner(
                        projects[kind],
                        run_id=run_id,
                        pack_root=packs.base_root,
                        output_dir=run_output,
                        mode=mode,
                        network_pack_root=(packs.network_root if kind == "zonal" else None),
                    )
                evidence = dict(
                    validator(
                        stage_id=stage_id,
                        kind=kind,
                        run_id=run_id,
                        output_dir=run_output,
                        expected_periods=expected_periods,
                        expected_years=expected_years,
                        project=projects[kind],
                        result=result,
                    )
                )
                if stage_id == "24h":
                    evidence["deterministic_scientific_fingerprint"] = (
                        _deterministic_scientific_fingerprint(run_output)
                    )
                if stage_id == "two-year":
                    evidence["two_year_causality"] = _two_year_causality_evidence(
                        run_output
                    )
            except BaseException as exc:
                elapsed = time.perf_counter() - started
                failure = {
                    "stage_id": stage_id,
                    "status": "failed",
                    "study_copies": copied,
                    "runs": runs,
                    "failed_run": run_id,
                    "error_code": (
                        exc.code
                        if isinstance(exc, ProductionGateError)
                        else "GF_PROMPT107_APPLICATION_RUN_FAILED"
                    ),
                    "error": f"{type(exc).__name__}: {exc}",
                    "error_evidence": (
                        exc.evidence if isinstance(exc, ProductionGateError) else {}
                    ),
                    "failed_run_elapsed_seconds": round(elapsed, 6),
                    "elapsed_seconds": round(time.perf_counter() - stage_started, 6),
                    "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
                    "prompt105_ten_year_started": False,
                }
                _write_json(root / "runs" / stage_id / "stage-report.json", failure)
                print(
                    f"PROMPT107_RUN_FAILED={run_id}:{failure['error_code']}", flush=True
                )
                return failure
            evidence["elapsed_seconds"] = round(time.perf_counter() - started, 6)
            evidence["study_kind"] = kind
            runs.append(evidence)
            print(f"PROMPT107_RUN_PASSED={run_id}", flush=True)
        matched_reruns: list[dict[str, object]] = []
        deterministic_rerun_fingerprint: str | None = None
        if stage_id == "24h":
            primary_by_kind = {
                str(row["study_kind"]): row for row in runs
            }
            for kind in ("copperplate", "zonal"):
                run_id = f"prompt107-{stage_id}-{kind}"
                run_output = root / "runs" / "matched-rerun" / kind
                if run_output.exists():
                    raise ProductionGateError(
                        "GF_PROMPT107_IMMUTABLE_OUTPUT_EXISTS",
                        {
                            "stage_id": stage_id,
                            "study_kind": kind,
                            "output": str(run_output),
                        },
                    )
                run_output.mkdir(parents=True, exist_ok=False)
                console_log = run_output / "console.log"
                started = time.perf_counter()
                try:
                    with console_log.open("w", encoding="utf-8", newline="") as console, \
                         redirect_stdout(console), redirect_stderr(console):
                        result = application_runner(
                            projects[kind],
                            run_id=run_id,
                            pack_root=packs.base_root,
                            output_dir=run_output,
                            mode=mode,
                            network_pack_root=(
                                packs.network_root if kind == "zonal" else None
                            ),
                        )
                    evidence = dict(
                        validator(
                            stage_id=stage_id,
                            kind=kind,
                            run_id=run_id,
                            output_dir=run_output,
                            expected_periods=expected_periods,
                            expected_years=expected_years,
                            project=projects[kind],
                            result=result,
                        )
                    )
                    observed = _deterministic_scientific_fingerprint(run_output)
                    expected = str(
                        primary_by_kind[kind][
                            "deterministic_scientific_fingerprint"
                        ]
                    )
                    if observed != expected:
                        raise ProductionGateError(
                            "GF_PROMPT107_NONDETERMINISTIC_RERUN",
                            {
                                "study_kind": kind,
                                "primary_fingerprint": expected,
                                "rerun_fingerprint": observed,
                                "primary_output": str(
                                    root / "runs" / stage_id / kind
                                ),
                                "rerun_output": str(run_output),
                            },
                        )
                    evidence.update(
                        {
                            "study_kind": kind,
                            "deterministic_scientific_fingerprint": observed,
                            "matches_primary": True,
                            "elapsed_seconds": round(
                                time.perf_counter() - started, 6
                            ),
                        }
                    )
                    matched_reruns.append(evidence)
                except BaseException as exc:
                    failure = {
                        "stage_id": stage_id,
                        "status": "failed",
                        "study_copies": copied,
                        "runs": runs,
                        "matched_reruns": matched_reruns,
                        "failed_run": f"{run_id}:matched-rerun",
                        "error_code": (
                            exc.code
                            if isinstance(exc, ProductionGateError)
                            else "GF_PROMPT107_APPLICATION_RUN_FAILED"
                        ),
                        "error": f"{type(exc).__name__}: {exc}",
                        "error_evidence": (
                            exc.evidence
                            if isinstance(exc, ProductionGateError)
                            else {}
                        ),
                        "failed_run_elapsed_seconds": round(
                            time.perf_counter() - started, 6
                        ),
                        "elapsed_seconds": round(
                            time.perf_counter() - stage_started, 6
                        ),
                        "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
                        "prompt105_ten_year_started": False,
                    }
                    _write_json(
                        root / "runs" / stage_id / "stage-report.json", failure
                    )
                    return failure
            deterministic_rerun_fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        row["study_kind"]: row[
                            "deterministic_scientific_fingerprint"
                        ]
                        for row in matched_reruns
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        stage_report = {
            "stage_id": stage_id,
            "status": "passed",
            "mode": mode,
            "study_copies": copied,
            "runs": runs,
            "matched_reruns": matched_reruns,
            "deterministic_rerun_fingerprint": deterministic_rerun_fingerprint,
            "elapsed_seconds": round(time.perf_counter() - stage_started, 6),
            "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
            "prompt105_ten_year_started": False,
        }
        _write_json(root / "runs" / stage_id / "stage-report.json", stage_report)
        print(f"PROMPT107_PHASE_PASSED={stage_id}", flush=True)
        return stage_report

    return execute


def _network_pack_observation(data_root: Path) -> dict[str, object]:
    manifest_path = (
        Path(data_root).expanduser().resolve()
        / "data-workbench"
        / "installed-packs"
        / NETWORK_PACK_ID
        / "manifest.json"
    ).resolve()
    if not manifest_path.is_file():
        return {
            "status": "missing",
            "required_pack_id": NETWORK_PACK_ID,
            "manifest": str(manifest_path),
            "required_scientific_sha256": NETWORK_SCIENTIFIC_SHA256,
        }
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid",
            "required_pack_id": NETWORK_PACK_ID,
            "manifest": str(manifest_path),
            "read_error": f"{type(exc).__name__}: {exc}",
        }
    network = dict(payload.get("zonal_network_pack") or {}) if isinstance(payload, dict) else {}
    approval = dict(payload.get("owner_approval") or {}) if isinstance(payload, dict) else {}
    observed_hash = str(network.get("scientific_sha256") or "")
    approved_hash = str(approval.get("installed_scientific_sha256") or "")
    observed_id = str(payload.get("id") or "") if isinstance(payload, dict) else ""
    passed = (
        observed_id == NETWORK_PACK_ID
        and network.get("network_pack_id") == NETWORK_PACK_ID
        and approval.get("network_pack_id") == NETWORK_PACK_ID
        and observed_hash == NETWORK_SCIENTIFIC_SHA256
        and approved_hash == NETWORK_SCIENTIFIC_SHA256
    )
    return {
        "status": "verified" if passed else "invalid",
        "required_pack_id": NETWORK_PACK_ID,
        "observed_pack_id": observed_id,
        "manifest": str(manifest_path),
        "required_scientific_sha256": NETWORK_SCIENTIFIC_SHA256,
        "observed_scientific_sha256": observed_hash,
        "owner_approved_installed_scientific_sha256": approved_hash,
    }


def _output_root_contents(output_root: Path) -> list[dict[str, object]]:
    root = _validated_output_root(output_root)
    if not root.exists():
        return []
    if not root.is_dir():
        return [{"path": ".", "type": "not_a_directory"}]
    contents: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            contents.append(
                {"path": relative, "type": "symlink", "target": os.readlink(path)}
            )
        elif path.is_dir():
            contents.append({"path": relative, "type": "directory"})
        elif path.is_file():
            contents.append(
                {
                    "path": relative,
                    "type": "file",
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
        else:
            contents.append({"path": relative, "type": "other"})
    return contents


def build_production_preflight(
    output_root: Path,
    packs: RequiredPacks,
    data_root: Path,
    *,
    accepted_source_lineage: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate immutable inputs and execution identity before smoke launches."""

    from gridform_core.v2.module_manifest import workspace_registry
    from gridform_core.zonal_solver_contract import (
        load_solver_validation_registry,
        solver_stack_identity,
    )
    from scripts.verify_public_uk_pack import verify as verify_public_uk_pack

    output = _validated_output_root(output_root)
    disk_probe = output
    while not disk_probe.exists() and disk_probe != disk_probe.parent:
        disk_probe = disk_probe.parent
    disk = shutil.disk_usage(disk_probe)
    if disk.free < MINIMUM_PRODUCTION_FREE_BYTES:
        raise ProductionGateError(
            "GF_PROMPT107_INSUFFICIENT_DISK_SPACE",
            {
                "output_root": str(output),
                "free_bytes": disk.free,
                "minimum_free_bytes": MINIMUM_PRODUCTION_FREE_BYTES,
            },
        )
    runtime_lineage = _runtime_source_lineage()
    accepted_status = "not_supplied"
    if accepted_source_lineage is not None:
        accepted = (
            dict(accepted_source_lineage)
            if isinstance(accepted_source_lineage, Mapping)
            else {}
        )
        mismatched_fields = sorted(
            field
            for field in ("head", "tree_id")
            if accepted.get(field) != runtime_lineage.get(field)
        )
        if (
            accepted.get("schema_version")
            != "value.prompt107-accepted-source-lineage/v1"
            or mismatched_fields
        ):
            raise ProductionGateError(
                "GF_PROMPT107_SOURCE_LINEAGE_MISMATCH",
                {
                    "expected_schema_version": "value.prompt107-accepted-source-lineage/v1",
                    "observed_schema_version": accepted.get("schema_version"),
                    "mismatched_fields": mismatched_fields,
                    "observed_head": runtime_lineage.get("head"),
                    "observed_tree_id": runtime_lineage.get("tree_id"),
                    "accepted_head": accepted.get("head"),
                    "accepted_tree_id": accepted.get("tree_id"),
                },
            )
        accepted_status = "verified_external_acceptance"
    observed_source_hashes: dict[str, str] = {}
    for name, expected_hash in PROMPT104_SOURCE_HASHES.items():
        path = ROOT / "publication" / name
        observed_hash = _sha256(path) if path.is_file() else ""
        observed_source_hashes[name] = observed_hash
        if observed_hash != expected_hash:
            raise ProductionGateError(
                "GF_PROMPT107_PROMPT104_SOURCE_HASH_MISMATCH",
                {
                    "source": str(path),
                    "expected_sha256": expected_hash,
                    "observed_sha256": observed_hash,
                },
            )
    source_projects = {
        kind: json.loads(path.read_text(encoding="utf-8"))
        for kind, path in {
            "copperplate": ROOT
            / "publication"
            / "prompt104-staged-copperplate-study.json",
            "zonal": ROOT / "publication" / "prompt104-zonal-study.json",
        }.items()
    }
    observed_project_differences = _changed_leaf_paths(
        source_projects["copperplate"], source_projects["zonal"]
    )
    allowed_project_differences = {
        "id",
        "market_configuration.balancing_module_id",
        "market_configuration.network_pack_id",
        "market_configuration.zonal_demand_mode",
        "maturity_acknowledgements.extension:value-zonal-redispatch-extension@1.0.0",
        "maturity_acknowledgements.module:value-zonal-redispatch-balancing@1.0.0",
        "modules.balancing",
        "name",
        "parent_revision_sha256",
        "revision_number",
        "revision_sha256",
        "selected_extensions",
    }
    if observed_project_differences != allowed_project_differences:
        raise ProductionGateError(
            "GF_PROMPT107_MATCHED_SCENARIO_AUTHORITY_MISMATCH",
            {
                "allowed_differences": sorted(allowed_project_differences),
                "observed_differences": sorted(observed_project_differences),
            },
        )
    base_verification = verify_public_uk_pack(packs.base_root)
    if base_verification.get("decision") != "GO":
        raise ProductionGateError(
            "GF_PROMPT107_BASE_PACK_VERIFICATION_FAILED", base_verification
        )
    network_verification = _network_pack_observation(data_root)
    if network_verification.get("status") != "verified":
        raise ProductionGateError(
            "GF_PROMPT107_NETWORK_PACK_VERIFICATION_FAILED", network_verification
        )
    registry = workspace_registry()
    zonal_manifest = registry.manifest("value-zonal-redispatch-balancing").to_dict()
    if zonal_manifest.get("version") != "1.2.0":
        raise ProductionGateError(
            "GF_PROMPT107_MODULE_GRAPH_MISMATCH",
            {
                "module_id": "value-zonal-redispatch-balancing",
                "expected_version": "1.2.0",
                "observed_version": zonal_manifest.get("version"),
            },
        )
    solver_defaults = dict(dict(zonal_manifest.get("solver_contract") or {}).get("defaults") or {})
    expected_solver_defaults = {
        "method": "highs-ds",
        "presolve": True,
        "primal_feasibility_tolerance": 1e-9,
        "dual_feasibility_tolerance": 1e-9,
        "contract_version": "value.zonal-lexicographic/v2",
    }
    if any(solver_defaults.get(key) != value for key, value in expected_solver_defaults.items()):
        raise ProductionGateError(
            "GF_PROMPT107_SOLVER_CONTRACT_MISMATCH",
            {
                "expected": expected_solver_defaults,
                "observed": solver_defaults,
            },
        )
    stack = solver_stack_identity()
    matching_registry_entries = [
        entry
        for entry in load_solver_validation_registry()
        if entry.module_id == "value-zonal-redispatch-balancing"
        and entry.module_version == "1.2.0"
        and entry.solver_contract_version == "value.zonal-lexicographic/v2"
        and entry.scipy_version == stack.scipy_version
        and entry.highs_binary_sha256 == stack.highs_binary_sha256
        and entry.highs_identity == stack.highs_identity
    ]
    if len(matching_registry_entries) != 1 or matching_registry_entries[0].status != "candidate":
        raise ProductionGateError(
            "GF_PROMPT107_SOLVER_REGISTRY_DISPOSITION_MISMATCH",
            {
                "expected_status": "candidate",
                "matching_entries": [vars(entry) for entry in matching_registry_entries],
            },
        )
    registry_entry = matching_registry_entries[0]
    lineage = derive_execution_studies(output, packs)
    preflight = {
        "status": "PERMITTED_UNVALIDATED",
        "execution_permission": "PERMITTED_UNVALIDATED",
        "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
        "project_revision": {
            **runtime_lineage,
            "source_root": str(ROOT),
            "accepted_source_lineage_status": accepted_status,
        },
        "disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
            "minimum_free_bytes": MINIMUM_PRODUCTION_FREE_BYTES,
        },
        "base_pack_verification": {
            **base_verification,
            "manifest": str((packs.base_root / "manifest.json").resolve()),
            "manifest_sha256": _sha256(packs.base_root / "manifest.json"),
        },
        "network_pack_verification": {
            **network_verification,
            "manifest_sha256": _sha256(packs.network_root / "manifest.json"),
        },
        "module_graph": {
            "zonal_module_id": zonal_manifest["id"],
            "zonal_module_version": zonal_manifest["version"],
            "zonal_module_scientific_version": zonal_manifest["scientific_version"],
            "solver_contract": zonal_manifest["solver_contract"],
        },
        "solver_stack": {
            **stack.to_dict(),
            "registry_id": registry_entry.registry_id,
            "registry_status": registry_entry.status,
        },
        "solver_contract_defaults": solver_defaults,
        "matched_scenario_authority": {
            "status": "verified",
            "allowed_project_differences": sorted(allowed_project_differences),
            "observed_project_differences": sorted(observed_project_differences),
        },
        "original_prompt104_hashes": observed_source_hashes,
        "study_lineage": lineage,
        "substitution_attempted": False,
        "prompt105_ten_year_started": False,
    }
    _write_json(output / "production-preflight.json", preflight)
    return preflight


def execute_production_gate(
    *,
    through: str,
    output_root: Path,
    data_root: Path,
    execute_stage: Callable[[str, RequiredPacks], Mapping[str, object]],
    accepted_source_lineage: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Resolve inputs, execute requested gates in order, and persist stop evidence."""

    if through not in THROUGH_INDEX:
        raise ValueError(f"through must be one of {', '.join(STAGE_ORDER)}")
    required_stages = list(STAGE_ORDER[: THROUGH_INDEX[through] + 1])
    generated_at = datetime.now(timezone.utc).isoformat()
    declared_output = _lexical_absolute(output_root)
    try:
        output = _validated_output_root(declared_output)
    except ProductionGateError as exc:
        output_preflight = {
            "path": str(declared_output),
            "existed_before": os.path.lexists(declared_output),
            "contents": [],
            "status": "blocked_redirected",
            **exc.evidence,
        }
        return {
            "schema_version": "value.prompt107-production-gate/v1",
            "generated_at_utc": generated_at,
            "through": through,
            "decision": "BLOCKED",
            "release_decision": "NO-GO",
            "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
            "output_root_preflight": output_preflight,
            "invoked_stages": [],
            "stages": [],
            "stop_decision": {
                "error_code": exc.code,
                "stopped_before": "smoke",
                "not_started": required_stages,
                "prompt105_ten_year_started": False,
            },
            "error_evidence": exc.evidence,
        }
    existed_before = output.exists()
    contents = _output_root_contents(output)
    output_preflight = {
        "path": str(output),
        "existed_before": existed_before,
        "contents": contents,
        "status": "verified_empty" if not contents else "blocked_nonempty",
    }
    if contents:
        return {
            "schema_version": "value.prompt107-production-gate/v1",
            "generated_at_utc": generated_at,
            "through": through,
            "decision": "BLOCKED",
            "release_decision": "NO-GO",
            "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
            "output_root_preflight": output_preflight,
            "invoked_stages": [],
            "stages": [],
            "stop_decision": {
                "error_code": "GF_PROMPT107_OUTPUT_ROOT_NOT_EMPTY",
                "stopped_before": "smoke",
                "not_started": required_stages,
                "prompt105_ten_year_started": False,
            },
        }
    output.mkdir(parents=True, exist_ok=True)
    try:
        packs = resolve_required_packs(data_root)
    except ProductionGateError as exc:
        base_status = "missing" if exc.code == "GF_PROMPT107_BASE_PACK_MISSING" else "invalid"
        report: dict[str, object] = {
            "schema_version": "value.prompt107-production-gate/v1",
            "generated_at_utc": generated_at,
            "through": through,
            "decision": "NO-GO",
            "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
            "output_root_preflight": output_preflight,
            "pack_resolution": {
                "user_data_root": str(Path(data_root).expanduser().resolve()),
                "base_pack": {
                    "status": base_status,
                    "required_pack_id": BASE_PACK_ID,
                    **exc.evidence,
                },
                "network_pack": _network_pack_observation(data_root),
                "substitution_attempted": False,
            },
            "invoked_stages": [],
            "stages": [],
            "stop_decision": {
                "error_code": exc.code,
                "stopped_before": "smoke",
                "not_started": required_stages,
                "prompt105_ten_year_started": False,
            },
            "error_evidence": exc.evidence,
        }
        _write_json(output / "prompt107-production-gate.json", report)
        return report

    try:
        production_preflight = build_production_preflight(
            output,
            packs,
            data_root,
            accepted_source_lineage=accepted_source_lineage,
        )
    except (OSError, ValueError, ProductionGateError) as exc:
        code = (
            exc.code
            if isinstance(exc, ProductionGateError)
            else "GF_PROMPT107_PRODUCTION_PREFLIGHT_FAILED"
        )
        evidence = exc.evidence if isinstance(exc, ProductionGateError) else {
            "error": f"{type(exc).__name__}: {exc}"
        }
        report = {
            "schema_version": "value.prompt107-production-gate/v1",
            "generated_at_utc": generated_at,
            "through": through,
            "decision": "NO-GO",
            "release_decision": "NO-GO",
            "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
            "output_root_preflight": output_preflight,
            "production_preflight": {
                "status": "failed",
                "error_code": code,
                "error_evidence": evidence,
            },
            "invoked_stages": [],
            "stages": [],
            "stop_decision": {
                "error_code": code,
                "stopped_before": "smoke",
                "not_started": required_stages,
                "prompt105_ten_year_started": False,
            },
        }
        _write_json(output / "prompt107-production-gate.json", report)
        return report

    invoked: list[str] = []

    def invoke(stage_id: str) -> Mapping[str, object]:
        invoked.append(stage_id)
        return execute_stage(stage_id, packs)

    sequence = run_stage_sequence(through, invoke)
    passed = sequence["status"] == "passed"
    report = {
        "schema_version": "value.prompt107-production-gate/v1",
        "generated_at_utc": generated_at,
        "through": through,
        "decision": "GO" if passed else "NO-GO",
        "solver_stack_validation_status": SOLVER_STACK_VALIDATION_STATUS,
        "output_root_preflight": output_preflight,
        "production_preflight": production_preflight,
        "release_decision": (
            "GO" if passed and through == "two-year"
            else "PENDING_LATER_GATES" if passed
            else "NO-GO"
        ),
        "pack_resolution": {
            "user_data_root": str(Path(data_root).expanduser().resolve()),
            "base_pack": {
                "status": "verified",
                "pack_id": BASE_PACK_ID,
                "manifest": str((packs.base_root / "manifest.json").resolve()),
            },
            "network_pack": _network_pack_observation(data_root),
            "substitution_attempted": False,
        },
        "invoked_stages": invoked,
        "stages": sequence["stages"],
        "stop_decision": {
            "error_code": (
                None
                if passed
                else (sequence["stages"][-1].get("error_code") or "GF_PROMPT107_STAGE_FAILED")
            ),
            "stopped_after": sequence["stopped_after"],
            "not_started": sequence["not_started"],
            "prompt105_ten_year_started": False,
        },
    }
    _write_json(output / "prompt107-production-gate.json", report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    from gridform_core.runtime_paths import user_data_root

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--through", choices=STAGE_ORDER, required=True
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/prompt107-production-gate"),
    )
    parser.add_argument(
        "--accepted-source-lineage",
        type=Path,
        help="Optional external value.prompt107-accepted-source-lineage/v1 JSON",
    )
    args = parser.parse_args(argv)
    output = args.output_root if args.output_root.is_absolute() else ROOT / args.output_root
    accepted_source_lineage = None
    if args.accepted_source_lineage is not None:
        accepted_source_lineage = json.loads(
            args.accepted_source_lineage.read_text(encoding="utf-8")
        )
    report = execute_production_gate(
        through=args.through,
        output_root=output,
        data_root=user_data_root(),
        execute_stage=build_application_stage_executor(output),
        accepted_source_lineage=accepted_source_lineage,
    )
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "through": report["through"],
                "stop_decision": report["stop_decision"],
                "output": str((output / "prompt107-production-gate.json").resolve()),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if report["decision"] == "GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
