"""High-throughput SQLite market evidence with a near-zero-cost null writer."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import importlib.util
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import (
    Iterable,
    Iterator,
    Mapping,
    Protocol,
    TextIO,
    get_args,
    get_type_hints,
)

from .clearing_inputs import ClearingInputRow, ClearingOutcomeRow
from .errors import InvariantError
from .market_integrity import (
    EVIDENCE_PROJECTION_SCHEMA,
    SCIENCE_PROJECTION_SCHEMA,
    ZERO_SHA256,
    annual_evidence_payload,
    initial_evidence_hash,
    initial_science_hash,
    next_evidence_hash,
    next_science_hash,
    projection_sha256,
    seal_year,
)
from .market_ownership import MarketLedgerOwnershipLease
from .subannual_checkpoint import LedgerPrefixIdentity
from .v2.contracts import JsonContract
from .vre_curtailment_attribution import VRECurtailmentAttribution
from .zonal_demand_alignment import SUPPORTED_ZONAL_DEMAND_MODES
from .zonal_solver_contract import (
    classify_lock,
    degradation_identity_matches,
    gbp1_stored_policy_matches,
    gbp1_stored_policy_requirement,
    validate_stored_lock_evidence,
)

_LOGGER = logging.getLogger(__name__)


SCHEMA_VERSION = "value.market-ledger/v8"
LEGACY_WRITER_SCHEMA_VERSION = "value.market-ledger/v7"
LEGACY_SCHEMA_VERSIONS = {
    "value.market-ledger/v4",
    "value.market-ledger/v5",
    "value.market-ledger/v6",
    "value.market-ledger/v7",
}
ATTRIBUTION_SCHEMA_VERSIONS = {
    "value.market-ledger/v6",
    "value.market-ledger/v7",
    SCHEMA_VERSION,
}
INDEX_SCHEMA_VERSION = "value.market-index/v2"
TABLE_ROLE_SCHEMA_VERSION = "value.market-table-roles/v1"
COMMON_TABLES = frozenset({
    "zonal_period_accounting",
    "vre_curtailment_period",
    "zonal_demand_alignment",
    "zone_period_summary",
    "boundary_period_summary",
    "solver_declaration_link",
})
FULL_ONLY_TABLES = frozenset({
    "orders",
    "storage_state",
    "physical_dispatch",
    "clearing_inputs",
    "clearing_outcomes",
    "vre_curtailment_detail",
    "zonal_resource_dispatch",
    "redispatch_settlement",
    "network_solver_diagnostics",
})
PERIOD_INDEXED_V8_TABLES = (
    "period_summary", "orders", "storage_state", "physical_dispatch",
    "clearing_inputs", "zonal_period_summary", "zonal_period_accounting",
    "vre_curtailment_period", "vre_curtailment_detail",
    "zonal_demand_alignment", "zone_period_summary",
    "boundary_period_summary", "zonal_resource_dispatch",
    "redispatch_settlement", "solver_declaration_link",
    "network_solver_diagnostics", "dispatch_summary", "storage_summary",
    "redispatch_summary", "period_integrity",
)
_CONTEXT_REGISTRY_METADATA_KEYS = frozenset({
    "run_context_sha256",
    "year_context_sha256",
    "run_context_schema_version",
    "year_context_schema_version",
    "run_context_artifact_path",
    "year_context_artifact_path",
})
_ACTIVE_LEDGER: "MarketLedger" | None = None


def _finite(value: object, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc
    if isinstance(value, bool) or not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _nonnegative(value: object, field_name: str) -> float:
    number = _finite(value, field_name)
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return number


def _required_text(value: object, field_name: str) -> str:
    text = str(value)
    if not text.strip():
        raise ValueError(f"{field_name} is required")
    return text


def _sha256_text(value: object, field_name: str) -> str:
    text = _required_text(value, field_name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field_name} must be a lowercase SHA-256")
    return text


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PeriodLedgerRow:
    year: int
    period: int
    stage: str
    forecast_demand_mwh: float
    real_demand_mwh: float
    accepted_supply_mwh: float
    storage_charge_mwh: float
    storage_discharge_mwh: float
    flexible_demand_mwh: float
    export_mwh: float
    vre_available_mwh: float
    vre_accepted_mwh: float
    curtailed_mwh: float
    import_mwh: float
    clearing_price_gbp_per_mwh: float
    physical_resource_cost_gbp: float
    market_payment_gbp: float
    policy_transfer_gbp: float
    blackout_mwh: float
    excess_mwh: float
    energy_balance_residual_mwh: float
    compatibility_adjustment_mwh: float = 0.0
    raw_energy_balance_residual_mwh: float = 0.0


@dataclass(frozen=True)
class DispatchSummaryRow:
    year: int
    period: int
    stage: str
    zone_id: str
    technology: str
    accepted_dispatch_mwh: float

    def __post_init__(self) -> None:
        for name in ("stage", "zone_id", "technology"):
            _required_text(getattr(self, name), name)
        _nonnegative(self.accepted_dispatch_mwh, "accepted_dispatch_mwh")


@dataclass(frozen=True)
class StorageSummaryRow:
    year: int
    period: int
    zone_id: str
    technology: str
    charge_mwh: float
    discharge_mwh: float
    closing_soc_mwh: float

    def __post_init__(self) -> None:
        for name in ("zone_id", "technology"):
            _required_text(getattr(self, name), name)
        for name in ("charge_mwh", "discharge_mwh", "closing_soc_mwh"):
            _nonnegative(getattr(self, name), name)


@dataclass(frozen=True)
class RedispatchSummaryRow:
    year: int
    period: int
    zone_id: str
    technology: str
    direction: str
    accepted_delta_mwh: float
    resource_cost_gbp: float

    def __post_init__(self) -> None:
        for name in ("zone_id", "technology"):
            _required_text(getattr(self, name), name)
        if self.direction not in {"up", "down"}:
            raise ValueError("direction must be up or down")
        _nonnegative(self.accepted_delta_mwh, "accepted_delta_mwh")
        _finite(self.resource_cost_gbp, "resource_cost_gbp")


@dataclass(frozen=True)
class PeriodIntegrity:
    year: int
    period: int
    previous_science_hash: str
    science_hash: str
    previous_evidence_hash: str
    evidence_hash: str
    common_projection_sha256: str
    stored_rows_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "previous_science_hash",
            "science_hash",
            "previous_evidence_hash",
            "evidence_hash",
            "common_projection_sha256",
            "stored_rows_sha256",
        ):
            _sha256_text(getattr(self, name), name)


@dataclass(frozen=True)
class MarketLedgerBoundary(JsonContract):
    year: int
    last_committed_period: int
    period_count: int
    run_context_sha256: str
    year_context_sha256: str
    science_root: str
    evidence_root: str
    common_projection_sha256: str
    stored_rows_sha256: str
    trace_level: str
    row_counts_json: str
    trace_coverage_json: str
    database_sha256: str
    committed_prefix_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.year, bool) or not isinstance(self.year, int):
            raise ValueError("year must be an integer")
        if (
            isinstance(self.last_committed_period, bool)
            or not isinstance(self.last_committed_period, int)
            or self.last_committed_period < 0
        ):
            raise ValueError("last_committed_period must be non-negative")
        if self.period_count != self.last_committed_period + 1:
            raise ValueError("period_count must describe a continuous 0..N prefix")
        for name in (
            "run_context_sha256", "year_context_sha256", "science_root",
            "evidence_root", "common_projection_sha256", "stored_rows_sha256",
            "database_sha256", "committed_prefix_sha256",
        ):
            _sha256_text(getattr(self, name), name)
        if self.trace_level not in {"summary", "full"}:
            raise ValueError("trace_level must be summary or full")
        for name in ("row_counts_json", "trace_coverage_json"):
            try:
                value = json.loads(getattr(self, name))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{name} must contain canonical JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{name} must contain a JSON object")

    @property
    def ledger_prefix_identity(self) -> LedgerPrefixIdentity:
        return LedgerPrefixIdentity(
            database_sha256=self.database_sha256,
            committed_period_count=self.period_count,
            maximum_committed_period=self.last_committed_period,
            committed_prefix_sha256=self.committed_prefix_sha256,
        )


@dataclass(frozen=True)
class MarketPeriodBatch:
    """Every row that may be committed for one scientific market period."""

    period: PeriodLedgerRow
    dispatch_summary: tuple[DispatchSummaryRow, ...] = ()
    storage_summary: tuple[StorageSummaryRow, ...] = ()
    redispatch_summary: tuple[RedispatchSummaryRow, ...] = ()
    common_rows: Mapping[str, tuple[object, ...]] = field(default_factory=dict)
    full_rows: Mapping[str, tuple[object, ...]] = field(default_factory=dict)
    science_payload: Mapping[str, object] = field(default_factory=dict)
    evidence_payload: Mapping[str, object] = field(default_factory=dict)
    run_context_sha256: str = ZERO_SHA256
    year_context_sha256: str = ZERO_SHA256

    def __post_init__(self) -> None:
        if not isinstance(self.period, PeriodLedgerRow):
            raise ValueError("MarketPeriodBatch.period must be a PeriodLedgerRow")
        common = MappingProxyType({
            str(table): tuple(rows) for table, rows in dict(self.common_rows).items()
        })
        full = MappingProxyType({
            str(table): tuple(rows) for table, rows in dict(self.full_rows).items()
        })
        object.__setattr__(self, "dispatch_summary", tuple(self.dispatch_summary))
        object.__setattr__(self, "storage_summary", tuple(self.storage_summary))
        object.__setattr__(self, "redispatch_summary", tuple(self.redispatch_summary))
        object.__setattr__(self, "common_rows", common)
        object.__setattr__(self, "full_rows", full)
        _validate_table_roles(common, full)
        science_payload = _build_common_projection(
            self.period,
            self.dispatch_summary,
            self.storage_summary,
            self.redispatch_summary,
            common,
        )
        supplied_science = dict(self.science_payload)
        if supplied_science and supplied_science != science_payload:
            raise ValueError(
                "science_payload must equal the fixed common-table projection"
            )
        evidence_payload = {
            "schema_version": EVIDENCE_PROJECTION_SCHEMA,
            "period": {"year": self.period.year, "period": self.period.period},
        }
        supplied_evidence = dict(self.evidence_payload)
        if supplied_evidence and supplied_evidence != evidence_payload:
            raise ValueError(
                "evidence_payload must equal the fixed period evidence seed"
            )
        object.__setattr__(
            self, "science_payload", MappingProxyType(science_payload)
        )
        object.__setattr__(
            self, "evidence_payload", MappingProxyType(evidence_payload)
        )
        _sha256_text(self.run_context_sha256, "run_context_sha256")
        _sha256_text(self.year_context_sha256, "year_context_sha256")
        if self.science_payload.get("schema_version") != SCIENCE_PROJECTION_SCHEMA:
            raise ValueError("science_payload has an unsupported schema_version")
        if self.evidence_payload.get("schema_version") != EVIDENCE_PROJECTION_SCHEMA:
            raise ValueError("evidence_payload has an unsupported schema_version")
        for rows in (
            self.dispatch_summary,
            self.storage_summary,
            self.redispatch_summary,
            *common.values(),
            *full.values(),
        ):
            for row in rows:
                if hasattr(row, "year") and int(getattr(row, "year")) != self.period.year:
                    raise ValueError("batch row year does not match period")
                if hasattr(row, "period") and int(getattr(row, "period")) != self.period.period:
                    raise ValueError("batch row period does not match period")


@lru_cache(maxsize=None)
def _resolved_row_type_hints(row_type: type[object]) -> Mapping[str, object]:
    return MappingProxyType(get_type_hints(row_type))


def _canonical_row_mapping(
    row_type: type[object], row: Mapping[str, object]
) -> dict[str, object]:
    type_hints = _resolved_row_type_hints(row_type)
    canonical: dict[str, object] = {}
    for field_name, value in row.items():
        field_type = type_hints.get(field_name)
        field_type_args = get_args(field_type)
        if field_type is bool:
            if type(value) is not bool:
                raise ValueError(f"{field_name} must be boolean")
            canonical[field_name] = value
        elif field_type is float:
            number = _finite(value, field_name)
            canonical[field_name] = 0.0 if number == 0.0 else number
        elif (
            len(field_type_args) == 2
            and float in field_type_args
            and type(None) in field_type_args
        ):
            if value is None:
                canonical[field_name] = None
            else:
                number = _finite(value, field_name)
                canonical[field_name] = 0.0 if number == 0.0 else number
        elif field_type is int:
            if isinstance(value, bool):
                raise ValueError(f"{field_name} must be an integer")
            if isinstance(value, int):
                canonical[field_name] = int(value)
            elif (
                isinstance(value, float)
                and math.isfinite(value)
                and value.is_integer()
            ):
                canonical[field_name] = int(value)
            else:
                raise ValueError(f"{field_name} must be an integer")
        else:
            canonical[field_name] = value
    return canonical


def _canonical_database_row_mapping(
    row_type: type[object], row: Mapping[str, object]
) -> dict[str, object]:
    type_hints = _resolved_row_type_hints(row_type)
    materialized = dict(row)
    for field_name, field_type in type_hints.items():
        if field_type is not bool or field_name not in materialized:
            continue
        value = materialized[field_name]
        if type(value) is not int or value not in {0, 1}:
            raise ValueError(f"{field_name} must be a SQLite boolean bit")
        materialized[field_name] = bool(value)
    return _canonical_row_mapping(row_type, materialized)


def _canonical_row_dicts(
    row_type: type[object], rows: Iterable[object]
) -> list[dict[str, object]]:
    materialized = [
        _canonical_row_mapping(row_type, asdict(row)) for row in rows
    ]
    return sorted(
        materialized,
        key=lambda row: json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
    )


def _validate_table_roles(
    common_rows: Mapping[str, tuple[object, ...]],
    full_rows: Mapping[str, tuple[object, ...]],
) -> None:
    overlap = COMMON_TABLES.intersection(FULL_ONLY_TABLES)
    if overlap:
        raise ValueError(
            "Market table-role contract overlaps: " + ", ".join(sorted(overlap))
        )
    common_names = set(common_rows)
    full_names = set(full_rows)
    misplaced_common = common_names.intersection(FULL_ONLY_TABLES)
    if misplaced_common:
        raise ValueError(
            "full-only market tables cannot be common rows: "
            + ", ".join(sorted(misplaced_common))
        )
    misplaced_full = full_names.intersection(COMMON_TABLES)
    if misplaced_full:
        raise ValueError(
            "common table cannot be stored as full-only detail: "
            + ", ".join(sorted(misplaced_full))
        )
    unknown = (common_names | full_names).difference(
        COMMON_TABLES | FULL_ONLY_TABLES
    )
    if unknown:
        raise ValueError(
            "Unsupported market period batch table: "
            + ", ".join(sorted(unknown))
        )
    contracts = _batch_table_contracts()
    for table, rows in (*common_rows.items(), *full_rows.items()):
        row_type, _ = contracts[table]
        if any(not isinstance(row, row_type) for row in rows):
            raise ValueError(f"{table} batch contains the wrong row contract")


def _batch_table_contracts() -> dict[str, tuple[type[object], int]]:
    return {
        "zonal_period_accounting": (ZonalAccountingLedgerRow, 16),
        "vre_curtailment_period": (VRECurtailmentPeriodRow, 20),
        "zonal_demand_alignment": (ZonalDemandAlignmentLedgerRow, 10),
        "zone_period_summary": (ZonePeriodLedgerRow, 9),
        "boundary_period_summary": (BoundaryPeriodLedgerRow, 9),
        "solver_declaration_link": (SolverDeclarationLinkRow, 7),
        "orders": (OrderLedgerRow, 14),
        "storage_state": (StorageStateRow, 8),
        "physical_dispatch": (PhysicalDispatchRow, 9),
        "clearing_inputs": (ClearingInputRow, 8),
        "clearing_outcomes": (ClearingOutcomeRow, 3),
        "vre_curtailment_detail": (VRECurtailmentDetailRow, 20),
        "zonal_resource_dispatch": (ZonalResourceDispatchRow, 13),
        "redispatch_settlement": (RedispatchSettlementRow, 14),
        "network_solver_diagnostics": (NetworkSolverDiagnosticRow, 29),
    }


def _period_table_row_types() -> dict[str, type[object]]:
    return {
        "period_summary": PeriodLedgerRow,
        "dispatch_summary": DispatchSummaryRow,
        "storage_summary": StorageSummaryRow,
        "redispatch_summary": RedispatchSummaryRow,
        **{
            table: contract[0]
            for table, contract in _batch_table_contracts().items()
        },
    }


def _build_common_projection(
    period: PeriodLedgerRow,
    dispatch_summary: Iterable[DispatchSummaryRow],
    storage_summary: Iterable[StorageSummaryRow],
    redispatch_summary: Iterable[RedispatchSummaryRow],
    common_rows: Mapping[str, Iterable[object]],
) -> dict[str, object]:
    contracts = _batch_table_contracts()
    return {
        "schema_version": SCIENCE_PROJECTION_SCHEMA,
        "period": _canonical_row_mapping(PeriodLedgerRow, asdict(period)),
        "dispatch_summary": _canonical_row_dicts(
            DispatchSummaryRow, dispatch_summary
        ),
        "storage_summary": _canonical_row_dicts(
            StorageSummaryRow, storage_summary
        ),
        "redispatch_summary": _canonical_row_dicts(
            RedispatchSummaryRow, redispatch_summary
        ),
        "common_rows": {
            table: _canonical_row_dicts(
                contracts[table][0], common_rows.get(table, ())
            )
            for table in sorted(COMMON_TABLES)
        },
    }


def build_market_period_batch(
    *,
    period: PeriodLedgerRow,
    dispatch_summary: Iterable[DispatchSummaryRow] = (),
    storage_summary: Iterable[StorageSummaryRow] = (),
    redispatch_summary: Iterable[RedispatchSummaryRow] = (),
    common_rows: Mapping[str, Iterable[object]] | None = None,
    full_rows: Mapping[str, Iterable[object]] | None = None,
    run_context_sha256: str = ZERO_SHA256,
    year_context_sha256: str = ZERO_SHA256,
) -> MarketPeriodBatch:
    """Build the stable common-science and stored-evidence projections."""

    dispatch = tuple(dispatch_summary)
    storage = tuple(storage_summary)
    redispatch = tuple(redispatch_summary)
    common = {
        str(table): tuple(rows)
        for table, rows in dict(common_rows or {}).items()
    }
    details = {
        str(table): tuple(rows)
        for table, rows in dict(full_rows or {}).items()
    }
    return MarketPeriodBatch(
        period=period,
        dispatch_summary=dispatch,
        storage_summary=storage,
        redispatch_summary=redispatch,
        common_rows=common,
        full_rows=details,
        run_context_sha256=run_context_sha256,
        year_context_sha256=year_context_sha256,
    )


@dataclass(frozen=True)
class OrderLedgerRow:
    order_id: str
    year: int
    period: int
    stage: str
    asset_id: str
    asset_type: str
    side: str
    offer_price_gbp_per_mwh: float
    offered_mwh: float
    accepted_mwh: float
    status: str
    reason_code: str
    physical_resource_cost_gbp: float
    market_payment_gbp: float


@dataclass(frozen=True)
class StorageStateRow:
    year: int
    period: int
    asset_id: str
    state_of_charge_mwh: float
    charge_mwh: float
    discharge_mwh: float
    power_capacity_mw: float
    energy_capacity_mwh: float


@dataclass(frozen=True)
class StorageEnergyAuditRow:
    """Per-asset storage energy audit of one period (P0-4 S4, P3-14, P5-11).

    ``charge_input_mwh``/``discharge_output_mwh`` are grid side; the other
    quantities are stored-side MWh.  ``identity_residual_mwh`` is
    ``soc_start + charge_stored - discharge_withdrawn - self_discharge -
    tail_writeoff - soc_end`` (rounding only).
    """

    year: int
    period: int
    asset_id: str
    soc_start_mwh: float
    charge_input_mwh: float
    charge_stored_mwh: float
    discharge_output_mwh: float
    discharge_withdrawn_mwh: float
    self_discharge_mwh: float
    tail_writeoff_mwh: float
    soc_end_mwh: float
    identity_residual_mwh: float


@dataclass(frozen=True)
class StorageYearBoundaryRow:
    """Storage state at an operating-year boundary (P0-4 S4, P3-14).

    ``carry_policy`` names what the PSM does with the closing state: the
    default PSM builds new batteries every year, so its closing state of
    charge is ``discarded`` (doctoral frozen behaviour, booked not changed).
    """

    year: int
    asset_id: str
    opening_soc_mwh: float
    closing_soc_mwh: float
    carried_forward_mwh: float
    discarded_mwh: float
    carry_policy: str


@dataclass(frozen=True)
class SurplusRoutingLedgerRow:
    """Pre-balancing surplus routing of one period and source class (P0-4 S5, Q7).

    ``in_dispatch`` surplus is already inside the accepted supply (must-run
    excess, scheduled output above real demand); ``out_of_dispatch`` surplus
    is VRE availability the ahead market did not accept.  ``spilled_mwh`` of
    the in-dispatch row is W_in (non_vre_spill); ``unrealised_mwh`` is the
    in-dispatch surplus the kernel routed or spilled that the accepted supply
    never contained.  available = storage + export + flexible + dispatch +
    curtailed + spilled + unrealised.
    """

    year: int
    period: int
    source_class: str
    available_mwh: float
    to_storage_mwh: float
    to_export_mwh: float
    to_flexible_mwh: float
    spilled_mwh: float
    to_dispatch_mwh: float
    curtailed_mwh: float
    unrealised_mwh: float


@dataclass(frozen=True)
class PhysicalDispatchRow:
    """One final, non-duplicated physical flow after all market stages.

    ``energy_mwh`` is always the magnitude shown to users, except that a named
    compatibility adjustment may be signed. ``balance_component_mwh`` carries
    the signed contribution to the public single-node balance. Context flows
    such as exports and curtailment have a zero balance component because the
    retained VALUE boundary reports them outside demand-serving dispatch.
    """

    year: int
    period: int
    asset_id: str
    technology: str
    flow_type: str
    energy_mwh: float
    balance_component_mwh: float
    evidence_scope: str
    source_stage: str = "final_dispatch"


@dataclass(frozen=True)
class ZonalPeriodLedgerRow:
    year: int
    period: int
    period_id: str
    system_resource_cost_gbp: float
    network_constraint_cost_gbp: float
    national_settlement_gbp: float
    redispatch_settlement_gbp: float
    policy_transfer_gbp: float
    perfect_forecast_resource_cost_gbp: float
    realised_copperplate_resource_cost_gbp: float
    zonal_resource_cost_gbp: float
    forecast_error_cost_gbp: float
    total_deviation_cost_gbp: float
    economic_ahead_unused_vre_mwh: float
    realised_availability_change_vre_mwh: float
    network_added_curtailment_vre_mwh: float
    total_curtailment_vre_mwh: float
    curtailment_identity_residual_mwh: float
    blackout_mwh: float
    counterfactual_realised_input_sha256: str
    accounting_status: str

    def __post_init__(self) -> None:
        _required_text(self.period_id, "period_id")
        _required_text(self.accounting_status, "accounting_status")
        for name in (
            "system_resource_cost_gbp", "network_constraint_cost_gbp",
            "national_settlement_gbp", "redispatch_settlement_gbp",
            "policy_transfer_gbp", "perfect_forecast_resource_cost_gbp",
            "realised_copperplate_resource_cost_gbp", "zonal_resource_cost_gbp",
            "forecast_error_cost_gbp", "total_deviation_cost_gbp",
            "economic_ahead_unused_vre_mwh", "realised_availability_change_vre_mwh",
            "network_added_curtailment_vre_mwh", "total_curtailment_vre_mwh",
            "curtailment_identity_residual_mwh", "blackout_mwh",
        ):
            _finite(getattr(self, name), name)
        if len(self.counterfactual_realised_input_sha256) != 64:
            raise ValueError("counterfactual_realised_input_sha256 must be a SHA-256")

    @classmethod
    def from_accounting(cls, accounting: object) -> "ZonalPeriodLedgerRow":
        return cls(
            year=int(getattr(accounting, "year")),
            period=int(getattr(accounting, "period")),
            period_id=str(getattr(accounting, "period_id")),
            system_resource_cost_gbp=float(getattr(accounting, "system_resource_cost_gbp")),
            network_constraint_cost_gbp=float(getattr(accounting, "transmission_constraint_resource_cost_gbp")),
            national_settlement_gbp=float(getattr(accounting, "national_settlement_gbp")),
            redispatch_settlement_gbp=float(getattr(accounting, "redispatch_settlement_gbp")),
            policy_transfer_gbp=float(getattr(accounting, "policy_transfer_gbp")),
            perfect_forecast_resource_cost_gbp=float(getattr(accounting, "perfect_forecast_resource_cost_gbp")),
            realised_copperplate_resource_cost_gbp=float(getattr(accounting, "realised_copperplate_resource_cost_gbp")),
            zonal_resource_cost_gbp=float(getattr(accounting, "zonal_resource_cost_gbp")),
            forecast_error_cost_gbp=float(getattr(accounting, "forecast_error_cost_gbp")),
            total_deviation_cost_gbp=float(getattr(accounting, "total_deviation_cost_gbp")),
            economic_ahead_unused_vre_mwh=float(getattr(accounting, "economic_ahead_unused_vre_mwh")),
            realised_availability_change_vre_mwh=float(getattr(accounting, "realised_availability_change_vre_mwh")),
            network_added_curtailment_vre_mwh=float(getattr(accounting, "network_added_curtailment_vre_mwh")),
            total_curtailment_vre_mwh=float(getattr(accounting, "total_curtailment_vre_mwh")),
            curtailment_identity_residual_mwh=float(getattr(accounting, "curtailment_identity_residual_mwh")),
            blackout_mwh=float(getattr(accounting, "blackout_mwh")),
            counterfactual_realised_input_sha256=str(getattr(accounting, "counterfactual_realised_input_sha256")),
            accounting_status=str(getattr(accounting, "accounting_status")),
        )


@dataclass(frozen=True)
class ZonalAccountingLedgerRow:
    """Cost, settlement and reliability evidence independent of curtailment."""

    year: int
    period: int
    period_id: str
    system_resource_cost_gbp: float
    network_constraint_cost_gbp: float
    national_settlement_gbp: float
    redispatch_settlement_gbp: float
    policy_transfer_gbp: float
    perfect_forecast_resource_cost_gbp: float
    realised_copperplate_resource_cost_gbp: float
    zonal_resource_cost_gbp: float
    forecast_error_cost_gbp: float
    total_deviation_cost_gbp: float
    blackout_mwh: float
    counterfactual_realised_input_sha256: str
    accounting_status: str

    def __post_init__(self) -> None:
        _required_text(self.period_id, "period_id")
        _required_text(self.accounting_status, "accounting_status")
        _sha256_text(
            self.counterfactual_realised_input_sha256,
            "counterfactual_realised_input_sha256",
        )
        for name in (
            "system_resource_cost_gbp",
            "network_constraint_cost_gbp",
            "national_settlement_gbp",
            "redispatch_settlement_gbp",
            "policy_transfer_gbp",
            "perfect_forecast_resource_cost_gbp",
            "realised_copperplate_resource_cost_gbp",
            "zonal_resource_cost_gbp",
            "forecast_error_cost_gbp",
            "total_deviation_cost_gbp",
            "blackout_mwh",
        ):
            _finite(getattr(self, name), name)

    @classmethod
    def from_accounting(cls, accounting: object) -> "ZonalAccountingLedgerRow":
        network_constraint_cost = (
            getattr(accounting, "network_constraint_cost_gbp")
            if hasattr(accounting, "network_constraint_cost_gbp")
            else getattr(accounting, "transmission_constraint_resource_cost_gbp")
        )
        return cls(
            year=int(getattr(accounting, "year")),
            period=int(getattr(accounting, "period")),
            period_id=str(getattr(accounting, "period_id")),
            system_resource_cost_gbp=float(
                getattr(accounting, "system_resource_cost_gbp")
            ),
            network_constraint_cost_gbp=float(network_constraint_cost),
            national_settlement_gbp=float(
                getattr(accounting, "national_settlement_gbp")
            ),
            redispatch_settlement_gbp=float(
                getattr(accounting, "redispatch_settlement_gbp")
            ),
            policy_transfer_gbp=float(getattr(accounting, "policy_transfer_gbp")),
            perfect_forecast_resource_cost_gbp=float(
                getattr(accounting, "perfect_forecast_resource_cost_gbp")
            ),
            realised_copperplate_resource_cost_gbp=float(
                getattr(accounting, "realised_copperplate_resource_cost_gbp")
            ),
            zonal_resource_cost_gbp=float(
                getattr(accounting, "zonal_resource_cost_gbp")
            ),
            forecast_error_cost_gbp=float(
                getattr(accounting, "forecast_error_cost_gbp")
            ),
            total_deviation_cost_gbp=float(
                getattr(accounting, "total_deviation_cost_gbp")
            ),
            blackout_mwh=float(getattr(accounting, "blackout_mwh")),
            counterfactual_realised_input_sha256=str(
                getattr(accounting, "counterfactual_realised_input_sha256")
            ),
            accounting_status=str(getattr(accounting, "accounting_status")),
        )


@dataclass(frozen=True)
class VRECurtailmentPeriodRow:
    year: int
    period: int
    period_id: str
    realised_available_vre_mwh: float
    perfect_reference_dispatch_mwh: float
    copperplate_reference_dispatch_mwh: float
    zonal_final_dispatch_mwh: float
    economic_curtailment_mwh: float
    forecast_added_curtailment_mwh: float
    forecast_avoided_curtailment_mwh: float
    redispatch_added_curtailment_mwh: float
    redispatch_avoided_curtailment_mwh: float
    redispatch_net_impact_mwh: float
    total_curtailment_mwh: float
    curtailment_rate: float
    identity_residual_mwh: float
    validation_tolerance_mwh: float
    accounting_status: str
    counterfactual_realised_input_sha256: str
    attribution_method_id: str

    def __post_init__(self) -> None:
        for name in (
            "period_id",
            "accounting_status",
            "attribution_method_id",
        ):
            _required_text(getattr(self, name), name)
        _sha256_text(
            self.counterfactual_realised_input_sha256,
            "counterfactual_realised_input_sha256",
        )
        for name in (
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
            "curtailment_rate",
            "identity_residual_mwh",
            "validation_tolerance_mwh",
        ):
            _finite(getattr(self, name), name)

    @classmethod
    def from_attribution(
        cls, attribution: VRECurtailmentAttribution
    ) -> "VRECurtailmentPeriodRow":
        period = attribution.period
        return cls(
            year=period.year,
            period=period.period,
            period_id=period.period_id,
            realised_available_vre_mwh=period.realised_available_vre_mwh,
            perfect_reference_dispatch_mwh=period.perfect_reference_dispatch_mwh,
            copperplate_reference_dispatch_mwh=period.copperplate_reference_dispatch_mwh,
            zonal_final_dispatch_mwh=period.zonal_final_dispatch_mwh,
            economic_curtailment_mwh=period.economic_curtailment_mwh,
            forecast_added_curtailment_mwh=period.forecast_added_curtailment_mwh,
            forecast_avoided_curtailment_mwh=period.forecast_avoided_curtailment_mwh,
            redispatch_added_curtailment_mwh=period.redispatch_added_curtailment_mwh,
            redispatch_avoided_curtailment_mwh=period.redispatch_avoided_curtailment_mwh,
            redispatch_net_impact_mwh=period.redispatch_net_impact_mwh,
            total_curtailment_mwh=period.total_curtailment_mwh,
            curtailment_rate=period.curtailment_rate,
            identity_residual_mwh=period.identity_residual_mwh,
            validation_tolerance_mwh=period.tolerance_mwh,
            accounting_status=period.status,
            counterfactual_realised_input_sha256=period.realised_input_sha256,
            attribution_method_id=period.attribution_method_id,
        )


@dataclass(frozen=True)
class VRECurtailmentDetailRow:
    year: int
    period: int
    period_id: str
    asset_id: str
    owner_id: str
    zone_id: str
    technology: str
    bid_tranche_id: str
    realised_available_vre_mwh: float
    perfect_reference_dispatch_mwh: float
    copperplate_reference_dispatch_mwh: float
    zonal_final_dispatch_mwh: float
    economic_curtailment_mwh: float
    forecast_added_curtailment_mwh: float
    forecast_avoided_curtailment_mwh: float
    redispatch_added_curtailment_mwh: float
    redispatch_avoided_curtailment_mwh: float
    redispatch_net_impact_mwh: float
    total_curtailment_mwh: float
    evidence_level: str

    def __post_init__(self) -> None:
        for name in (
            "period_id",
            "asset_id",
            "owner_id",
            "zone_id",
            "technology",
            "bid_tranche_id",
            "evidence_level",
        ):
            _required_text(getattr(self, name), name)
        for name in (
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
        ):
            _finite(getattr(self, name), name)

    @classmethod
    def from_attribution(
        cls, attribution: VRECurtailmentAttribution
    ) -> tuple["VRECurtailmentDetailRow", ...]:
        period = attribution.period
        return tuple(
            cls(
                year=period.year,
                period=period.period,
                period_id=period.period_id,
                asset_id=detail.asset_id,
                owner_id=detail.owner_id,
                zone_id=detail.zone_id,
                technology=detail.canonical_technology,
                bid_tranche_id=detail.bid_tranche_id,
                realised_available_vre_mwh=detail.realised_available_vre_mwh,
                perfect_reference_dispatch_mwh=detail.perfect_reference_dispatch_mwh,
                copperplate_reference_dispatch_mwh=detail.copperplate_reference_dispatch_mwh,
                zonal_final_dispatch_mwh=detail.zonal_final_dispatch_mwh,
                economic_curtailment_mwh=detail.economic_curtailment_mwh,
                forecast_added_curtailment_mwh=detail.forecast_added_curtailment_mwh,
                forecast_avoided_curtailment_mwh=detail.forecast_avoided_curtailment_mwh,
                redispatch_added_curtailment_mwh=detail.redispatch_added_curtailment_mwh,
                redispatch_avoided_curtailment_mwh=detail.redispatch_avoided_curtailment_mwh,
                redispatch_net_impact_mwh=detail.redispatch_net_impact_mwh,
                total_curtailment_mwh=detail.total_curtailment_mwh,
                evidence_level="deterministic_reference_allocation",
            )
            for detail in attribution.details
        )


@dataclass(frozen=True)
class ZonalDemandAlignmentLedgerRow:
    year: int
    period: int
    period_id: str
    demand_mode: str
    research_real_demand_mwh: float
    research_forecast_demand_mwh: float
    network_national_demand_mwh: float
    scale_factor: float
    aligned_zonal_total_mwh: float
    conservation_residual_mwh: float

    def __post_init__(self) -> None:
        _required_text(self.period_id, "period_id")
        if self.demand_mode not in SUPPORTED_ZONAL_DEMAND_MODES:
            raise ValueError("demand_mode is not supported")
        for name in (
            "research_real_demand_mwh",
            "research_forecast_demand_mwh",
            "network_national_demand_mwh",
            "scale_factor",
            "aligned_zonal_total_mwh",
        ):
            _nonnegative(getattr(self, name), name)
        _finite(self.conservation_residual_mwh, "conservation_residual_mwh")


@dataclass(frozen=True)
class ZonePeriodLedgerRow:
    year: int
    period: int
    zone_id: str
    demand_mwh: float
    ahead_injection_mwh: float
    final_injection_mwh: float
    signed_adjustment_mwh: float
    load_shedding_mwh: float
    net_position_mwh: float

    def __post_init__(self) -> None:
        _required_text(self.zone_id, "zone_id")
        _nonnegative(self.demand_mwh, "demand_mwh")
        _nonnegative(self.load_shedding_mwh, "load_shedding_mwh")
        for name in ("ahead_injection_mwh", "final_injection_mwh", "signed_adjustment_mwh", "net_position_mwh"):
            _finite(getattr(self, name), name)


@dataclass(frozen=True)
class BoundaryPeriodLedgerRow:
    year: int
    period: int
    boundary_id: str
    transfer_mwh: float
    forward_capacity_mwh: float
    reverse_capacity_mwh: float
    utilisation_fraction: float
    boundary_shadow_value_gbp_per_mwh: float
    shadow_value_semantics: str

    def __post_init__(self) -> None:
        _required_text(self.boundary_id, "boundary_id")
        _required_text(self.shadow_value_semantics, "shadow_value_semantics")
        _finite(self.transfer_mwh, "transfer_mwh")
        _nonnegative(self.forward_capacity_mwh, "forward_capacity_mwh")
        _nonnegative(self.reverse_capacity_mwh, "reverse_capacity_mwh")
        _nonnegative(self.utilisation_fraction, "utilisation_fraction")
        _finite(self.boundary_shadow_value_gbp_per_mwh, "boundary_shadow_value_gbp_per_mwh")
        if "not_zonal_price_or_cash_cost" not in self.shadow_value_semantics:
            raise ValueError("boundary shadow value must be labelled as a diagnostic, not a price or cash cost")


@dataclass(frozen=True)
class ZonalResourceDispatchRow:
    year: int
    period: int
    asset_id: str
    agent_id: str
    zone_id: str
    technology: str
    ahead_dispatch_mwh: float
    final_dispatch_mwh: float
    signed_adjustment_mwh: float
    final_soc_mwh: float
    charge_mwh: float
    discharge_mwh: float
    physical_resource_cost_gbp: float

    def __post_init__(self) -> None:
        for name in ("asset_id", "agent_id", "zone_id", "technology"):
            _required_text(getattr(self, name), name)
        for name in ("ahead_dispatch_mwh", "final_dispatch_mwh", "signed_adjustment_mwh"):
            _finite(getattr(self, name), name)
        for name in ("final_soc_mwh", "charge_mwh", "discharge_mwh", "physical_resource_cost_gbp"):
            _nonnegative(getattr(self, name), name)


@dataclass(frozen=True)
class RedispatchSettlementRow:
    bid_id: str
    year: int
    period: int
    agent_id: str
    asset_id: str
    zone_id: str
    technology: str
    direction: str
    offered_mwh: float
    accepted_delta_mwh: float
    bid_price_gbp_per_mwh: float
    cashflow_to_agent_gbp: float
    status: str
    reason_code: str

    def __post_init__(self) -> None:
        for name in ("bid_id", "agent_id", "asset_id", "zone_id", "technology", "status", "reason_code"):
            _required_text(getattr(self, name), name)
        if self.direction not in {"up", "down"}:
            raise ValueError("direction must be up or down")
        _nonnegative(self.offered_mwh, "offered_mwh")
        for name in ("accepted_delta_mwh", "bid_price_gbp_per_mwh", "cashflow_to_agent_gbp"):
            _finite(getattr(self, name), name)
        if not math.isclose(
            self.accepted_delta_mwh * self.bid_price_gbp_per_mwh,
            self.cashflow_to_agent_gbp,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("redispatch cashflow must equal signed accepted delta times bid price")


@dataclass(frozen=True)
class ReliabilityEventRow:
    event_id: str
    year: int
    start_period: int
    end_period: int
    observed_half_hours: int
    event_duration_hours: float
    unserved_mwh: float
    affected_zones_json: str
    maximum_deficit_mwh: float
    metric_semantics: str

    def __post_init__(self) -> None:
        _required_text(self.event_id, "event_id")
        _required_text(self.metric_semantics, "metric_semantics")
        if self.end_period < self.start_period or self.observed_half_hours <= 0:
            raise ValueError("reliability event chronology is invalid")
        _nonnegative(self.event_duration_hours, "event_duration_hours")
        _nonnegative(self.unserved_mwh, "unserved_mwh")
        _nonnegative(self.maximum_deficit_mwh, "maximum_deficit_mwh")
        parsed = json.loads(self.affected_zones_json)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("affected_zones_json must encode a list of zone IDs")
        if self.metric_semantics != "observed_loss_of_load_chronology_not_statistical_lole":
            raise ValueError("a single chronology must not be labelled statistical LOLE")


@dataclass(frozen=True)
class SolverDeclarationLinkRow:
    year: int
    period: int
    declared_input_sha256: str
    declaration_artifact_id: str
    solver_artifact_id: str | None
    failure_artifact_id: str | None
    solver_status: str

    def __post_init__(self) -> None:
        if len(self.declared_input_sha256) != 64:
            raise ValueError("declared_input_sha256 must be a SHA-256")
        _required_text(self.declaration_artifact_id, "declaration_artifact_id")
        _required_text(self.solver_status, "solver_status")


@dataclass(frozen=True)
class NetworkSolverDiagnosticRow:
    run_id: str
    year: int
    period: int
    period_id: str
    phase_id: str
    module_id: str
    module_version: str
    solver_contract_version: str
    scipy_version: str
    highs_identity: str
    highs_binary_sha256: str
    method: str
    presolve: bool
    primal_feasibility_tolerance: float
    dual_feasibility_tolerance: float
    ipm_optimality_tolerance: float | None
    objective_unit: str
    optimum: float
    achieved_final_value: float
    degradation: float
    computed_tolerance: float
    warning_ceiling: float
    validated_ceiling: float
    absolute_ceiling: float
    nonzero_term_count: int
    absolute_term_scale: float
    validation_class: str
    error_code: str | None
    declared_input_sha256: str

    def __post_init__(self) -> None:
        for field_name in (
            "run_id", "period_id", "module_id", "module_version",
            "solver_contract_version", "scipy_version", "highs_identity",
        ):
            _required_text(getattr(self, field_name), field_name)
        if isinstance(self.year, bool) or not isinstance(self.year, int):
            raise ValueError("year must be an integer")
        if isinstance(self.period, bool) or not isinstance(self.period, int) or self.period < 0:
            raise ValueError("period must be a non-negative integer")
        if self.phase_id not in {
            "primary_bid_cost",
            "secondary_schedule_deviation",
            "physical_throughput",
        }:
            raise ValueError("phase_id is not a locked solver phase")
        if self.method not in {"highs-ds", "highs-ipm", "highs"}:
            raise ValueError("method is not supported")
        if not isinstance(self.presolve, bool):
            raise ValueError("presolve must be boolean")
        if self.objective_unit not in {"GBP", "MWh"}:
            raise ValueError("objective_unit must be GBP or MWh")
        expected_unit = "GBP" if self.phase_id == "primary_bid_cost" else "MWh"
        if self.objective_unit != expected_unit:
            raise ValueError(
                f"{self.phase_id} objective_unit must be {expected_unit}"
            )
        if self.validation_class not in {
            "GO", "GO_WITH_NUMERICAL_WARNING",
            "COMPLETED_WITH_NUMERICAL_WARNING",
        }:
            raise ValueError("validation_class is not supported")
        _sha256_text(self.highs_binary_sha256, "highs_binary_sha256")
        if self.highs_identity != (
            f"scipy-embedded-highs:{self.highs_binary_sha256}"
        ):
            raise ValueError(
                "highs_identity must match the recorded HiGHS binary SHA"
            )
        _sha256_text(self.declared_input_sha256, "declared_input_sha256")
        for field_name in (
            "primal_feasibility_tolerance", "dual_feasibility_tolerance",
            "warning_ceiling", "validated_ceiling", "absolute_ceiling",
        ):
            if _finite(getattr(self, field_name), field_name) <= 0.0:
                raise ValueError(f"{field_name} must be positive")
        if self.ipm_optimality_tolerance is not None:
            if _finite(
                self.ipm_optimality_tolerance, "ipm_optimality_tolerance"
            ) <= 0.0:
                raise ValueError("ipm_optimality_tolerance must be positive")
        if self.method == "highs-ds" and self.ipm_optimality_tolerance is not None:
            raise ValueError("ipm_optimality_tolerance must be null for highs-ds")
        if self.method != "highs-ds" and self.ipm_optimality_tolerance is None:
            raise ValueError(
                "ipm_optimality_tolerance must be positive for an active IPM method"
            )
        for field_name in ("optimum", "achieved_final_value"):
            _finite(getattr(self, field_name), field_name)
        for field_name in (
            "degradation", "computed_tolerance", "absolute_term_scale",
        ):
            _nonnegative(getattr(self, field_name), field_name)
        if not degradation_identity_matches(
            optimum=self.optimum,
            achieved_final_value=self.achieved_final_value,
            degradation=self.degradation,
            computed_tolerance=self.computed_tolerance,
        ):
            raise ValueError(
                "degradation must equal max(0, achieved_final_value - optimum) "
                "within bounded floating-point reconstruction tolerance"
            )
        if self.warning_ceiling > self.validated_ceiling:
            raise ValueError("warning_ceiling cannot exceed validated_ceiling")
        if self.validated_ceiling > self.absolute_ceiling:
            raise ValueError("validated_ceiling cannot exceed absolute_ceiling")
        if not gbp1_stored_policy_matches({
            "solver_contract_version": self.solver_contract_version,
            "phase_id": self.phase_id,
            "computed_tolerance": self.computed_tolerance,
            "validated_ceiling": self.validated_ceiling,
            "absolute_ceiling": self.absolute_ceiling,
        }):
            raise ValueError(
                gbp1_stored_policy_requirement(self.solver_contract_version)
            )
        classification = classify_lock(
            self.degradation,
            self.computed_tolerance,
            self.validated_ceiling,
            self.warning_ceiling / self.validated_ceiling,
            self.absolute_ceiling,
        )
        if classification.status != self.validation_class:
            raise ValueError(
                "validation_class does not match declared numerical evidence"
            )
        if (
            isinstance(self.nonzero_term_count, bool)
            or not isinstance(self.nonzero_term_count, int)
            or self.nonzero_term_count < 0
        ):
            raise ValueError("nonzero_term_count must be a non-negative integer")
        if self.error_code is not None:
            _required_text(self.error_code, "error_code")


# Optional v7 tables of the default PSM energy audit (P0-4 S4-S6).  They are
# created on first write only, so ledgers of other PSMs keep their table set.
# table -> (schema file, number of columns)
OPTIONAL_ENERGY_AUDIT_TABLES: dict[str, tuple[str, int]] = {
    "storage_energy_audit": ("market-ledger-storage-audit-v1.schema.sql", 12),
    "storage_year_boundary": ("market-ledger-storage-audit-v1.schema.sql", 7),
    "surplus_routing": ("market-ledger-surplus-routing-v1.schema.sql", 11),
}


def _optional_table_ddl(schema_file: str) -> str:
    return (Path(__file__).resolve().parent / "data" / "contracts" / schema_file).read_text(encoding="utf-8")


class MarketLedger(Protocol):
    trace_level: str

    def record_period_batch(self, batch: MarketPeriodBatch) -> PeriodIntegrity: ...
    def record_period(self, row: PeriodLedgerRow) -> None: ...
    def record_orders(self, rows: Iterable[OrderLedgerRow]) -> None: ...
    def record_storage(self, rows: Iterable[StorageStateRow]) -> None: ...
    def record_physical_dispatch(self, rows: Iterable[PhysicalDispatchRow]) -> None: ...
    def record_clearing_input(self, row: ClearingInputRow) -> None: ...
    def record_clearing_outcome(self, row: ClearingOutcomeRow) -> None: ...
    def record_zonal_accounting(self, rows: Iterable[ZonalAccountingLedgerRow]) -> None: ...
    def record_vre_curtailment_periods(self, rows: Iterable[VRECurtailmentPeriodRow]) -> None: ...
    def record_vre_curtailment_details(self, rows: Iterable[VRECurtailmentDetailRow]) -> None: ...
    def record_zonal_periods(self, rows: Iterable[ZonalPeriodLedgerRow]) -> None: ...
    def record_zonal_demand_alignment(self, rows: Iterable[ZonalDemandAlignmentLedgerRow]) -> None: ...
    def record_zones(self, rows: Iterable[ZonePeriodLedgerRow]) -> None: ...
    def record_boundaries(self, rows: Iterable[BoundaryPeriodLedgerRow]) -> None: ...
    def record_zonal_resources(self, rows: Iterable[ZonalResourceDispatchRow]) -> None: ...
    def record_redispatch_settlements(self, rows: Iterable[RedispatchSettlementRow]) -> None: ...
    def record_reliability_events(self, rows: Iterable[ReliabilityEventRow]) -> None: ...
    def record_solver_links(self, rows: Iterable[SolverDeclarationLinkRow]) -> None: ...
    def record_network_solver_diagnostics(
        self, rows: Iterable[NetworkSolverDiagnosticRow]
    ) -> None: ...
    def record_storage_audit(self, rows: Iterable[StorageEnergyAuditRow]) -> None: ...
    def record_storage_year_boundary(self, rows: Iterable[StorageYearBoundaryRow]) -> None: ...
    def record_surplus_routing(self, rows: Iterable[SurplusRoutingLedgerRow]) -> None: ...
    def close(self) -> dict[str, object]: ...


class NullMarketLedger:
    def __init__(self, *, schema_version: str = SCHEMA_VERSION) -> None:
        self.schema_version = schema_version

    trace_level = "off"

    def record_period_batch(self, batch: MarketPeriodBatch) -> PeriodIntegrity:
        return PeriodIntegrity(
            batch.period.year,
            batch.period.period,
            ZERO_SHA256,
            ZERO_SHA256,
            ZERO_SHA256,
            ZERO_SHA256,
            ZERO_SHA256,
            ZERO_SHA256,
        )
    def record_period(self, row: PeriodLedgerRow) -> None: pass
    def record_orders(self, rows: Iterable[OrderLedgerRow]) -> None: pass
    def record_storage(self, rows: Iterable[StorageStateRow]) -> None: pass
    def record_physical_dispatch(self, rows: Iterable[PhysicalDispatchRow]) -> None: pass
    def record_clearing_input(self, row: ClearingInputRow) -> None: pass
    def record_clearing_outcome(self, row: ClearingOutcomeRow) -> None: pass
    def record_zonal_accounting(self, rows: Iterable[ZonalAccountingLedgerRow]) -> None: pass
    def record_vre_curtailment_periods(self, rows: Iterable[VRECurtailmentPeriodRow]) -> None: pass
    def record_vre_curtailment_details(self, rows: Iterable[VRECurtailmentDetailRow]) -> None: pass
    def record_zonal_periods(self, rows: Iterable[ZonalPeriodLedgerRow]) -> None: pass
    def record_zonal_demand_alignment(self, rows: Iterable[ZonalDemandAlignmentLedgerRow]) -> None: pass
    def record_zones(self, rows: Iterable[ZonePeriodLedgerRow]) -> None: pass
    def record_boundaries(self, rows: Iterable[BoundaryPeriodLedgerRow]) -> None: pass
    def record_zonal_resources(self, rows: Iterable[ZonalResourceDispatchRow]) -> None: pass
    def record_redispatch_settlements(self, rows: Iterable[RedispatchSettlementRow]) -> None: pass
    def record_reliability_events(self, rows: Iterable[ReliabilityEventRow]) -> None: pass
    def record_solver_links(self, rows: Iterable[SolverDeclarationLinkRow]) -> None: pass
    def record_network_solver_diagnostics(
        self, rows: Iterable[NetworkSolverDiagnosticRow]
    ) -> None: pass
    def record_storage_audit(self, rows: Iterable[StorageEnergyAuditRow]) -> None: pass
    def record_storage_year_boundary(self, rows: Iterable[StorageYearBoundaryRow]) -> None: pass
    def record_surplus_routing(self, rows: Iterable[SurplusRoutingLedgerRow]) -> None: pass
    def close(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "trace_level": "off", "rows": 0, "bytes": 0, "writer_seconds": 0.0}


@contextmanager
def _read_only_connection(database: Path) -> Iterator[sqlite3.Connection]:
    """Read a finalized DB immutably or recover a committed WAL on a copy."""

    database = database.resolve()
    wal = database.with_name(f"{database.name}-wal")
    if wal.is_file() and wal.stat().st_size > 0:
        source_stats = {
            path.name: (path.stat().st_size, path.stat().st_mtime_ns)
            for path in (database, wal)
        }
        with tempfile.TemporaryDirectory(prefix="gridform-sqlite-snapshot-") as folder:
            snapshot = Path(folder) / database.name
            shutil.copyfile(database, snapshot)
            shutil.copyfile(wal, snapshot.with_name(f"{snapshot.name}-wal"))
            copied_stats = {
                path.name: (path.stat().st_size, path.stat().st_mtime_ns)
                for path in (database, wal)
            }
            if copied_stats != source_stats:
                raise sqlite3.OperationalError(
                    "SQLite evidence changed while copying committed WAL snapshot"
                )
            connection = sqlite3.connect(snapshot)
            connection.execute("PRAGMA query_only=ON")
            try:
                yield connection
            finally:
                connection.close()
        return
    uri = f"{database.as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        yield connection
    finally:
        connection.close()


def _declared_schema_version(database: Path) -> str | None:
    if not database.is_file():
        return None
    try:
        with _read_only_connection(database) as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table: metadata" in str(exc):
            return None
        raise
    return str(row[0]) if row else None


def market_ledger_capabilities(database: Path) -> dict[str, object]:
    """Inspect readable market-ledger versions without opening a writer."""

    with _read_only_connection(database) as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        version = str(row[0]) if row else "unknown"
        tables = {
            str(item[0])
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        period_count = (
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM vre_curtailment_period"
                ).fetchone()[0]
            )
            if "vre_curtailment_period" in tables
            else 0
        )
        statuses = (
            {
                str(item[0])
                for item in connection.execute(
                    "SELECT DISTINCT accounting_status FROM vre_curtailment_period"
                )
            }
            if period_count
            else set()
        )
    if version in {"value.market-ledger/v4", "value.market-ledger/v5"}:
        attribution_status = "legacy_partial"
        avoided_available = False
    elif version in ATTRIBUTION_SCHEMA_VERSIONS:
        attribution_status = (
            "reconciled" if statuses == {"reconciled"} else "not_recorded"
        )
        avoided_available = "vre_curtailment_period" in tables
    else:
        attribution_status = "unsupported"
        avoided_available = False
    return {
        "schema_version": "value.market-ledger-capabilities/v1",
        "ledger_schema_version": version,
        "attribution_status": attribution_status,
        "redispatch_avoided_curtailment_available": avoided_available,
    }


class SQLiteMarketLedger:
    def __init__(self, path: Path, *, trace_level: str, batch_size: int = 500, balance_tolerance_mwh: float = 1e-5, balance_relative_tolerance: float = 0.001, storage_cost_module_id: str = "unknown", export_format: str = "sqlite", semantic_metadata: dict[str, object] | None = None, _schema_version: str = SCHEMA_VERSION) -> None:
        if trace_level not in {"summary", "full"}:
            raise ValueError("SQLite market trace level must be summary or full")
        if _schema_version not in {LEGACY_WRITER_SCHEMA_VERSION, SCHEMA_VERSION}:
            raise ValueError(f"Unsupported writable market ledger schema {_schema_version}")
        self.schema_version = _schema_version
        self._authoritative_v8 = _schema_version == SCHEMA_VERSION
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ownership_lease = MarketLedgerOwnershipLease.acquire(
            self.path, role="writer"
        )
        try:
            existing_schema_version = _declared_schema_version(self.path)
            if (
                existing_schema_version in LEGACY_SCHEMA_VERSIONS
                and existing_schema_version != self.schema_version
            ):
                raise InvariantError(
                    "GF_LEDGER_SCHEMA_RESUME_MISMATCH: a legacy market ledger is "
                    "read-only. Start a new run ID restored from a portable checkpoint; "
                    "in-place schema conversion is not supported."
                )
            if existing_schema_version not in {None, self.schema_version}:
                raise ValueError(
                    f"Unsupported market ledger schema {existing_schema_version}"
                )
            supplied_semantic_metadata = dict(semantic_metadata or {})
            persistent_semantic_metadata = {
                str(key): value
                for key, value in supplied_semantic_metadata.items()
                if str(key) not in _CONTEXT_REGISTRY_METADATA_KEYS
            }
            if self._authoritative_v8 and existing_schema_version == SCHEMA_VERSION:
                with _read_only_connection(self.path) as existing_connection:
                    existing_metadata = {
                        str(key): str(value)
                        for key, value in existing_connection.execute(
                            "SELECT key, value FROM metadata"
                        )
                    }
                existing_trace = existing_metadata.pop("trace_level", None)
                existing_metadata.pop("schema_version", None)
                expected_metadata = {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    for key, value in sorted(persistent_semantic_metadata.items())
                }
                if existing_trace != trace_level:
                    raise InvariantError(
                        "Market ledger trace_level is immutable after creation"
                    )
                if existing_metadata != expected_metadata:
                    raise InvariantError(
                        "Market ledger semantic metadata is immutable after creation"
                    )
            self.trace_level = trace_level
            self.batch_size = max(1, int(batch_size))
            self.balance_tolerance_mwh = float(balance_tolerance_mwh)
            self.balance_relative_tolerance = float(balance_relative_tolerance)
            if export_format not in {"sqlite", "parquet"}:
                raise ValueError("market export format must be sqlite or parquet")
            self.export_format = export_format
            self.storage_cost_module_id = storage_cost_module_id
            self.semantic_metadata = supplied_semantic_metadata
            self.maximum_absolute_residual_mwh = 0.0
            self.maximum_absolute_raw_residual_mwh = 0.0
            self.compatibility_adjustment_periods = 0
            self.writer_seconds = 0.0
            self._periods: list[tuple] = []
            self._orders: list[tuple] = []
            self._storage: list[tuple] = []
            self._physical_dispatch: list[tuple] = []
            self._clearing_inputs: list[tuple] = []
            self._clearing_outcomes: list[tuple] = []
            self._zonal_accounting: list[tuple] = []
            self._vre_curtailment_periods: list[tuple] = []
            self._vre_curtailment_details: list[tuple] = []
            self._zonal_demand_alignment: list[tuple] = []
            self._zones: list[tuple] = []
            self._boundaries: list[tuple] = []
            self._zonal_resources: list[tuple] = []
            self._redispatch_settlements: list[tuple] = []
            self._reliability_events: list[tuple] = []
            self._solver_links: list[tuple] = []
            self._network_solver_diagnostics: list[tuple] = []
            # P0-4 S4-S6 optional energy-audit tables: table -> buffered rows.
            self._optional_rows: dict[str, list[tuple]] = {
                table: [] for table in OPTIONAL_ENERGY_AUDIT_TABLES
            }
            self._optional_created: set[str] = set()
            self._closed = False
        except Exception:
            self._ownership_lease.close()
            raise
        try:
            self.connection = sqlite3.connect(self.path)
        except Exception:
            self._ownership_lease.close()
            raise
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS period_summary(
                year INTEGER NOT NULL, period INTEGER NOT NULL, stage TEXT NOT NULL,
                forecast_demand_mwh REAL NOT NULL, real_demand_mwh REAL NOT NULL,
                accepted_supply_mwh REAL NOT NULL, storage_charge_mwh REAL NOT NULL,
                storage_discharge_mwh REAL NOT NULL, flexible_demand_mwh REAL NOT NULL,
                export_mwh REAL NOT NULL, vre_available_mwh REAL NOT NULL,
                vre_accepted_mwh REAL NOT NULL, curtailed_mwh REAL NOT NULL,
                import_mwh REAL NOT NULL, clearing_price_gbp_per_mwh REAL NOT NULL,
                physical_resource_cost_gbp REAL NOT NULL, market_payment_gbp REAL NOT NULL,
                policy_transfer_gbp REAL NOT NULL, blackout_mwh REAL NOT NULL,
                excess_mwh REAL NOT NULL, energy_balance_residual_mwh REAL NOT NULL,
                compatibility_adjustment_mwh REAL NOT NULL,
                raw_energy_balance_residual_mwh REAL NOT NULL,
                PRIMARY KEY(year, period, stage)
            );
            CREATE TABLE IF NOT EXISTS orders(
                order_id TEXT PRIMARY KEY, year INTEGER NOT NULL, period INTEGER NOT NULL,
                stage TEXT NOT NULL, asset_id TEXT NOT NULL, asset_type TEXT NOT NULL,
                side TEXT NOT NULL, offer_price_gbp_per_mwh REAL NOT NULL,
                offered_mwh REAL NOT NULL, accepted_mwh REAL NOT NULL,
                status TEXT NOT NULL, reason_code TEXT NOT NULL,
                physical_resource_cost_gbp REAL NOT NULL, market_payment_gbp REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS storage_state(
                year INTEGER NOT NULL, period INTEGER NOT NULL, asset_id TEXT NOT NULL,
                state_of_charge_mwh REAL NOT NULL, charge_mwh REAL NOT NULL,
                discharge_mwh REAL NOT NULL, power_capacity_mw REAL NOT NULL,
                energy_capacity_mwh REAL NOT NULL,
                PRIMARY KEY(year, period, asset_id)
            );
            CREATE TABLE IF NOT EXISTS physical_dispatch(
                year INTEGER NOT NULL, period INTEGER NOT NULL,
                asset_id TEXT NOT NULL, technology TEXT NOT NULL,
                flow_type TEXT NOT NULL, energy_mwh REAL NOT NULL,
                balance_component_mwh REAL NOT NULL,
                evidence_scope TEXT NOT NULL, source_stage TEXT NOT NULL,
                PRIMARY KEY(year, period, asset_id, flow_type)
            );
            CREATE TABLE IF NOT EXISTS clearing_inputs(
                input_sha256 TEXT PRIMARY KEY,
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                stage TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                information_scope TEXT NOT NULL,
                declared_before_clearing INTEGER NOT NULL CHECK(declared_before_clearing=1),
                payload_json TEXT NOT NULL,
                UNIQUE(year, period, stage)
            );
            CREATE TABLE IF NOT EXISTS clearing_outcomes(
                input_sha256 TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                outcome_json TEXT NOT NULL,
                FOREIGN KEY(input_sha256) REFERENCES clearing_inputs(input_sha256)
            );
            CREATE INDEX IF NOT EXISTS orders_period_stage ON orders(year, period, stage);
            CREATE INDEX IF NOT EXISTS orders_asset ON orders(asset_id, year, period);
            CREATE INDEX IF NOT EXISTS storage_period ON storage_state(year, period);
            CREATE INDEX IF NOT EXISTS physical_dispatch_period ON physical_dispatch(year, period);
            CREATE INDEX IF NOT EXISTS physical_dispatch_technology ON physical_dispatch(year, technology, flow_type);
            CREATE INDEX IF NOT EXISTS clearing_input_period_stage ON clearing_inputs(year, period, stage);
        """)
        self._initialize_v7_schema()
        if self._authoritative_v8:
            self.connection.executescript(
                (
                    Path(__file__).resolve().parent
                    / "data"
                    / "contracts"
                    / "market-ledger-v8.schema.sql"
                ).read_text(encoding="utf-8")
            )
        if existing_schema_version is None:
            self.connection.executemany(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",
                (
                    ("schema_version", self.schema_version),
                    ("trace_level", trace_level),
                    *(
                        (
                            str(key),
                            json.dumps(value, ensure_ascii=False, sort_keys=True),
                        )
                        for key, value in sorted(
                            (
                                persistent_semantic_metadata
                                if self._authoritative_v8
                                else self.semantic_metadata
                            ).items()
                        )
                    ),
                ),
            )
        self.connection.commit()

    def _initialize_v7_schema(self) -> None:
        contracts = Path(__file__).resolve().parent / "data" / "contracts"
        v5_base = (
            contracts / "market-ledger-v5.schema.sql"
        )
        v6_contract = contracts / "market-ledger-v6.schema.sql"
        self.connection.executescript(v5_base.read_text(encoding="utf-8"))
        self.connection.executescript(
            v6_contract.read_text(encoding="utf-8")
        )
        self.connection.executescript(
            (contracts / "market-ledger-v7.schema.sql").read_text(encoding="utf-8")
        )

    def _period_metrics(self, row: PeriodLedgerRow) -> tuple[float, float, int]:
        if not math.isfinite(row.energy_balance_residual_mwh):
            raise InvariantError("Market energy-balance residual is not finite")
        if not math.isfinite(row.raw_energy_balance_residual_mwh):
            raise InvariantError("Raw market energy-balance residual is not finite")
        absolute_residual = abs(row.energy_balance_residual_mwh)
        allowed_residual = max(
            self.balance_tolerance_mwh,
            self.balance_relative_tolerance
            * max(abs(row.real_demand_mwh), abs(row.accepted_supply_mwh), 1.0),
        )
        if absolute_residual > allowed_residual:
            raise InvariantError(
                f"Market energy balance failed in {row.year}:{row.period}:{row.stage}: "
                f"{row.energy_balance_residual_mwh:.9f} MWh "
                f"(supply={row.accepted_supply_mwh:.9f}, demand={row.real_demand_mwh:.9f}, "
                f"blackout={row.blackout_mwh:.9f}, charge={row.storage_charge_mwh:.9f}, "
                f"flexible={row.flexible_demand_mwh:.9f}, export={row.export_mwh:.9f}, "
                f"excess={row.excess_mwh:.9f})"
            )
        return (
            absolute_residual,
            abs(row.raw_energy_balance_residual_mwh),
            int(abs(row.compatibility_adjustment_mwh) > 1e-9),
        )

    def _insert_batch_rows(self, table: str, rows: Iterable[object]) -> int:
        allowed = _batch_table_contracts()
        if table not in allowed:
            raise ValueError(f"Unsupported market period batch table {table}")
        row_type, placeholders = allowed[table]
        materialized = tuple(rows)
        if any(not isinstance(row, row_type) for row in materialized):
            raise ValueError(f"{table} batch contains the wrong row contract")
        if not materialized:
            return 0
        self.connection.executemany(
            f"INSERT INTO {table} VALUES({','.join('?' for _ in range(placeholders))})",
            (tuple(asdict(row).values()) for row in materialized),
        )
        self._after_period_batch_table_insert(table)
        return len(materialized)

    def _after_period_batch_table_insert(self, table: str) -> None:
        """Test seam after a table insert and before the period commit."""

    def _register_batch_contexts(self, batch: MarketPeriodBatch) -> None:
        rows = (
            (
                "run",
                -1,
                str(
                    self.semantic_metadata.get("run_context_schema_version")
                    or "value.run-static-context/v1"
                ),
                batch.run_context_sha256,
                str(
                    self.semantic_metadata.get("run_context_artifact_path")
                    or "market/context/run-context.json"
                ),
            ),
            (
                "year",
                batch.period.year,
                str(
                    self.semantic_metadata.get("year_context_schema_version")
                    or "value.year-context/v1"
                ),
                batch.year_context_sha256,
                str(
                    self.semantic_metadata.get("year_context_artifact_path")
                    or f"market/context/year-{batch.period.year}.json"
                ),
            ),
        )
        for row in rows:
            existing = self.connection.execute(
                "SELECT schema_version, sha256, artifact_path FROM context_registry "
                "WHERE context_scope=? AND year=?",
                row[:2],
            ).fetchone()
            if existing is not None and tuple(existing) != row[2:]:
                raise InvariantError(
                    f"Market context registry conflict for {row[0]}:{row[1]}"
                )
            if existing is None:
                self.connection.execute(
                    "INSERT INTO context_registry VALUES(?,?,?,?,?)", row
                )

    def record_period_batch(self, batch: MarketPeriodBatch) -> PeriodIntegrity:
        if not self._authoritative_v8:
            raise InvariantError(
                "Atomic market period batches require the staged v8 ledger factory"
            )
        if self._closed:
            raise RuntimeError("Market ledger is closed")
        if not isinstance(batch, MarketPeriodBatch):
            raise ValueError("record_period_batch requires a MarketPeriodBatch")
        _validate_table_roles(batch.common_rows, batch.full_rows)
        metrics = self._period_metrics(batch.period)
        self.flush()
        started = time.perf_counter()
        row_counts: dict[str, int] = {
            "period_summary": 1,
            "dispatch_summary": len(batch.dispatch_summary),
            "storage_summary": len(batch.storage_summary),
            "redispatch_summary": len(batch.redispatch_summary),
        }
        row_counts.update({
            table: len(batch.common_rows.get(table, ()))
            for table in sorted(COMMON_TABLES)
        })
        if self.trace_level == "full":
            row_counts.update({
                table: len(batch.full_rows.get(table, ()))
                for table in sorted(FULL_ONLY_TABLES)
            })
        else:
            row_counts.update({table: 0 for table in sorted(FULL_ONLY_TABLES)})
        science_payload = _build_common_projection(
            batch.period,
            batch.dispatch_summary,
            batch.storage_summary,
            batch.redispatch_summary,
            batch.common_rows,
        )
        contracts = _batch_table_contracts()
        stored_payload = {
            "schema_version": EVIDENCE_PROJECTION_SCHEMA,
            "period": {
                "year": batch.period.year,
                "period": batch.period.period,
            },
        }
        stored_payload["trace_level"] = self.trace_level
        stored_payload["stored_row_counts"] = {
            key: row_counts[key] for key in sorted(row_counts)
        }
        stored_payload["common_rows"] = {
            "dispatch_summary": _canonical_row_dicts(
                DispatchSummaryRow, batch.dispatch_summary
            ),
            "storage_summary": _canonical_row_dicts(
                StorageSummaryRow, batch.storage_summary
            ),
            "redispatch_summary": _canonical_row_dicts(
                RedispatchSummaryRow, batch.redispatch_summary
            ),
            **{
                table: _canonical_row_dicts(
                    contracts[table][0], batch.common_rows.get(table, ())
                )
                for table in sorted(COMMON_TABLES)
            },
        }
        stored_payload["full_rows"] = (
            {
                table: _canonical_row_dicts(
                    contracts[table][0], batch.full_rows.get(table, ())
                )
                for table in sorted(FULL_ONLY_TABLES)
            }
            if self.trace_level == "full"
            else {}
        )
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing_year = self.connection.execute(
                "SELECT run_context_sha256, year_context_sha256, "
                "period_count, complete FROM year_integrity WHERE year=?",
                (batch.period.year,),
            ).fetchone()
            if existing_year is not None and int(existing_year[3]) == 1:
                raise InvariantError(
                    f"Market year {batch.period.year} is sealed and cannot be appended"
                )
            previous = self.connection.execute(
                "SELECT period, science_hash, evidence_hash FROM period_integrity "
                "WHERE year=? ORDER BY period DESC LIMIT 1",
                (batch.period.year,),
            ).fetchone()
            expected_period = int(previous[0]) + 1 if previous is not None else 0
            if batch.period.period != expected_period:
                raise InvariantError(
                    f"Market year {batch.period.year} expected period "
                    f"{expected_period}, received {batch.period.period}"
                )
            science_previous = (
                str(previous[1])
                if previous is not None
                else initial_science_hash(
                    batch.run_context_sha256, batch.year_context_sha256
                )
            )
            evidence_previous = (
                str(previous[2])
                if previous is not None
                else initial_evidence_hash(science_previous, self.trace_level)
            )
            science_hash = next_science_hash(
                science_previous, science_payload
            )
            evidence_hash = next_evidence_hash(
                evidence_previous, stored_payload
            )
            integrity = PeriodIntegrity(
                batch.period.year,
                batch.period.period,
                science_previous,
                science_hash,
                evidence_previous,
                evidence_hash,
                projection_sha256(
                    science_payload,
                    schema_version=SCIENCE_PROJECTION_SCHEMA,
                ),
                projection_sha256(
                    stored_payload,
                    schema_version=EVIDENCE_PROJECTION_SCHEMA,
                ),
            )
            self._register_batch_contexts(batch)
            self.connection.execute(
                "INSERT INTO period_summary VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(asdict(batch.period).values()),
            )
            self._after_period_batch_table_insert("period_summary")
            for table, rows in (
                ("dispatch_summary", batch.dispatch_summary),
                ("storage_summary", batch.storage_summary),
                ("redispatch_summary", batch.redispatch_summary),
            ):
                if rows:
                    self.connection.executemany(
                        f"INSERT INTO {table} VALUES({','.join('?' for _ in range(len(asdict(rows[0]))))})",
                        (tuple(asdict(row).values()) for row in rows),
                    )
                    self._after_period_batch_table_insert(table)
            for table, rows in batch.common_rows.items():
                self._insert_batch_rows(table, rows)
            if self.trace_level == "full":
                for table, rows in batch.full_rows.items():
                    self._insert_batch_rows(table, rows)
            self.connection.execute(
                "INSERT INTO period_integrity VALUES(?,?,?,?,?,?,?,?)",
                tuple(asdict(integrity).values()),
            )
            if existing_year is not None and tuple(existing_year[:2]) != (
                batch.run_context_sha256,
                batch.year_context_sha256,
            ):
                raise InvariantError(
                    f"Market year context changed for {batch.period.year}"
                )
            period_count = int(existing_year[2]) + 1 if existing_year else 1
            self.connection.execute(
                "INSERT INTO year_integrity VALUES(?,?,?,?,?,?,?,?,0) "
                "ON CONFLICT(year) DO UPDATE SET "
                "science_root=excluded.science_root, "
                "evidence_root=excluded.evidence_root, "
                "period_count=excluded.period_count, "
                "row_counts_json=excluded.row_counts_json, "
                "trace_coverage_json=excluded.trace_coverage_json, complete=0",
                (
                    batch.period.year,
                    batch.run_context_sha256,
                    batch.year_context_sha256,
                    science_hash,
                    evidence_hash,
                    period_count,
                    json.dumps(row_counts, sort_keys=True, separators=(",", ":")),
                    json.dumps(
                        {
                            "schema_version": "value.market-trace-coverage/v1",
                            "trace_level": self.trace_level,
                            "common_summary": True,
                            "full_detail": self.trace_level == "full",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        self.maximum_absolute_residual_mwh = max(
            self.maximum_absolute_residual_mwh, metrics[0]
        )
        self.maximum_absolute_raw_residual_mwh = max(
            self.maximum_absolute_raw_residual_mwh, metrics[1]
        )
        self.compatibility_adjustment_periods += metrics[2]
        self.writer_seconds += time.perf_counter() - started
        return integrity

    def record_period(self, row: PeriodLedgerRow) -> None:
        if self._authoritative_v8:
            self.record_period_batch(build_market_period_batch(period=row))
            return
        metrics = self._period_metrics(row)
        self.maximum_absolute_residual_mwh = max(
            self.maximum_absolute_residual_mwh, metrics[0]
        )
        self.maximum_absolute_raw_residual_mwh = max(
            self.maximum_absolute_raw_residual_mwh, metrics[1]
        )
        self.compatibility_adjustment_periods += metrics[2]
        self._periods.append(tuple(asdict(row).values()))
        if len(self._periods) >= self.batch_size:
            self.flush()

    def record_orders(self, rows: Iterable[OrderLedgerRow]) -> None:
        if self.trace_level != "full":
            return
        self._orders.extend(tuple(asdict(row).values()) for row in rows)
        if len(self._orders) >= self.batch_size:
            self.flush()

    def record_storage(self, rows: Iterable[StorageStateRow]) -> None:
        if self._authoritative_v8 and self.trace_level != "full":
            return
        self._storage.extend(tuple(asdict(row).values()) for row in rows)
        if len(self._storage) >= self.batch_size:
            self.flush()

    def record_physical_dispatch(self, rows: Iterable[PhysicalDispatchRow]) -> None:
        if self._authoritative_v8 and self.trace_level != "full":
            return
        for row in rows:
            values = tuple(asdict(row).values())
            if not all(math.isfinite(float(value)) for value in (row.energy_mwh, row.balance_component_mwh)):
                raise InvariantError("Physical dispatch contains a non-finite energy value")
            self._physical_dispatch.append(values)
        if len(self._physical_dispatch) >= self.batch_size:
            self.flush()

    def record_clearing_input(self, row: ClearingInputRow) -> None:
        if self.trace_level != "full":
            return
        if row.declared_before_clearing != 1:
            raise InvariantError("Clearing input was not declared before clearing")
        self._clearing_inputs.append(tuple(asdict(row).values()))
        if len(self._clearing_inputs) >= self.batch_size:
            self.flush()

    def record_clearing_outcome(self, row: ClearingOutcomeRow) -> None:
        if self.trace_level != "full":
            return
        self._clearing_outcomes.append(tuple(asdict(row).values()))
        if len(self._clearing_outcomes) >= self.batch_size:
            self.flush()

    def _extend(self, target: list[tuple], rows: Iterable[object]) -> None:
        target.extend(tuple(asdict(row).values()) for row in rows)
        if len(target) >= self.batch_size:
            self.flush()

    def _require_zonal_identity(self) -> None:
        required_identity = {
            "run_id", "run_parent_id", "data_pack_id", "network_pack_id", "module_ids"
        }
        missing = sorted(required_identity.difference(self.semantic_metadata))
        if missing:
            raise InvariantError(
                "Zonal market evidence lacks immutable run identities: "
                + ", ".join(missing)
            )

    def record_zonal_accounting(
        self, rows: Iterable[ZonalAccountingLedgerRow]
    ) -> None:
        self._require_zonal_identity()
        self._extend(self._zonal_accounting, rows)

    def record_vre_curtailment_periods(
        self, rows: Iterable[VRECurtailmentPeriodRow]
    ) -> None:
        self._require_zonal_identity()
        self._extend(self._vre_curtailment_periods, rows)

    def record_vre_curtailment_details(
        self, rows: Iterable[VRECurtailmentDetailRow]
    ) -> None:
        if self._authoritative_v8 and self.trace_level != "full":
            return
        self._require_zonal_identity()
        self._extend(self._vre_curtailment_details, rows)

    def record_zonal_periods(self, rows: Iterable[ZonalPeriodLedgerRow]) -> None:
        """Transitional cost-only adapter; v6 never writes the obsolete table."""

        self.record_zonal_accounting(
            ZonalAccountingLedgerRow.from_accounting(row) for row in rows
        )

    def record_zonal_demand_alignment(
        self, rows: Iterable[ZonalDemandAlignmentLedgerRow]
    ) -> None:
        self._extend(self._zonal_demand_alignment, rows)

    def record_zones(self, rows: Iterable[ZonePeriodLedgerRow]) -> None:
        self._extend(self._zones, rows)

    def record_boundaries(self, rows: Iterable[BoundaryPeriodLedgerRow]) -> None:
        self._extend(self._boundaries, rows)

    def record_zonal_resources(self, rows: Iterable[ZonalResourceDispatchRow]) -> None:
        if self._authoritative_v8 and self.trace_level != "full":
            return
        self._extend(self._zonal_resources, rows)

    def record_redispatch_settlements(
        self, rows: Iterable[RedispatchSettlementRow]
    ) -> None:
        if self.trace_level != "full":
            return
        self._extend(self._redispatch_settlements, rows)

    def record_reliability_events(self, rows: Iterable[ReliabilityEventRow]) -> None:
        materialized = tuple(rows)
        if not materialized:
            return
        if not self._authoritative_v8:
            self._extend(self._reliability_events, materialized)
            return
        if any(not isinstance(row, ReliabilityEventRow) for row in materialized):
            raise ValueError("reliability_event batch contains the wrong row contract")
        years = {int(row.year) for row in materialized}
        if len(years) != 1:
            raise ValueError("reliability events must seal exactly one market year")
        year = next(iter(years))
        self.flush()
        started = time.perf_counter()
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            state = self.connection.execute(
                "SELECT complete FROM year_integrity WHERE year=?", (year,)
            ).fetchone()
            if state is None:
                raise InvariantError(
                    f"Reliability evidence has no committed market year {year}"
                )
            if int(state[0]) == 1:
                raise InvariantError(
                    f"Market year {year} is sealed and cannot accept reliability evidence"
                )
            self.connection.executemany(
                "INSERT INTO reliability_event VALUES(?,?,?,?,?,?,?,?,?,?)",
                (tuple(asdict(row).values()) for row in materialized),
            )
            seal_year(self.connection, year)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        self.writer_seconds += time.perf_counter() - started

    def record_solver_links(self, rows: Iterable[SolverDeclarationLinkRow]) -> None:
        self._extend(self._solver_links, rows)

    def record_network_solver_diagnostics(
        self, rows: Iterable[NetworkSolverDiagnosticRow]
    ) -> None:
        materialized = list(rows)
        groups: dict[tuple[str, int, int], list[NetworkSolverDiagnosticRow]] = {}
        for row in materialized:
            groups.setdefault((row.run_id, row.year, row.period), []).append(row)
        expected_phases = {
            "primary_bid_cost",
            "secondary_schedule_deviation",
            "physical_throughput",
        }
        for identity, period_rows in groups.items():
            phases = {row.phase_id for row in period_rows}
            if len(period_rows) != 3 or phases != expected_phases:
                raise InvariantError(
                    "Network solver evidence requires all three locked phases "
                    f"for {identity[0]}:{identity[1]}:{identity[2]}"
                )
            if len({row.period_id for row in period_rows}) != 1:
                raise InvariantError(
                    "Network solver evidence has inconsistent period_id"
                )
            if len({row.declared_input_sha256 for row in period_rows}) != 1:
                raise InvariantError(
                    "Network solver evidence has inconsistent declared input identity"
                )
        if self._authoritative_v8 and self.trace_level != "full":
            return
        self._extend(self._network_solver_diagnostics, materialized)

    def _record_optional(self, table: str, rows: Iterable[object]) -> None:
        buffer = self._optional_rows[table]
        buffer.extend(tuple(asdict(row).values()) for row in rows)
        if len(buffer) >= self.batch_size:
            self.flush()

    def record_storage_audit(self, rows: Iterable[StorageEnergyAuditRow]) -> None:
        """Per-asset storage energy audit (P0-4 S4); every trace level."""

        self._record_optional("storage_energy_audit", rows)

    def record_storage_year_boundary(self, rows: Iterable[StorageYearBoundaryRow]) -> None:
        self._record_optional("storage_year_boundary", rows)

    def record_surplus_routing(self, rows: Iterable[SurplusRoutingLedgerRow]) -> None:
        """Source-classified surplus routing (P0-4 S5); every trace level."""

        self._record_optional("surplus_routing", rows)

    def _flush_optional(self) -> None:
        for table, buffer in self._optional_rows.items():
            if not buffer:
                continue
            if table not in self._optional_created:
                schema_file, _ = OPTIONAL_ENERGY_AUDIT_TABLES[table]
                self.connection.executescript(_optional_table_ddl(schema_file))
                self._optional_created.add(table)
            columns = OPTIONAL_ENERGY_AUDIT_TABLES[table][1]
            self.connection.executemany(
                f"INSERT OR REPLACE INTO {table} VALUES({','.join('?' for _ in range(columns))})",
                buffer,
            )
            buffer.clear()

    def flush(self) -> None:
        if self._closed:
            return
        started = time.perf_counter()
        self._flush_optional()
        if self._periods:
            self.connection.executemany("INSERT OR REPLACE INTO period_summary VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self._periods)
            self._periods.clear()
        if self._orders:
            self.connection.executemany("INSERT OR REPLACE INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", self._orders)
            self._orders.clear()
        if self._storage:
            self.connection.executemany("INSERT OR REPLACE INTO storage_state VALUES(?,?,?,?,?,?,?,?)", self._storage)
            self._storage.clear()
        if self._physical_dispatch:
            self.connection.executemany(
                "INSERT OR REPLACE INTO physical_dispatch VALUES(?,?,?,?,?,?,?,?,?)",
                self._physical_dispatch,
            )
            self._physical_dispatch.clear()
        if self._clearing_inputs:
            self.connection.executemany(
                "INSERT OR REPLACE INTO clearing_inputs VALUES(?,?,?,?,?,?,?,?)",
                self._clearing_inputs,
            )
            self._clearing_inputs.clear()
        if self._clearing_outcomes:
            self.connection.executemany(
                "INSERT OR REPLACE INTO clearing_outcomes VALUES(?,?,?)",
                self._clearing_outcomes,
            )
            self._clearing_outcomes.clear()
        for buffer, table, placeholders in (
            (self._zonal_accounting, "zonal_period_accounting", 16),
            (self._vre_curtailment_periods, "vre_curtailment_period", 20),
            (self._vre_curtailment_details, "vre_curtailment_detail", 20),
            (self._zonal_demand_alignment, "zonal_demand_alignment", 10),
            (self._zones, "zone_period_summary", 9),
            (self._boundaries, "boundary_period_summary", 9),
            (self._zonal_resources, "zonal_resource_dispatch", 13),
            (self._redispatch_settlements, "redispatch_settlement", 14),
            (self._reliability_events, "reliability_event", 10),
            (self._solver_links, "solver_declaration_link", 7),
            (
                self._network_solver_diagnostics,
                "network_solver_diagnostics",
                29,
            ),
        ):
            if buffer:
                self.connection.executemany(
                    f"INSERT OR REPLACE INTO {table} VALUES({','.join('?' for _ in range(placeholders))})",
                    buffer,
                )
                buffer.clear()
        self.connection.commit()
        self.writer_seconds += time.perf_counter() - started

    def close(self) -> dict[str, object]:
        try:
            return self._close_owned()
        finally:
            self.connection.close()
            self._ownership_lease.close()

    def close_unsealed(self) -> None:
        """Close an interrupted writer without producing annual artifacts."""

        if self._closed:
            self._ownership_lease.close()
            return
        self.connection.close()
        self._closed = True
        self._ownership_lease.close()

    def __del__(self) -> None:
        connection = getattr(self, "connection", None)
        lease = getattr(self, "_ownership_lease", None)
        try:
            try:
                if connection is not None:
                    connection.close()
            finally:
                if lease is not None:
                    lease.close()
        except Exception as exc:  # noqa: BLE001 - a finaliser must never raise
            # Interpreter shutdown may already have torn down sqlite/locks; the
            # explicit close() path reports real errors.  Record, do not hide.
            _LOGGER.debug("Market ledger finaliser ignored %s: %s", type(exc).__name__, exc)

    def _close_owned(self) -> dict[str, object]:
        if not self._authoritative_v8:
            return self._close_legacy()
        if self._closed:
            return self.metadata()
        self.flush()
        self._closed = True
        sealed_years = {
            int(year): dict(seal_year(self.connection, int(year)))
            for (year,) in self.connection.execute(
                "SELECT DISTINCT year FROM period_integrity ORDER BY year"
            )
        }
        self.connection.commit()
        tables = (
            "period_summary", "orders", "storage_state", "physical_dispatch",
            "clearing_inputs", "clearing_outcomes", "zonal_period_summary",
            "zonal_period_accounting", "vre_curtailment_period",
            "vre_curtailment_detail",
            "zonal_demand_alignment",
            "zone_period_summary", "boundary_period_summary",
            "zonal_resource_dispatch", "redispatch_settlement",
            "reliability_event", "solver_declaration_link",
            "network_solver_diagnostics",
            "dispatch_summary", "storage_summary", "redispatch_summary",
            "context_registry", "period_integrity", "year_integrity",
        )
        counts = {
            table: int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
        balance = self.connection.execute(
            "SELECT COALESCE(MAX(ABS(energy_balance_residual_mwh)), 0), "
            "COALESCE(MAX(ABS(raw_energy_balance_residual_mwh)), 0), "
            "COALESCE(SUM(CASE WHEN ABS(compatibility_adjustment_mwh) > 1e-9 "
            "THEN 1 ELSE 0 END), 0) FROM period_summary"
        ).fetchone()
        self.maximum_absolute_residual_mwh = float(balance[0])
        self.maximum_absolute_raw_residual_mwh = float(balance[1])
        self.compatibility_adjustment_periods = int(balance[2])
        checkpoint = self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is None or int(checkpoint[0]) != 0:
            raise RuntimeError(
                "Market ledger could not checkpoint its WAL before scientific sealing"
            )
        journal_mode = self.connection.execute("PRAGMA journal_mode=DELETE").fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "delete":
            raise RuntimeError(
                "Market ledger could not leave WAL mode before scientific sealing"
            )
        self.connection.close()
        parquet_exports: dict[str, object] | None = None
        if self.export_format == "parquet":
            if not parquet_available():
                raise RuntimeError(
                    "Optional Parquet export requires pyarrow; use the default SQLite output or install the approved optional dependency"
                )
            parquet_exports = export_market_parquet(self.path, self.path.parent / "parquet")
        source_artifact_sha256 = _sha256_file(self.path)
        science_root_by_year = {
            str(year): str(row["science_root"])
            for year, row in sealed_years.items()
        }
        evidence_root_by_year = {
            str(year): str(row["evidence_root"])
            for year, row in sealed_years.items()
        }
        context_hashes = {
            "run_context_sha256": next(
                (
                    str(row["run_context_sha256"])
                    for row in sealed_years.values()
                ),
                None,
            ),
            "year_context_sha256_by_year": {
                str(year): str(row["year_context_sha256"])
                for year, row in sealed_years.items()
            },
        }
        trace_coverage = {
            str(year): dict(row["trace_coverage"])
            for year, row in sealed_years.items()
        }
        result = {
            "schema_version": SCHEMA_VERSION,
            "trace_level": self.trace_level,
            "rows": counts,
            "bytes": self.path.stat().st_size if self.path.exists() else 0,
            "writer_seconds": self.writer_seconds,
            "maximum_absolute_energy_balance_residual_mwh": self.maximum_absolute_residual_mwh,
            "maximum_absolute_raw_energy_balance_residual_mwh": self.maximum_absolute_raw_residual_mwh,
            "compatibility_adjustment_periods": self.compatibility_adjustment_periods,
            "energy_balance_relative_tolerance": self.balance_relative_tolerance,
            "uri": str(self.path),
            "storage_cost_module_id": self.storage_cost_module_id,
            "requested_export_format": self.export_format,
            "parquet_exports": parquet_exports,
            "source_artifact_sha256": source_artifact_sha256,
            "semantic_metadata": self.semantic_metadata,
            "context_hashes": context_hashes,
            "science_root_by_year": science_root_by_year,
            "evidence_root_by_year": evidence_root_by_year,
            "trace_coverage_by_year": trace_coverage,
        }
        metadata_path = self.path.parent / "metadata.json"
        metadata_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        index = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "ledger_schema_version": SCHEMA_VERSION,
            "trace_level": self.trace_level,
            "years": _market_years(self.path),
            "rows": counts,
            "artifacts": {
                "sqlite": "market.sqlite",
                "parquet": parquet_exports,
            },
            "storage_cost_module_id": self.storage_cost_module_id,
            "source_artifact_sha256": source_artifact_sha256,
            "semantic_metadata": self.semantic_metadata,
            "context_hashes": context_hashes,
            "science_root_by_year": science_root_by_year,
            "evidence_root_by_year": evidence_root_by_year,
            "trace_coverage_by_year": trace_coverage,
            "units": {
                "energy": "MWh/period",
                "power_capacity": "MW",
                "energy_capacity": "MWh",
                "price": "GBP/MWh",
                "cost_and_payment": "GBP",
            },
            "maximum_absolute_energy_balance_residual_mwh": self.maximum_absolute_residual_mwh,
            "maximum_absolute_raw_energy_balance_residual_mwh": self.maximum_absolute_raw_residual_mwh,
        }
        (self.path.parent / "index.json").write_text(
            json.dumps(index, indent=2), encoding="utf-8"
        )
        _write_field_dictionary(
            self.path.parent / "field-dictionary.json",
            ledger_schema_version=self.schema_version,
        )
        return result

    def _close_legacy(self) -> dict[str, object]:
        """Seal the pre-Prompt120 v7 output contract for non-staged callers."""

        if self._closed:
            return self.metadata()
        self.flush()
        self._closed = True
        tables = (
            "period_summary", "orders", "storage_state", "physical_dispatch",
            "clearing_inputs", "clearing_outcomes", "zonal_period_summary",
            "zonal_period_accounting", "vre_curtailment_period",
            "vre_curtailment_detail", "zonal_demand_alignment",
            "zone_period_summary", "boundary_period_summary",
            "zonal_resource_dispatch", "redispatch_settlement",
            "reliability_event", "solver_declaration_link",
            "network_solver_diagnostics",
        )
        counts = {
            table: int(
                self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in tables
        }
        present = {
            row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for table in OPTIONAL_ENERGY_AUDIT_TABLES:
            if table in present:
                counts[table] = int(
                    self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
        energy_audit = self._energy_audit_summary(present)
        balance = self.connection.execute(
            "SELECT COALESCE(MAX(ABS(energy_balance_residual_mwh)), 0), "
            "COALESCE(MAX(ABS(raw_energy_balance_residual_mwh)), 0), "
            "COALESCE(SUM(CASE WHEN ABS(compatibility_adjustment_mwh) > 1e-9 "
            "THEN 1 ELSE 0 END), 0) FROM period_summary"
        ).fetchone()
        self.maximum_absolute_residual_mwh = float(balance[0])
        self.maximum_absolute_raw_residual_mwh = float(balance[1])
        self.compatibility_adjustment_periods = int(balance[2])
        checkpoint = self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is None or int(checkpoint[0]) != 0:
            raise RuntimeError(
                "Market ledger could not checkpoint its WAL before scientific sealing"
            )
        journal_mode = self.connection.execute("PRAGMA journal_mode=DELETE").fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "delete":
            raise RuntimeError(
                "Market ledger could not leave WAL mode before scientific sealing"
            )
        self.connection.close()
        parquet_exports: dict[str, object] | None = None
        if self.export_format == "parquet":
            if not parquet_available():
                raise RuntimeError(
                    "Optional Parquet export requires pyarrow; use the default SQLite output or install the approved optional dependency"
                )
            parquet_exports = export_market_parquet(
                self.path, self.path.parent / "parquet"
            )
        source_artifact_sha256 = _sha256_file(self.path)
        result = {
            "schema_version": self.schema_version,
            "trace_level": self.trace_level,
            "rows": counts,
            "bytes": self.path.stat().st_size if self.path.exists() else 0,
            "writer_seconds": self.writer_seconds,
            "maximum_absolute_energy_balance_residual_mwh": self.maximum_absolute_residual_mwh,
            "maximum_absolute_raw_energy_balance_residual_mwh": self.maximum_absolute_raw_residual_mwh,
            "compatibility_adjustment_periods": self.compatibility_adjustment_periods,
            "energy_balance_relative_tolerance": self.balance_relative_tolerance,
            "uri": str(self.path),
            "storage_cost_module_id": self.storage_cost_module_id,
            "requested_export_format": self.export_format,
            "parquet_exports": parquet_exports,
            "source_artifact_sha256": source_artifact_sha256,
            "semantic_metadata": self.semantic_metadata,
        }
        if energy_audit:
            result["energy_audit"] = energy_audit
        (self.path.parent / "metadata.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        index = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "ledger_schema_version": self.schema_version,
            "trace_level": self.trace_level,
            "years": _market_years(self.path),
            "rows": counts,
            "artifacts": {"sqlite": "market.sqlite", "parquet": parquet_exports},
            "storage_cost_module_id": self.storage_cost_module_id,
            "source_artifact_sha256": source_artifact_sha256,
            "semantic_metadata": self.semantic_metadata,
            "units": {
                "energy": "MWh/period",
                "power_capacity": "MW",
                "energy_capacity": "MWh",
                "price": "GBP/MWh",
                "cost_and_payment": "GBP",
            },
            "maximum_absolute_energy_balance_residual_mwh": self.maximum_absolute_residual_mwh,
            "maximum_absolute_raw_energy_balance_residual_mwh": self.maximum_absolute_raw_residual_mwh,
        }
        (self.path.parent / "index.json").write_text(
            json.dumps(index, indent=2), encoding="utf-8"
        )
        _write_field_dictionary(
            self.path.parent / "field-dictionary.json",
            ledger_schema_version=self.schema_version,
        )
        return result

    def _energy_audit_summary(self, present: set[str]) -> dict[str, object]:
        """Per-year SQL summaries of the optional P0-4 tables.

        The default PSM opens a new ledger instance on the same file every
        year, so the summary is computed over the file (all years so far),
        not from this instance's buffers.
        """

        summary: dict[str, object] = {}
        if "storage_energy_audit" in present:
            summary["storage_by_year"] = [
                {
                    "year": int(row[0]),
                    "charge_input_mwh": float(row[1]),
                    "discharge_output_mwh": float(row[2]),
                    "self_discharge_mwh": float(row[3]),
                    "tail_writeoff_mwh": float(row[4]),
                    "maximum_absolute_identity_residual_mwh": float(row[5]),
                }
                for row in self.connection.execute(
                    "SELECT year, SUM(charge_input_mwh), SUM(discharge_output_mwh), "
                    "SUM(self_discharge_mwh), SUM(tail_writeoff_mwh), "
                    "MAX(ABS(identity_residual_mwh)) FROM storage_energy_audit "
                    "GROUP BY year ORDER BY year"
                )
            ]
            if "storage_state" in present:
                # Report-only throughput bound (P0-4 S4): grid-side charge or
                # discharge above rated power x period length.
                try:
                    hours = float(self.semantic_metadata.get("period_hours", 0.5))
                except (TypeError, ValueError):
                    hours = 0.5
                row = self.connection.execute(
                    "SELECT COUNT(*) FROM storage_energy_audit a JOIN storage_state s "
                    "ON a.year=s.year AND a.period=s.period AND a.asset_id=s.asset_id "
                    "WHERE a.charge_input_mwh > s.power_capacity_mw * ? + 1e-9 "
                    "OR a.discharge_output_mwh > s.power_capacity_mw * ? + 1e-9",
                    (hours, hours),
                ).fetchone()
                summary["storage_throughput_exceedances"] = {
                    "periods": int(row[0]), "enforcement": "report_only",
                }
        if "surplus_routing" in present:
            summary["surplus_routing_by_year"] = [
                {
                    "year": int(row[0]), "source_class": str(row[1]),
                    "available_mwh": float(row[2]), "to_storage_mwh": float(row[3]),
                    "to_export_mwh": float(row[4]), "to_flexible_mwh": float(row[5]),
                    "to_dispatch_mwh": float(row[6]), "curtailed_mwh": float(row[7]),
                    "spilled_mwh": float(row[8]), "unrealised_mwh": float(row[9]),
                }
                for row in self.connection.execute(
                    "SELECT year, source_class, SUM(available_mwh), SUM(to_storage_mwh), "
                    "SUM(to_export_mwh), SUM(to_flexible_mwh), SUM(to_dispatch_mwh), "
                    "SUM(curtailed_mwh), SUM(spilled_mwh), SUM(unrealised_mwh) "
                    "FROM surplus_routing GROUP BY year, source_class ORDER BY year, source_class"
                )
            ]
        if "storage_year_boundary" in present:
            summary["storage_year_boundary"] = [
                {"year": int(row[0]), "discarded_mwh": float(row[1]), "carried_forward_mwh": float(row[2])}
                for row in self.connection.execute(
                    "SELECT year, SUM(discarded_mwh), SUM(carried_forward_mwh) "
                    "FROM storage_year_boundary GROUP BY year ORDER BY year"
                )
            ]
        return summary

    def metadata(self) -> dict[str, object]:
        metadata_path = self.path.parent / "metadata.json"
        if metadata_path.exists():
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        return {"schema_version": self.schema_version, "trace_level": self.trace_level, "uri": str(self.path)}


def create_market_ledger(
    path: Path,
    trace_level: str,
    *,
    batch_size: int = 500,
    balance_tolerance_mwh: float = 1e-5,
    storage_cost_module_id: str = "unknown",
    export_format: str = "sqlite",
    semantic_metadata: dict[str, object] | None = None,
) -> MarketLedger:
    if trace_level == "off":
        return NullMarketLedger(schema_version=LEGACY_WRITER_SCHEMA_VERSION)
    return SQLiteMarketLedger(
        path,
        trace_level=trace_level,
        batch_size=batch_size,
        balance_tolerance_mwh=balance_tolerance_mwh,
        storage_cost_module_id=storage_cost_module_id,
        export_format=export_format,
        semantic_metadata=semantic_metadata,
        _schema_version=LEGACY_WRITER_SCHEMA_VERSION,
    )


def create_staged_market_ledger_v8(
    path: Path,
    trace_level: str,
    *,
    batch_size: int = 500,
    balance_tolerance_mwh: float = 1e-5,
    storage_cost_module_id: str = "unknown",
    export_format: str = "sqlite",
    semantic_metadata: dict[str, object] | None = None,
) -> MarketLedger:
    """Create the authoritative v8 ledger used only by staged market runs."""

    if trace_level == "off":
        return NullMarketLedger()
    return SQLiteMarketLedger(
        path,
        trace_level=trace_level,
        batch_size=batch_size,
        balance_tolerance_mwh=balance_tolerance_mwh,
        storage_cost_module_id=storage_cost_module_id,
        export_format=export_format,
        semantic_metadata=semantic_metadata,
    )


def parquet_available() -> bool:
    return importlib.util.find_spec("pyarrow") is not None


def _market_years(database: Path) -> list[int]:
    with _read_only_connection(database) as connection:
        return [
            int(row[0])
            for row in connection.execute(
                "SELECT DISTINCT year FROM period_summary ORDER BY year"
            )
        ]


MARKET_TABLES = (
    "period_summary", "orders", "storage_state", "physical_dispatch",
    "clearing_inputs", "clearing_outcomes", "zonal_period_summary",
    "zonal_period_accounting", "vre_curtailment_period",
    "vre_curtailment_detail",
    "zonal_demand_alignment",
    "zone_period_summary", "boundary_period_summary",
    "zonal_resource_dispatch", "redispatch_settlement",
    "reliability_event", "solver_declaration_link",
    "network_solver_diagnostics",
    "dispatch_summary", "storage_summary", "redispatch_summary",
    "context_registry", "period_integrity", "year_integrity",
)


def _write_field_dictionary(
    path: Path, *, ledger_schema_version: str = SCHEMA_VERSION
) -> None:
    fields = {
        "year": "Model year containing the interval.",
        "period": "Ledger interval index within the model year.",
        "period_id": "Stable chronology identity shared by the three matched counterfactuals.",
        "asset_id": "Stable executable VRE dispatch-object identity.",
        "owner_id": "Stable owner identity associated with the dispatch object.",
        "zone_id": "Stable zone identity used for the attributed regional view.",
        "technology": "Canonical VRE technology: Solar, Onshore wind or Offshore wind.",
        "bid_tranche_id": "Stable bid-tranche identity; never solver row order or a display-formatted float.",
        "realised_available_vre_mwh": "Realised available Solar, Onshore wind and Offshore wind energy in the interval.",
        "perfect_reference_dispatch_mwh": "VRE accepted in the matched perfect-forecast copperplate case after deterministic technology/tranche reference allocation.",
        "copperplate_reference_dispatch_mwh": "VRE accepted in the matched forecast-schedule plus realised copperplate case after deterministic technology/tranche reference allocation.",
        "zonal_final_dispatch_mwh": "Final physical VRE dispatch after zonal redispatch; detail rows preserve the solver result without redistribution.",
        "economic_curtailment_mwh": "Realised available VRE minus perfect-forecast copperplate reference dispatch.",
        "forecast_added_curtailment_mwh": "Positive part of perfect-reference dispatch minus realised-copperplate reference dispatch (Forecast & scheduling impact).",
        "forecast_avoided_curtailment_mwh": "Positive part of realised-copperplate reference dispatch minus perfect-reference dispatch (Forecast & scheduling impact).",
        "redispatch_added_curtailment_mwh": "Positive part of realised-copperplate reference dispatch minus final zonal dispatch (Redispatch impact).",
        "redispatch_avoided_curtailment_mwh": "Positive part of final zonal dispatch minus realised-copperplate reference dispatch (Redispatch impact).",
        "redispatch_net_impact_mwh": "Redispatch impact: redispatch-added minus redispatch-avoided curtailment; a negative value means net avoided curtailment.",
        "total_curtailment_mwh": "Final VRE curtailment: realised available VRE minus final zonal dispatch.",
        "curtailment_rate": "Final VRE curtailment divided by realised available VRE. Annual values use SUM(total_curtailment_mwh) / SUM(realised_available_vre_mwh), not a mean of period rates.",
        "identity_residual_mwh": "Economic plus forecast-added minus forecast-avoided plus redispatch-added minus redispatch-avoided minus final curtailment.",
        "validation_tolerance_mwh": "Period attribution tolerance: max(1e-7 MWh, 1e-10 times max(period realised available VRE, 1 MWh)).",
        "accounting_status": "Validation state of the authoritative v6 period attribution row.",
        "counterfactual_realised_input_sha256": "Lowercase SHA-256 proving the three dispatch cases use the same realised input.",
        "attribution_method_id": "Versioned deterministic reference-allocation method identity.",
        "evidence_level": "Evidence scope for detail rows; regional and technology values are deterministic reference allocations, not direct national counterfactual quantities.",
        "system_resource_cost_gbp": "Final physical resource cost; settlement transfers are excluded.",
        "network_constraint_cost_gbp": "Zonal realised resource cost minus the matched realised copperplate resource cost.",
        "national_settlement_gbp": "Ahead schedule volume paid at the GB national clearing price.",
        "redispatch_settlement_gbp": "Signed pay-as-bid cashflow for accepted redispatch adjustments.",
        "policy_transfer_gbp": "Declared policy/support transfer, kept outside physical resource cost.",
        "boundary_shadow_value_gbp_per_mwh": "Diagnostic marginal value in the accepted-bid objective; not a zonal price or observed cash cost.",
        "forecast_error_cost_gbp": "Forecast-schedule realised copperplate cost minus perfect-forecast copperplate realised cost.",
        "network_constraint_cost_identity_gbp": "Forecast-schedule realised zonal cost minus matched realised copperplate cost.",
        "total_deviation_cost_gbp": "Forecast-schedule realised zonal cost minus perfect-forecast copperplate realised cost.",
        "event_duration_hours": "Observed duration in this chronology; not statistical LOLE.",
        "unserved_mwh": "Observed energy not served in the event.",
        "scale_factor": "Multiplier applied to signed network-pack zonal demand in the declared demand-authority mode.",
        "conservation_residual_mwh": "Aligned zonal total minus the authoritative national realised demand for the period.",
        "run_id": "Immutable run identity owning the solver evidence.",
        "phase_id": "Locked lexicographic objective phase identity.",
        "module_id": "Balancing module identity used for the period solve.",
        "module_version": "Balancing module version used for the period solve.",
        "solver_contract_version": "Declared numerical solver-contract version.",
        "scipy_version": "Exact SciPy package version used by the run.",
        "highs_identity": "Content-addressed identity of the embedded HiGHS extension.",
        "highs_binary_sha256": "Lowercase SHA-256 of the embedded HiGHS binary.",
        "method": "Declared scipy.optimize.linprog HiGHS method.",
        "presolve": "Whether solver presolve was enabled.",
        "primal_feasibility_tolerance": "Active primal feasibility tolerance.",
        "dual_feasibility_tolerance": "Active dual feasibility tolerance.",
        "ipm_optimality_tolerance": "Active IPM optimality tolerance, or null when inactive.",
        "objective_unit": "Physical or monetary unit of the locked objective.",
        "optimum": "Objective value at the phase optimum.",
        "achieved_final_value": "Locked objective recomputed from the final solution.",
        "degradation": "One-sided final objective degradation from the phase optimum.",
        "computed_tolerance": "Solver-derived one-sided lock tolerance.",
        "warning_ceiling": "Configured warning fraction multiplied by the validated ceiling.",
        "validated_ceiling": "Declared built-in validation ceiling for the objective.",
        "absolute_ceiling": "Recorded VALUE numerical reference threshold for the objective.",
        "nonzero_term_count": "Number of non-zero terms in the locked objective.",
        "absolute_term_scale": "Sum of absolute coefficient-times-optimum terms.",
        "validation_class": "GO, numerical warning, or completed unvalidated status.",
        "error_code": "Machine-readable solver-contract error code when present.",
        "declared_input_sha256": "Lowercase SHA-256 of the complete declared balancing input.",
    }
    table_units = {
        "vre_curtailment_period": {
            "year": "index",
            "period": "index",
            "period_id": "identifier",
            "realised_available_vre_mwh": "MWh",
            "perfect_reference_dispatch_mwh": "MWh",
            "copperplate_reference_dispatch_mwh": "MWh",
            "zonal_final_dispatch_mwh": "MWh",
            "economic_curtailment_mwh": "MWh",
            "forecast_added_curtailment_mwh": "MWh",
            "forecast_avoided_curtailment_mwh": "MWh",
            "redispatch_added_curtailment_mwh": "MWh",
            "redispatch_avoided_curtailment_mwh": "MWh",
            "redispatch_net_impact_mwh": "MWh",
            "total_curtailment_mwh": "MWh",
            "curtailment_rate": "fraction",
            "identity_residual_mwh": "MWh",
            "validation_tolerance_mwh": "MWh",
            "accounting_status": "status enum",
            "counterfactual_realised_input_sha256": "sha256",
            "attribution_method_id": "method identifier",
        },
        "vre_curtailment_detail": {
            "year": "index",
            "period": "index",
            "period_id": "identifier",
            "asset_id": "identifier",
            "owner_id": "identifier",
            "zone_id": "identifier",
            "technology": "categorical identifier",
            "bid_tranche_id": "identifier",
            "realised_available_vre_mwh": "MWh",
            "perfect_reference_dispatch_mwh": "MWh",
            "copperplate_reference_dispatch_mwh": "MWh",
            "zonal_final_dispatch_mwh": "MWh",
            "economic_curtailment_mwh": "MWh",
            "forecast_added_curtailment_mwh": "MWh",
            "forecast_avoided_curtailment_mwh": "MWh",
            "redispatch_added_curtailment_mwh": "MWh",
            "redispatch_avoided_curtailment_mwh": "MWh",
            "redispatch_net_impact_mwh": "MWh",
            "total_curtailment_mwh": "MWh",
            "evidence_level": "status enum",
        },
        "network_solver_diagnostics": {
            "run_id": "identifier",
            "year": "index",
            "period": "index",
            "period_id": "identifier",
            "phase_id": "identifier",
            "module_id": "identifier",
            "module_version": "version",
            "solver_contract_version": "version",
            "scipy_version": "version",
            "highs_identity": "identifier",
            "highs_binary_sha256": "sha256",
            "method": "method identifier",
            "presolve": "boolean",
            "primal_feasibility_tolerance": "solver tolerance",
            "dual_feasibility_tolerance": "solver tolerance",
            "ipm_optimality_tolerance": "solver tolerance",
            "objective_unit": "GBP or MWh",
            "optimum": "GBP or MWh",
            "achieved_final_value": "GBP or MWh",
            "degradation": "GBP or MWh",
            "computed_tolerance": "GBP or MWh",
            "warning_ceiling": "GBP or MWh",
            "validated_ceiling": "GBP or MWh",
            "absolute_ceiling": "GBP or MWh",
            "nonzero_term_count": "count",
            "absolute_term_scale": "GBP or MWh",
            "validation_class": "status enum",
            "error_code": "error code",
            "declared_input_sha256": "sha256",
        },
    }
    table_semantics = {
        "vre_curtailment_period": (
            "One authoritative national VRE attribution row per model interval."
        ),
        "vre_curtailment_detail": (
            "One deterministic object/tranche attribution row per model interval."
        ),
        "network_solver_diagnostics": (
            "One authoritative solver-evidence row per model interval and locked phase."
        ),
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(
            {
                "schema_version": "value.market-ledger-field-dictionary/v1",
                "ledger_schema_version": ledger_schema_version,
                "fields": fields,
                "tables": {
                    table: {
                        "semantics": table_semantics[table],
                        "fields": {
                            field: {
                                "unit": unit,
                                "semantics": fields[field],
                            }
                            for field, unit in field_units.items()
                        },
                    }
                    for table, field_units in table_units.items()
                },
                "attribution_components": [
                    "economic_curtailment_mwh",
                    "forecast_added_curtailment_mwh",
                    "forecast_avoided_curtailment_mwh",
                    "redispatch_added_curtailment_mwh",
                    "redispatch_avoided_curtailment_mwh",
                    "total_curtailment_mwh",
                ],
                "public_labels": {
                    "redispatch_net_impact_mwh": "Redispatch impact",
                },
                "aggregation": {
                    "annual_curtailment_rate": {
                        "formula": "sum(total_curtailment_mwh) / sum(realised_available_vre_mwh)",
                        "denominator": "sum(realised_available_vre_mwh)",
                        "weighting": "realised available VRE energy",
                        "unit": "fraction",
                    },
                },
                "compatibility_statuses": {
                    "legacy_partial": {
                        "avoided_curtailment": "unavailable",
                        "missing_value": None,
                        "zero_is_not_a_missing_value": True,
                    },
                },
                "capabilities": [
                    "evidence.vre-counterfactual-snapshot/v1",
                    "results.vre-curtailment-attribution/v2",
                ],
                "presentation": {
                    "waterfall_is_presentation_only": True,
                    "authoritative_values": ledger_schema_version,
                },
                "units": {
                    "energy": "MWh",
                    "price": "GBP/MWh",
                    "cost_and_settlement": "GBP",
                    "duration": "hours",
                },
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ) + "\n")


def export_market_parquet(database: Path, destination: Path, *, batch_rows: int = 50_000) -> dict[str, object]:
    """Optional bounded-memory post-run export; SQLite remains canonical."""

    import pyarrow as pa  # type: ignore[import-not-found]
    import pyarrow.parquet as pq  # type: ignore[import-not-found]

    destination.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {}
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        for table in MARKET_TABLES:
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            order_columns = [
                column for column in (
                    "year", "period", "start_period", "input_sha256", "event_id"
                ) if column in columns
            ]
            order = ", ".join(order_columns) or "rowid"
            cursor = connection.execute(f"SELECT * FROM {table} ORDER BY {order}")
            writer = None
            rows_written = 0
            path = destination / f"{table}.parquet"
            try:
                while True:
                    rows = cursor.fetchmany(batch_rows)
                    if not rows:
                        break
                    batch = pa.Table.from_pylist([dict(row) for row in rows])
                    if writer is None:
                        writer = pq.ParquetWriter(path, batch.schema, compression="zstd")
                    writer.write_table(batch)
                    rows_written += len(rows)
            finally:
                if writer is not None:
                    writer.close()
            result[table] = {
                "uri": f"parquet/{path.name}",
                "rows": rows_written,
                "bytes": path.stat().st_size if path.exists() else 0,
            }
    return result


def _database_period_rows(
    connection: sqlite3.Connection,
    table: str,
    year: int,
    period: int,
) -> list[dict[str, object]]:
    row_type = _period_table_row_types().get(table)
    if row_type is None:
        raise ValueError(f"Unsupported market period table: {table}")
    columns = [
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
    ]
    if table == "clearing_outcomes":
        rows = connection.execute(
            "SELECT outcome.* FROM clearing_outcomes AS outcome "
            "JOIN clearing_inputs AS input "
            "ON input.input_sha256=outcome.input_sha256 "
            "WHERE input.year=? AND input.period=?",
            (int(year), int(period)),
        )
    else:
        if "year" not in columns or "period" not in columns:
            raise ValueError(f"period table {table} lacks year/period identity")
        rows = connection.execute(
            f"SELECT * FROM {table} WHERE year=? AND period=?",
            (int(year), int(period)),
        )
    materialized = [
        _canonical_database_row_mapping(row_type, dict(zip(columns, row)))
        for row in rows
    ]
    return sorted(
        materialized,
        key=lambda row: json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
    )


def _database_period_projections(
    connection: sqlite3.Connection,
    *,
    year: int,
    period: int,
    trace_level: str,
) -> tuple[dict[str, object], dict[str, object]]:
    period_rows = _database_period_rows(
        connection, "period_summary", year, period
    )
    if len(period_rows) != 1:
        raise ValueError(
            f"period_summary coverage for {year}:{period} is {len(period_rows)}"
        )
    dispatch = _database_period_rows(
        connection, "dispatch_summary", year, period
    )
    storage = _database_period_rows(
        connection, "storage_summary", year, period
    )
    redispatch = _database_period_rows(
        connection, "redispatch_summary", year, period
    )
    common = {
        table: _database_period_rows(connection, table, year, period)
        for table in sorted(COMMON_TABLES)
    }
    full = {
        table: _database_period_rows(connection, table, year, period)
        for table in sorted(FULL_ONLY_TABLES)
    }
    science_payload = {
        "schema_version": SCIENCE_PROJECTION_SCHEMA,
        "period": period_rows[0],
        "dispatch_summary": dispatch,
        "storage_summary": storage,
        "redispatch_summary": redispatch,
        "common_rows": common,
    }
    row_counts = {
        "period_summary": 1,
        "dispatch_summary": len(dispatch),
        "storage_summary": len(storage),
        "redispatch_summary": len(redispatch),
        **{table: len(rows) for table, rows in common.items()},
        **{
            table: len(rows) if trace_level == "full" else 0
            for table, rows in full.items()
        },
    }
    evidence_payload = {
        "schema_version": EVIDENCE_PROJECTION_SCHEMA,
        "period": {"year": int(year), "period": int(period)},
        "trace_level": trace_level,
        "stored_row_counts": {
            key: row_counts[key] for key in sorted(row_counts)
        },
        "common_rows": {
            "dispatch_summary": dispatch,
            "storage_summary": storage,
            "redispatch_summary": redispatch,
            **common,
        },
        "full_rows": full if trace_level == "full" else {},
    }
    return science_payload, evidence_payload


def _v8_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _assert_period_indexed_v8_table_registry(
    connection: sqlite3.Connection,
) -> None:
    discovered: set[str] = set()
    for table in _v8_tables(connection):
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if {"year", "period"}.issubset(columns):
            discovered.add(table)
    registered = set(PERIOD_INDEXED_V8_TABLES)
    if discovered != registered:
        missing = sorted(discovered - registered)
        stale = sorted(registered - discovered)
        raise InvariantError(
            "v8 period-indexed table registry mismatch: "
            f"unregistered={missing}, missing={stale}"
        )


def _prefix_row_counts(
    connection: sqlite3.Connection, *, year: int, committed_period: int
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in sorted(_v8_tables(connection)):
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if "year" not in columns:
            continue
        if "period" in columns:
            counts[table] = int(connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE year=? AND period<=?",
                (year, committed_period),
            ).fetchone()[0])
        else:
            counts[table] = int(connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE year=?", (year,)
            ).fetchone()[0])
    return counts


def _trace_coverage(trace_level: str) -> dict[str, object]:
    return {
        "schema_version": "value.market-trace-coverage/v1",
        "trace_level": trace_level,
        "common_summary": True,
        "full_detail": trace_level == "full",
    }


def _sqlite_backup_sha256(connection: sqlite3.Connection) -> str:
    with tempfile.TemporaryDirectory(prefix="gridform-ledger-identity-") as folder:
        snapshot = Path(folder) / "market.sqlite"
        with closing(sqlite3.connect(snapshot)) as retained:
            connection.backup(retained)
        return _sha256_file(snapshot)


def _committed_prefix_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _replay_v8_market_prefix(
    connection: sqlite3.Connection,
    *,
    year: int,
    committed_period: int,
    trace_level: str,
) -> dict[str, object]:
    rows = list(connection.execute(
        "SELECT period, previous_science_hash, science_hash, "
        "previous_evidence_hash, evidence_hash, common_projection_sha256, "
        "stored_rows_sha256 FROM period_integrity "
        "WHERE year=? AND period<=? ORDER BY period",
        (year, committed_period),
    ))
    periods = [int(row[0]) for row in rows]
    expected_periods = list(range(committed_period + 1))
    if periods != expected_periods:
        raise InvariantError(
            f"Market ledger prefix is not continuous 0..{committed_period} "
            f"for {year}: {periods}"
        )
    context = connection.execute(
        "SELECT run_context_sha256, year_context_sha256 FROM year_integrity "
        "WHERE year=?", (year,),
    ).fetchone()
    if context is None:
        raise InvariantError(f"Market ledger year {year} has no integrity state")
    run_context_sha256, year_context_sha256 = map(str, context)
    science_previous = initial_science_hash(
        run_context_sha256, year_context_sha256
    )
    evidence_previous = initial_evidence_hash(science_previous, trace_level)
    last_common_projection = ZERO_SHA256
    last_stored_projection = ZERO_SHA256
    for row in rows:
        period = int(row[0])
        if trace_level != "full":
            for table in sorted(FULL_ONLY_TABLES):
                if _database_period_rows(connection, table, year, period):
                    raise InvariantError(
                        f"{trace_level} prefix contains full-only rows in "
                        f"{table}:{year}:{period}"
                    )
        try:
            science_payload, evidence_payload = _database_period_projections(
                connection, year=year, period=period, trace_level=trace_level
            )
        except (ValueError, sqlite3.DatabaseError) as exc:
            raise InvariantError(
                f"Market ledger prefix projection unreadable at {year}:{period}: {exc}"
            ) from exc
        common_projection = projection_sha256(
            science_payload, schema_version=SCIENCE_PROJECTION_SCHEMA
        )
        stored_projection = projection_sha256(
            evidence_payload, schema_version=EVIDENCE_PROJECTION_SCHEMA
        )
        science_hash = next_science_hash(science_previous, science_payload)
        evidence_hash = next_evidence_hash(evidence_previous, evidence_payload)
        if str(row[1]) != science_previous:
            raise InvariantError(
                f"Market ledger previous science root mismatch at {year}:{period}"
            )
        if str(row[2]) != science_hash:
            raise InvariantError(
                f"Market ledger science root mismatch at {year}:{period}"
            )
        if str(row[3]) != evidence_previous:
            raise InvariantError(
                f"Market ledger previous evidence root mismatch at {year}:{period}"
            )
        if str(row[4]) != evidence_hash:
            raise InvariantError(
                f"Market ledger evidence root mismatch at {year}:{period}"
            )
        if str(row[5]) != common_projection:
            raise InvariantError(
                f"Market ledger common projection mismatch at {year}:{period}"
            )
        if str(row[6]) != stored_projection:
            raise InvariantError(
                f"Market ledger stored projection mismatch at {year}:{period}"
            )
        science_previous = science_hash
        evidence_previous = evidence_hash
        last_common_projection = common_projection
        last_stored_projection = stored_projection
    return {
        "run_context_sha256": run_context_sha256,
        "year_context_sha256": year_context_sha256,
        "science_root": science_previous,
        "evidence_root": evidence_previous,
        "common_projection_sha256": last_common_projection,
        "stored_rows_sha256": last_stored_projection,
    }


def _verify_v8_market_prefix_connection(
    connection: sqlite3.Connection,
    *,
    boundary: MarketLedgerBoundary,
    require_exact: bool = False,
) -> dict[str, object]:
    schema = connection.execute(
        "SELECT value FROM metadata WHERE key='schema_version'"
    ).fetchone()
    if schema is None or str(schema[0]) != SCHEMA_VERSION:
        raise InvariantError("Market prefix verification requires value.market-ledger/v8")
    trace = connection.execute(
        "SELECT value FROM metadata WHERE key='trace_level'"
    ).fetchone()
    trace_level = str(trace[0]) if trace else "unknown"
    if trace_level != boundary.trace_level:
        raise InvariantError("Market ledger trace level does not match the boundary")
    _assert_period_indexed_v8_table_registry(connection)
    state = connection.execute(
        "SELECT run_context_sha256, year_context_sha256, period_count, complete "
        "FROM year_integrity WHERE year=?", (boundary.year,),
    ).fetchone()
    if state is None:
        raise InvariantError(f"Market ledger year {boundary.year} is absent")
    if int(state[3]) != 0:
        raise InvariantError(
            f"Market ledger year {boundary.year} is complete and cannot be recovered"
        )
    if int(state[2]) < boundary.period_count:
        raise InvariantError("Market ledger contains fewer periods than the boundary")
    if require_exact and int(state[2]) != boundary.period_count:
        raise InvariantError("Recovered market ledger period count is not exact")
    run_registry = connection.execute(
        "SELECT sha256 FROM context_registry "
        "WHERE context_scope='run' AND year=-1"
    ).fetchone()
    year_registry = connection.execute(
        "SELECT sha256 FROM context_registry "
        "WHERE context_scope='year' AND year=?", (boundary.year,),
    ).fetchone()
    if (
        run_registry is None
        or str(run_registry[0]) != boundary.run_context_sha256
        or str(state[0]) != boundary.run_context_sha256
    ):
        raise InvariantError("Market ledger RunContext does not match the boundary")
    if (
        year_registry is None
        or str(year_registry[0]) != boundary.year_context_sha256
        or str(state[1]) != boundary.year_context_sha256
    ):
        raise InvariantError("Market ledger YearContext does not match the boundary")
    reliability_rows = int(connection.execute(
        "SELECT COUNT(*) FROM reliability_event WHERE year=?", (boundary.year,)
    ).fetchone()[0])
    if reliability_rows:
        raise InvariantError(
            f"Incomplete market year {boundary.year} contains reliability_event rows"
        )
    for table in PERIOD_INDEXED_V8_TABLES:
        negative = int(connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE year=? AND period<0",
            (boundary.year,),
        ).fetchone()[0])
        if negative:
            raise InvariantError(f"Market ledger {table} contains negative periods")
        if require_exact:
            tail = int(connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE year=? AND period>?",
                (boundary.year, boundary.last_committed_period),
            ).fetchone()[0])
            if tail:
                raise InvariantError(f"Recovered market ledger retains tail rows in {table}")
    replayed = _replay_v8_market_prefix(
        connection,
        year=boundary.year,
        committed_period=boundary.last_committed_period,
        trace_level=trace_level,
    )
    expected = {
        "run_context_sha256": boundary.run_context_sha256,
        "year_context_sha256": boundary.year_context_sha256,
        "science_root": boundary.science_root,
        "evidence_root": boundary.evidence_root,
        "common_projection_sha256": boundary.common_projection_sha256,
        "stored_rows_sha256": boundary.stored_rows_sha256,
    }
    if replayed != expected:
        raise InvariantError("Market ledger replay does not match the selected boundary")
    row_counts_json = json.dumps(
        _prefix_row_counts(
            connection, year=boundary.year,
            committed_period=boundary.last_committed_period,
        ),
        sort_keys=True, separators=(",", ":"),
    )
    if row_counts_json != boundary.row_counts_json:
        raise InvariantError("Market ledger prefix row counts do not match the boundary")
    trace_coverage_json = json.dumps(
        _trace_coverage(trace_level), sort_keys=True, separators=(",", ":")
    )
    if trace_coverage_json != boundary.trace_coverage_json:
        raise InvariantError("Market ledger trace coverage does not match the boundary")
    prefix_payload = {
        "year": boundary.year,
        "last_committed_period": boundary.last_committed_period,
        "period_count": boundary.period_count,
        **expected,
        "trace_level": trace_level,
        "row_counts_json": row_counts_json,
        "trace_coverage_json": trace_coverage_json,
    }
    if _committed_prefix_sha256(prefix_payload) != boundary.committed_prefix_sha256:
        raise InvariantError("Market ledger committed prefix identity does not match")
    return {
        "valid": True,
        **prefix_payload,
        "database_sha256": boundary.database_sha256,
        "committed_prefix_sha256": boundary.committed_prefix_sha256,
        "ledger_prefix_identity": boundary.ledger_prefix_identity.to_dict(),
    }


def market_ledger_boundary(
    database: Path, *, year: int, committed_period: int
) -> MarketLedgerBoundary:
    """Capture one verified, continuous v8 ledger prefix identity."""

    if isinstance(committed_period, bool) or int(committed_period) < 0:
        raise ValueError("committed_period must be non-negative")
    year = int(year)
    committed_period = int(committed_period)
    with _read_only_connection(Path(database)) as connection:
        schema = connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        if schema is None or str(schema[0]) != SCHEMA_VERSION:
            raise InvariantError(
                "Market prefix boundaries require value.market-ledger/v8"
            )
        trace = connection.execute(
            "SELECT value FROM metadata WHERE key='trace_level'"
        ).fetchone()
        trace_level = str(trace[0]) if trace else "unknown"
        if trace_level not in {"summary", "full"}:
            raise InvariantError(f"Unsupported v8 trace level {trace_level}")
        _assert_period_indexed_v8_table_registry(connection)
        replayed = _replay_v8_market_prefix(
            connection, year=year, committed_period=committed_period,
            trace_level=trace_level,
        )
        state = connection.execute(
            "SELECT period_count, complete FROM year_integrity WHERE year=?",
            (year,),
        ).fetchone()
        if state is None or int(state[0]) < committed_period + 1:
            raise InvariantError("Market ledger does not contain the selected boundary")
        if int(state[1]) != 0:
            raise InvariantError(f"Market ledger year {year} is already complete")
        reliability_rows = int(connection.execute(
            "SELECT COUNT(*) FROM reliability_event WHERE year=?", (year,)
        ).fetchone()[0])
        if reliability_rows:
            raise InvariantError(
                f"Incomplete market year {year} contains reliability_event rows"
            )
        row_counts_json = json.dumps(
            _prefix_row_counts(
                connection, year=year, committed_period=committed_period
            ),
            sort_keys=True, separators=(",", ":"),
        )
        trace_coverage_json = json.dumps(
            _trace_coverage(trace_level), sort_keys=True, separators=(",", ":")
        )
        prefix_payload = {
            "year": year,
            "last_committed_period": committed_period,
            "period_count": committed_period + 1,
            **replayed,
            "trace_level": trace_level,
            "row_counts_json": row_counts_json,
            "trace_coverage_json": trace_coverage_json,
        }
        boundary = MarketLedgerBoundary(
            **prefix_payload,
            database_sha256=_sqlite_backup_sha256(connection),
            committed_prefix_sha256=_committed_prefix_sha256(prefix_payload),
        )
        _verify_v8_market_prefix_connection(connection, boundary=boundary)
        return boundary


def verify_v8_market_prefix(
    database: Path, *, boundary: MarketLedgerBoundary
) -> Mapping[str, object]:
    """Replay and verify a selected v8 market prefix without changing SQLite."""

    if not isinstance(boundary, MarketLedgerBoundary):
        raise TypeError("boundary must be a MarketLedgerBoundary")
    with _read_only_connection(Path(database)) as connection:
        return _verify_v8_market_prefix_connection(
            connection, boundary=boundary
        )


def validate_market_ledger_file(database: Path) -> dict[str, object]:
    """Validate SQLite integrity across legacy read-only and current v8 ledgers."""

    errors: list[str] = []
    solver_evidence_errors: list[str] = []
    science_root_by_year: dict[str, str] = {}
    evidence_root_by_year: dict[str, str] = {}
    try:
        with _read_only_connection(database) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            version = str(row[0]) if row else None
            trace_row = connection.execute(
                "SELECT value FROM metadata WHERE key='trace_level'"
            ).fetchone()
            trace_level = str(trace_row[0]) if trace_row else "unknown"
            tables = {
                str(item[0]) for item in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if version == SCHEMA_VERSION:
                if trace_level not in {"summary", "full"}:
                    errors.append(f"v8_trace_level_unsupported:{trace_level}")
                if trace_level != "full":
                    for table in sorted(FULL_ONLY_TABLES.intersection(tables)):
                        count = int(
                            connection.execute(
                                f"SELECT COUNT(*) FROM {table}"
                            ).fetchone()[0]
                        )
                        if count:
                            errors.append(
                                f"{trace_level}_contains_full_only_rows:"
                                f"{table}:{count}"
                            )
            if (
                version == "value.market-ledger/v7"
                or (version == SCHEMA_VERSION and trace_level == "full")
            ) and {
                "network_solver_diagnostics", "zonal_period_accounting"
            }.issubset(tables):
                solver_evidence_errors = network_solver_evidence_errors(
                    connection
                )
            if version == SCHEMA_VERSION and "year_integrity" in tables:
                for integrity_row in connection.execute(
                    "SELECT year, run_context_sha256, year_context_sha256, "
                    "science_root, evidence_root, period_count, row_counts_json, "
                    "trace_coverage_json, complete "
                    "FROM year_integrity ORDER BY year"
                ):
                    year = int(integrity_row[0])
                    science_root_by_year[str(year)] = str(integrity_row[3])
                    evidence_root_by_year[str(year)] = str(integrity_row[4])
                    period_rows = list(connection.execute(
                        "SELECT period, previous_science_hash, science_hash, "
                        "previous_evidence_hash, evidence_hash, "
                        "common_projection_sha256, stored_rows_sha256 "
                        "FROM period_integrity WHERE year=? ORDER BY period",
                        (year,),
                    ))
                    if not period_rows:
                        errors.append(f"year_integrity_without_period:{year}")
                        continue
                    science_previous = initial_science_hash(
                        str(integrity_row[1]), str(integrity_row[2])
                    )
                    evidence_previous = initial_evidence_hash(
                        science_previous, trace_level
                    )
                    for expected_period, period_integrity in enumerate(period_rows):
                        period = int(period_integrity[0])
                        if period != expected_period:
                            errors.append(
                                f"period_integrity_coverage_gap:{year}:{period}"
                            )
                        if trace_level != "full":
                            for table in sorted(FULL_ONLY_TABLES):
                                if _database_period_rows(
                                    connection, table, year, period
                                ):
                                    errors.append(
                                        f"{trace_level}_contains_full_only_rows:"
                                        f"{year}:{period}:{table}"
                                    )
                        try:
                            science_payload, evidence_payload = (
                                _database_period_projections(
                                    connection,
                                    year=year,
                                    period=period,
                                    trace_level=trace_level,
                                )
                            )
                        except (ValueError, sqlite3.DatabaseError) as exc:
                            errors.append(
                                f"period_integrity_projection_unreadable:"
                                f"{year}:{period}:{exc}"
                            )
                            continue
                        if str(period_integrity[1]) != science_previous:
                            errors.append(
                                f"period_integrity_previous_science_mismatch:"
                                f"{year}:{period}"
                            )
                        expected_science_hash = next_science_hash(
                            science_previous, science_payload
                        )
                        if (
                            str(period_integrity[5])
                            != projection_sha256(
                                science_payload,
                                schema_version=SCIENCE_PROJECTION_SCHEMA,
                            )
                            or str(period_integrity[2]) != expected_science_hash
                        ):
                            errors.append(
                                f"period_integrity_science_projection_mismatch:"
                                f"{year}:{period}"
                            )
                        if str(period_integrity[3]) != evidence_previous:
                            errors.append(
                                f"period_integrity_previous_evidence_mismatch:"
                                f"{year}:{period}"
                            )
                        expected_evidence_hash = next_evidence_hash(
                            evidence_previous, evidence_payload
                        )
                        if (
                            str(period_integrity[6])
                            != projection_sha256(
                                evidence_payload,
                                schema_version=EVIDENCE_PROJECTION_SCHEMA,
                            )
                            or str(period_integrity[4]) != expected_evidence_hash
                        ):
                            errors.append(
                                f"period_integrity_evidence_projection_mismatch:"
                                f"{year}:{period}"
                            )
                        science_previous = expected_science_hash
                        evidence_previous = expected_evidence_hash
                    if len(period_rows) != int(integrity_row[5]):
                        errors.append(f"year_integrity_period_count_mismatch:{year}")
                    actual_row_counts: dict[str, int] = {}
                    for table in sorted(tables):
                        columns = {
                            str(column[1])
                            for column in connection.execute(
                                f"PRAGMA table_info({table})"
                            )
                        }
                        if "year" in columns:
                            actual_row_counts[table] = int(
                                connection.execute(
                                    f"SELECT COUNT(*) FROM {table} WHERE year=?",
                                    (year,),
                                ).fetchone()[0]
                            )
                    try:
                        stored_row_counts = json.loads(str(integrity_row[6]))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        stored_row_counts = None
                    if stored_row_counts != actual_row_counts:
                        errors.append(f"year_integrity_row_counts_mismatch:{year}")
                    expected_trace_coverage = {
                        "schema_version": "value.market-trace-coverage/v1",
                        "trace_level": trace_level,
                        "common_summary": trace_level in {"summary", "full"},
                        "full_detail": trace_level == "full",
                    }
                    try:
                        stored_trace_coverage = json.loads(str(integrity_row[7]))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        stored_trace_coverage = None
                    if stored_trace_coverage != expected_trace_coverage:
                        errors.append(
                            f"year_integrity_trace_coverage_mismatch:{year}"
                        )
                    expected_annual_evidence = next_evidence_hash(
                        evidence_previous,
                        annual_evidence_payload(connection, year),
                    )
                    if science_previous != str(integrity_row[3]):
                        errors.append(f"year_integrity_science_root_mismatch:{year}")
                    if expected_annual_evidence != str(integrity_row[4]):
                        errors.append(f"year_integrity_evidence_root_mismatch:{year}")
                    if int(integrity_row[8]) != 1:
                        errors.append(f"year_integrity_incomplete:{year}")
    except (OSError, sqlite3.DatabaseError) as exc:
        return {
            "valid": False,
            "schema_version": None,
            "errors": [f"unreadable_sqlite:{exc}"],
        }
    if integrity != "ok":
        errors.append(f"sqlite_integrity:{integrity}")
    if version not in LEGACY_SCHEMA_VERSIONS | {SCHEMA_VERSION}:
        errors.append(f"unsupported_schema:{version}")
    v5_required = {
        "zonal_period_summary", "zone_period_summary",
        "zonal_demand_alignment",
        "boundary_period_summary", "zonal_resource_dispatch",
        "redispatch_settlement", "reliability_event",
        "solver_declaration_link",
    }
    required: set[str] = set()
    if version == "value.market-ledger/v5":
        required = v5_required
    elif version in ATTRIBUTION_SCHEMA_VERSIONS:
        required = v5_required | {
            "zonal_period_accounting",
            "vre_curtailment_period",
            "vre_curtailment_detail",
        }
        if version in {"value.market-ledger/v7", SCHEMA_VERSION}:
            required.add("network_solver_diagnostics")
        if version == SCHEMA_VERSION:
            required.update({
                "dispatch_summary",
                "storage_summary",
                "redispatch_summary",
                "context_registry",
                "period_integrity",
                "year_integrity",
            })
    if required:
        for table in sorted(required.difference(tables)):
            errors.append(f"missing_table:{table}")
    if version == "value.market-ledger/v7" or (
        version == SCHEMA_VERSION and trace_level == "full"
    ):
        errors.extend(solver_evidence_errors)
    return {
        "valid": not errors,
        "schema_version": version,
        "integrity": integrity,
        "errors": errors,
        "science_root_by_year": science_root_by_year,
        "evidence_root_by_year": evidence_root_by_year,
    }


_SOLVER_PHASES = {
    "primary_bid_cost",
    "secondary_schedule_deviation",
    "physical_throughput",
}


def network_solver_evidence_errors(
    connection: sqlite3.Connection,
    *,
    year: int | None = None,
) -> list[str]:
    """Return bounded structural/reconciliation errors for v7 solver evidence."""

    errors: list[str] = []

    def add(code: str, identity: tuple[object, ...]) -> None:
        if not any(item.startswith(code) for item in errors):
            errors.append(f"{code}:{':'.join(str(item) for item in identity)}")

    where = "WHERE year=?" if year is not None else ""
    values: tuple[object, ...] = (year,) if year is not None else ()
    column_names = (
        "run_id", "year", "period", "period_id", "phase_id", "module_id",
        "module_version", "solver_contract_version", "scipy_version",
        "highs_identity", "highs_binary_sha256", "method", "presolve",
        "primal_feasibility_tolerance", "dual_feasibility_tolerance",
        "ipm_optimality_tolerance", "declared_input_sha256", "optimum",
        "achieved_final_value", "degradation", "computed_tolerance",
        "warning_ceiling", "validated_ceiling", "absolute_ceiling",
        "validation_class", "objective_unit",
    )
    columns = ", ".join(column_names)
    current_identity: tuple[object, ...] | None = None
    group: list[tuple[object, ...]] = []

    def finish_group() -> None:
        if current_identity is None:
            return
        phases = {str(row[4]) for row in group}
        if len(group) != 3 or phases != _SOLVER_PHASES:
            add("solver_diagnostics_incomplete_phase_group", current_identity)
        if len({str(row[3]) for row in group}) != 1:
            add("solver_diagnostics_inconsistent_period_identity", current_identity)
        stack_slice = slice(5, 16)
        if len({tuple(row[stack_slice]) for row in group}) != 1:
            add("solver_diagnostics_inconsistent_stack_identity", current_identity)
        if len({str(row[16]) for row in group}) != 1:
            add("solver_diagnostics_inconsistent_input_identity", current_identity)
        for row in group:
            record = dict(zip(column_names, row))
            validation = validate_stored_lock_evidence(record)
            for code in validation.errors:
                add(code, (*current_identity, str(row[4])))

    for row in connection.execute(
        f"SELECT {columns} FROM network_solver_diagnostics {where} "
        "ORDER BY run_id, year, period, CASE phase_id "
        "WHEN 'primary_bid_cost' THEN 0 "
        "WHEN 'secondary_schedule_deviation' THEN 1 "
        "WHEN 'physical_throughput' THEN 2 ELSE 3 END",
        values,
    ):
        identity = (str(row[0]), int(row[1]), int(row[2]))
        if current_identity is not None and identity != current_identity:
            finish_group()
            group = []
        current_identity = identity
        group.append(tuple(row))
    finish_group()

    year_filter = "AND a.year=?" if year is not None else ""
    missing = connection.execute(
        "SELECT a.year, a.period, a.period_id "
        "FROM zonal_period_accounting AS a "
        "WHERE a.accounting_status='reconciled' "
        f"{year_filter} "
        "AND NOT EXISTS ("
        "SELECT 1 FROM network_solver_diagnostics AS d "
        "WHERE d.year=a.year AND d.period=a.period "
        "AND d.period_id=a.period_id) "
        "ORDER BY a.year, a.period LIMIT 1",
        values,
    ).fetchone()
    if missing is not None:
        add("solver_diagnostics_missing_completed_period", tuple(missing))

    year_filter = "AND d.year=?" if year is not None else ""
    orphan = connection.execute(
        "SELECT d.run_id, d.year, d.period, MIN(d.period_id) "
        "FROM network_solver_diagnostics AS d "
        "WHERE NOT EXISTS ("
        "SELECT 1 FROM zonal_period_accounting AS a "
        "WHERE a.accounting_status='reconciled' "
        "AND a.year=d.year AND a.period=d.period AND a.period_id=d.period_id) "
        f"{year_filter} "
        "GROUP BY d.run_id, d.year, d.period "
        "ORDER BY d.run_id, d.year, d.period LIMIT 1",
        values,
    ).fetchone()
    if orphan is not None:
        add("solver_diagnostics_orphan_period", tuple(orphan))
    return errors


def set_active_market_ledger(ledger: MarketLedger | None) -> None:
    global _ACTIVE_LEDGER
    _ACTIVE_LEDGER = ledger


def active_market_ledger() -> MarketLedger:
    return _ACTIVE_LEDGER if _ACTIVE_LEDGER is not None else NullMarketLedger()


def query_market_table(
    database: Path,
    table: str,
    *,
    limit: int = 100,
    offset: int = 0,
    year: int | None = None,
    period: int | None = None,
    period_from: int | None = None,
    period_to: int | None = None,
    stage: str | None = None,
    asset_id: str | None = None,
    technology: str | None = None,
    flow_type: str | None = None,
    status: str | None = None,
    side: str | None = None,
    zone_id: str | None = None,
    boundary_id: str | None = None,
    agent_id: str | None = None,
    event_id: str | None = None,
) -> dict[str, object]:
    if table not in set(MARKET_TABLES):
        raise ValueError("Unsupported market ledger table")
    try:
        limit, offset = int(limit), int(offset)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be integers") from exc
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    if offset < 0:
        raise ValueError("offset cannot be negative")
    if period is not None and (period_from is not None or period_to is not None):
        raise ValueError("period cannot be combined with period_from or period_to")
    if period_from is not None and int(period_from) < 0:
        raise ValueError("period_from cannot be negative")
    if period_to is not None and int(period_to) < 0:
        raise ValueError("period_to cannot be negative")
    if (
        period_from is not None
        and period_to is not None
        and int(period_to) < int(period_from)
    ):
        raise ValueError("period_to must be at least period_from")
    with _read_only_connection(database) as schema_connection:
        columns = {
            row[1]
            for row in schema_connection.execute(f"PRAGMA table_info({table})")
        }
    filters, values = [], []
    for column, value in (
        ("year", year), ("period", period), ("stage", stage),
        ("asset_id", asset_id), ("technology", technology),
        ("flow_type", flow_type), ("status", status), ("side", side),
        ("zone_id", zone_id), ("boundary_id", boundary_id),
        ("agent_id", agent_id), ("event_id", event_id),
    ):
        if value is not None and column in columns:
            filters.append(f"{column}=?")
            values.append(value)
    if "period" in columns:
        if period_from is not None:
            filters.append("period>=?")
            values.append(int(period_from))
        if period_to is not None:
            filters.append("period<=?")
            values.append(int(period_to))
    where = " WHERE " + " AND ".join(filters) if filters else ""
    if table == "clearing_outcomes":
        order = "input_sha256"
    else:
        order_columns = [column for column in ("year", "period", "order_id", "zone_id", "boundary_id", "agent_id", "asset_id", "bid_id", "event_id") if column in columns]
        order = ", ".join(order_columns) or "rowid"
    with _read_only_connection(database) as connection:
        connection.row_factory = sqlite3.Row
        total = connection.execute(f"SELECT COUNT(*) FROM {table}{where}", values).fetchone()[0]
        rows = connection.execute(
            f"SELECT * FROM {table}{where} ORDER BY {order} LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(row) for row in rows]}


def export_market_table(database: Path, table: str, destination: Path, *, output_format: str = "jsonl") -> dict[str, object]:
    if table not in set(MARKET_TABLES):
        raise ValueError("Unsupported market ledger table")
    if output_format not in {"jsonl", "csv"}:
        raise ValueError("output_format must be jsonl or csv")
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with closing(sqlite3.connect(database)) as connection, destination.open("w", encoding="utf-8", newline="") as handle:
        connection.row_factory = sqlite3.Row
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        order_columns = [column for column in ("year", "period", "input_sha256", "event_id") if column in columns]
        order = ", ".join(order_columns) or "rowid"
        cursor = connection.execute(f"SELECT * FROM {table} ORDER BY {order}")
        writer = None
        for record in cursor:
            row = dict(record)
            if output_format == "jsonl":
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            else:
                if writer is None:
                    writer = csv.DictWriter(handle, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
            count += 1
    return {"rows": count, "bytes": destination.stat().st_size, "uri": str(destination)}
