"""Bounded, versioned read models for VALUE market replay and VRE evidence."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from .market_ledger import _read_only_connection
from .model_clock import ledger_clock, period_start_iso


AUCTION_VIEW_SCHEMA = "value.market-auction-view/v1"
PHYSICAL_DISPATCH_SCHEMA = "value.physical-dispatch-view/v1"
DISPATCH_TIMELINE_SCHEMA = "value.dispatch-timeline/v2"
REPLAY_CAPABILITIES_SCHEMA = "value.market-replay-capabilities/v1"
VRE_SUMMARY_SCHEMA = "value.vre-curtailment-summary/v1"
VRE_TIMELINE_SCHEMA = "value.vre-curtailment-timeline/v1"
STRESS_EVENTS_SCHEMA = "value.stress-events/v1"
# C20: the corrected rule set's declared ``curtailed`` column (native_market_rules.column_semantics).
CORRECTED_CURTAILMENT_SEMANTICS = "vre_available_minus_gross_output"
ZONAL_REPLAY_CAPABILITY = "value.zonal-results-page/v1"


def canonical_technology(
    asset_id: str,
    *,
    asset_type: str | None = None,
    declared_technology: str | None = None,
) -> str:
    """Map executable market identities to stable result groups.

    The mapping lives in the backend so charts never infer scientific identity
    from display labels. Unknown values remain explicit instead of disappearing.
    """

    raw = " ".join(
        value for value in (declared_technology, asset_id, asset_type) if value
    ).lower().replace("-", "_").replace(" ", "_")
    if "offshore" in raw:
        return "offshore_wind"
    if "onshore" in raw:
        return "onshore_wind"
    if "solar" in raw or "photovolta" in raw:
        return "solar"
    if "pumped" in raw and "hydro" in raw:
        return "pumped_hydro"
    if "hydro_natural" in raw or "run_of_river" in raw or "natural_flow" in raw:
        return "natural_flow_hydro"
    if "reservoir" in raw and "hydro" in raw:
        return "reservoir_hydro"
    if "nuclear" in raw:
        return "nuclear"
    if "ccgt" in raw:
        return "ccgt"
    if "ocgt" in raw:
        return "ocgt"
    if "biomass" in raw or "bio_and_waste" in raw:
        return "biomass_and_waste"
    if "connection" in raw or "connector" in raw or "interconnector" in raw or "import" in raw:
        return "boundary_import"
    if "hydrogen" in raw and ("battery" in raw or "storage" in raw):
        return "hydrogen_storage"
    if "battery" in raw or "storage" in raw:
        return "battery_storage"
    if "electroly" in raw or "flexible" in raw:
        return "flexible_demand"
    return "unmapped"


# Role of each physical-dispatch flow type in the period energy balance
# (dispatch timeline v2, P0-9 S4).  Only ``supply`` flows are stacked as
# generation; the others are context.  Every flow type the three writers
# (scheme_c_native_psm, perfect_foresight_psm, staged_psm) record is listed;
# tests/test_market_replay.py scans their source to keep this complete.  An
# unknown flow type is ``context``: shown in evidence, never stacked.
FLOW_ROLE_BY_TYPE = {
    "generation": "supply",
    "import": "supply",
    "storage_discharge": "supply",
    "storage_charge": "storage_charge",
    "flexible_demand": "demand",
    "export": "demand",
    "balancing_curtailment": "curtailment",
    "unused_vre": "curtailment",
    "excess_generation": "excess",
    "blackout": "unserved",
}
FLOW_ROLES = ("supply", "demand", "storage_charge", "curtailment", "excess", "unserved", "context")
V8_SUPPLY_STAGE = "final_dispatch"


def flow_role(flow_type: str) -> str:
    return FLOW_ROLE_BY_TYPE.get(str(flow_type), "context")


def v8_summary_flow_role(stage: str, energy_mwh: float) -> str:
    """v8 dispatch summaries: only positive final dispatch is supply; earlier
    stages (ahead schedules) are context for the same period."""

    return "supply" if str(stage) == V8_SUPPLY_STAGE and float(energy_mwh) > 0 else "context"


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _semantic_metadata(database: Path) -> dict[str, object]:
    metadata_path = database.parent / "metadata.json"
    if metadata_path.is_file():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        semantic = payload.get("semantic_metadata")
        if isinstance(semantic, Mapping):
            return {str(key): value for key, value in semantic.items()}
    result: dict[str, object] = {}
    with _read_only_connection(database) as connection:
        if "metadata" not in _tables(connection):
            return result
        for key, value in connection.execute("SELECT key, value FROM metadata"):
            if str(key) in {"schema_version", "trace_level"}:
                result[str(key)] = str(value)
                continue
            try:
                result[str(key)] = json.loads(str(value))
            except json.JSONDecodeError:
                result[str(key)] = str(value)
    return result


# What a period price in ``period_summary.clearing_price_gbp_per_mwh`` means
# (P0-9 S3, Q6).  The read model states it; the UI only renders the label.
PRICE_BASES = (
    "average_period_cost",
    "national_ahead_clearing_price",
    "balance_shadow_price",
    "ahead_settlement_price",
    "not_declared",
)


def period_price_basis(
    semantic: Mapping[str, object], ledger_schema_version: str | None = None,
) -> tuple[str, str]:
    """Return ``(price_basis, price_basis_source)`` for one market ledger.

    ``source`` is ``declared`` when the writer named the basis, ``semantics``
    when it is read from the writer's price semantics text, and
    ``inferred_from_writer`` for the staged (v8) writer, which records a
    national pay-as-clear price but no semantics key (the v8 metadata is
    compared on reopen, so no key is added to it).  Anything else is
    ``not_declared``: the UI then says "basis not recorded".
    """

    declared = semantic.get("price_basis")
    if isinstance(declared, str) and declared in PRICE_BASES:
        return declared, "declared"
    semantics = str(semantic.get("period_price_semantics") or "").lower()
    pricing_rule = str(semantic.get("pricing_rule") or "").lower()
    legacy_basis = str(semantic.get("period_price_basis") or "").lower()
    if semantics.startswith("demand_normalised_total_period_cost"):
        return "average_period_cost", "semantics"
    if "objective derivative" in semantics or pricing_rule == "lp_balance_dual":
        return "balance_shadow_price", "semantics"
    if legacy_basis.startswith("ahead_generator_settlement"):
        return "ahead_settlement_price", "semantics"
    if str(ledger_schema_version or "") == "value.market-ledger/v8":
        return "national_ahead_clearing_price", "inferred_from_writer"
    return "not_declared", "not_declared"


def _ledger_schema_version(database: Path) -> str:
    metadata_path = database.parent / "metadata.json"
    if metadata_path.is_file():
        version = json.loads(metadata_path.read_text(encoding="utf-8")).get("schema_version")
        if version:
            return str(version)
    with _read_only_connection(database) as connection:
        if "metadata" not in _tables(connection):
            return "unknown"
        row = connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
    return str(row[0]) if row else "unknown"


def market_year_bounds(database: Path) -> dict[int, tuple[int, int, int]]:
    """``{year: (first period, last period, distinct periods)}`` of the period ledger (P0-9 S5)."""

    with _read_only_connection(database) as connection:
        if "period_summary" not in _tables(connection):
            return {}
        rows = connection.execute(
            "SELECT year, MIN(period), MAX(period), COUNT(DISTINCT period) "
            "FROM period_summary GROUP BY year ORDER BY year"
        ).fetchall()
    return {int(year): (int(first), int(last), int(count)) for year, first, last, count in rows}


def market_price_basis(database: Path) -> dict[str, str]:
    """``{"price_basis", "price_basis_source"}`` of the run's market ledger."""

    basis, source = period_price_basis(_semantic_metadata(database), _ledger_schema_version(database))
    return {"price_basis": basis, "price_basis_source": source}


def _artifact_hash(database: Path) -> str | None:
    metadata_path = database.parent / "metadata.json"
    if not metadata_path.is_file():
        return None
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    value = payload.get("source_artifact_sha256")
    return str(value) if value else None


def _legacy_staged_market_source(run_root: Path) -> Path:
    run_root = Path(run_root).resolve()
    status_path = run_root / "status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LookupError("Legacy market replay requires a completed legacy Run") from exc
    if not isinstance(status, Mapping) or status.get("status") != "completed":
        raise LookupError("Legacy market replay requires a completed legacy Run")

    market_root = run_root / "model-output" / "market"
    database = market_root / "market.sqlite"
    if database.is_file():
        with _read_only_connection(database) as connection:
            tables = _tables(connection)
            metadata = {
                str(key): str(value)
                for key, value in connection.execute("SELECT key, value FROM metadata")
            } if "metadata" in tables else {}
            version = metadata.get("schema_version", "unknown")
        supported_legacy = {
            f"{namespace}.market-ledger/v{version_number}"
            for namespace in ("value", "gridform")
            for version_number in range(4, 8)
        }
        if version not in supported_legacy:
            raise LookupError("Legacy JSONL fallback is not applicable to this market ledger")

    source = market_root / "staged-market.jsonl"
    if not source.is_file():
        raise LookupError("Legacy staged market JSONL is not available")
    return source


def legacy_staged_market_available(run_root: Path) -> bool:
    """Return whether the run has the legal read-only legacy fallback shape."""

    try:
        _legacy_staged_market_source(run_root)
    except LookupError:
        return False
    return True


def query_legacy_staged_market_jsonl(
    run_root: Path,
    *,
    year: int,
    period_from: int,
    period_to: int,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, object]:
    """Stream one bounded page from an immutable completed legacy JSONL run."""

    try:
        year = int(year)
        period_from = int(period_from)
        period_to = int(period_to)
        limit = int(limit)
        offset = int(offset)
    except (TypeError, ValueError) as exc:
        raise ValueError("Legacy market bounds must be integers") from exc
    if period_from < 0 or period_to < period_from:
        raise ValueError("period_to must be at least non-negative period_from")
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    if offset < 0:
        raise ValueError("offset cannot be negative")

    source = _legacy_staged_market_source(run_root)
    items: list[dict[str, object]] = []
    total = 0
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Legacy staged market JSONL is malformed at line {line_number}"
                ) from exc
            if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
                raise ValueError(
                    f"Legacy staged market JSONL is malformed at line {line_number}"
                )
            payload = row["payload"]
            if payload.get("year") != year:
                continue
            try:
                period = int(payload.get("period"))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Legacy staged market JSONL is malformed at line {line_number}"
                ) from exc
            if not period_from <= period <= period_to:
                continue
            if offset <= total < offset + limit:
                items.append(row)
            total += 1
    return {
        "schema_version": "value.legacy-staged-market-page/v1",
        "source_schema_version": "legacy.staged-market-jsonl",
        "year": year,
        "period_from": period_from,
        "period_to": period_to,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


def market_replay_capabilities(database: Path) -> dict[str, object]:
    semantic = _semantic_metadata(database)
    metadata_path = database.parent / "metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.is_file()
        else {}
    )
    with _read_only_connection(database) as connection:
        tables = _tables(connection)
        years = (
            [int(row[0]) for row in connection.execute(
                "SELECT DISTINCT year FROM period_summary ORDER BY year"
            )]
            if "period_summary" in tables else []
        )
        stages: list[dict[str, object]] = []
        if {"clearing_inputs", "clearing_outcomes"}.issubset(tables):
            stages = [
                {
                    "stage": str(row[0]),
                    "declared_periods": int(row[1]),
                    "outcome_periods": int(row[2]),
                    "order_detail": (
                        "complete" if str(row[0]) in {"ahead", "balancing"}
                        else "stage_summary_only"
                    ),
                }
                for row in connection.execute(
                    """
                    SELECT i.stage, COUNT(*), COUNT(o.input_sha256)
                    FROM clearing_inputs i
                    LEFT JOIN clearing_outcomes o ON o.input_sha256=i.input_sha256
                    GROUP BY i.stage ORDER BY i.stage
                    """
                )
            ]
        physical_rows = (
            int(connection.execute("SELECT COUNT(*) FROM physical_dispatch").fetchone()[0])
            if "physical_dispatch" in tables else 0
        )
        period_rows = (
            int(connection.execute("SELECT COUNT(*) FROM period_summary").fetchone()[0])
            if "period_summary" in tables else 0
        )
        # R3-16: v6+ ledgers keep zonal periods in zonal_period_accounting;
        # an EXISTS-style probe, not a COUNT over the year.
        zonal_rows = int(any(
            table in tables
            and connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None
            for table in ("zonal_period_accounting", "zonal_period_summary")
        ))
        order_rows = (
            int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
            if "orders" in tables else 0
        )
        dispatch_summary_rows = (
            int(connection.execute("SELECT COUNT(*) FROM dispatch_summary").fetchone()[0])
            if "dispatch_summary" in tables else 0
        )
    trace_level = str(metadata.get("trace_level", semantic.get("trace_level", "unknown")))
    bid_replay_available = trace_level == "full" and (bool(stages) or order_rows > 0)
    ledger_schema_version = str(metadata.get("schema_version", semantic.get("schema_version", "unknown")))
    price_basis, price_basis_source = period_price_basis(semantic, ledger_schema_version)
    return {
        "schema_version": REPLAY_CAPABILITIES_SCHEMA,
        "ledger_schema_version": ledger_schema_version,
        "trace_level": trace_level,
        "price_basis": price_basis,
        "price_basis_source": price_basis_source,
        "years": years,
        "period_summary": period_rows > 0,
        "physical_dispatch": physical_rows > 0,
        "physical_dispatch_rows": physical_rows,
        "dispatch_summary_available": dispatch_summary_rows > 0,
        "dispatch_summary_rows": dispatch_summary_rows,
        "zonal_redispatch": zonal_rows > 0,
        "zonal_results_schema_version": (
            ZONAL_REPLAY_CAPABILITY if zonal_rows > 0 else None
        ),
        "auction_replay": bool(stages),
        "bid_replay_available": bid_replay_available,
        "bid_replay_missing_reason": (
            None if bid_replay_available
            else "Bid-level detail was not recorded; create a new Study revision with Full market replay."
        ),
        "missing_detail": (
            [] if bid_replay_available
            else ["individual bids", "bid-level acceptance", "agent-level settlement"]
        ),
        "auction_stages": stages,
        "storage_state": int((metadata.get("rows") or {}).get("storage_state", 0)) > 0,
        "storage_cost_module_id": metadata.get("storage_cost_module_id", "unknown"),
        "declared_inputs": bool(stages),
        "source_artifact_sha256": _artifact_hash(database),
        "semantic_metadata": semantic,
        "missing_reason": (
            None if period_rows else "The selected run has no market period ledger."
        ),
    }


def query_auction_view(
    database: Path,
    *,
    year: int,
    period: int,
    stage: str,
) -> dict[str, object]:
    with _read_only_connection(database) as connection:
        connection.row_factory = sqlite3.Row
        tables = _tables(connection)
        if not {"clearing_inputs", "clearing_outcomes"}.issubset(tables):
            raise LookupError("This run does not contain declared auction evidence")
        row = connection.execute(
            """
            SELECT i.*, o.outcome_json
            FROM clearing_inputs i
            LEFT JOIN clearing_outcomes o ON o.input_sha256=i.input_sha256
            WHERE i.year=? AND i.period=? AND i.stage=?
            """,
            (int(year), int(period), stage),
        ).fetchone()
        # M-D1: the storage offer ledger books each storage offer's own
        # accepted MWh (accounting zone), keyed by the clearing offer id.
        storage_ledger = {
            str(item["clearing_offer_id"]): item
            for item in connection.execute(
                "SELECT clearing_offer_id, accepted_mwh, status, reason_code FROM storage_orders "
                "WHERE year=? AND period=?",
                (int(year), int(period)),
            )
        } if "storage_orders" in tables else {}
    if row is None:
        raise LookupError("The requested market stage is not available")
    envelope = json.loads(str(row["payload_json"]))
    payload = dict(envelope.get("payload") or {})
    outcome = json.loads(str(row["outcome_json"])) if row["outcome_json"] else {}
    offers = list(payload.get("offers") or payload.get("actions") or [])
    accepted_rows = list(outcome.get("accepted") or [])
    outcome_has_order_acceptance = isinstance(outcome.get("accepted"), list)
    accepted_by_asset: defaultdict[str, float] = defaultdict(float)
    prices_by_asset: defaultdict[str, list[float]] = defaultdict(list)
    for accepted in accepted_rows:
        asset_id = str(accepted.get("asset_id") or "unknown")
        power = float(accepted.get("accepted_power_mw", 0.0) or 0.0)
        accepted_by_asset[asset_id] += power
        price = accepted.get("offer_price_gbp_per_mwh")
        if price is not None:
            prices_by_asset[asset_id].append(float(price))
    offer_counts: defaultdict[str, int] = defaultdict(int)
    for offer in offers:
        offer_counts[str(offer.get("asset_id") or "unknown")] += 1
    period_hours = float(payload.get("period_hours", 0.5) or 0.5)
    ordered_offers = sorted(
        enumerate(offers),
        key=lambda item: (
            float(item[1].get("offer_price_gbp_per_mwh", 0.0) or 0.0),
            item[0],
        ),
    )
    result_offers: list[dict[str, object]] = []
    cumulative_offered = 0.0
    cumulative_accepted = 0.0
    for execution_order, (input_order, raw_offer) in enumerate(ordered_offers):
        offer = dict(raw_offer)
        asset_id = str(offer.get("asset_id") or "unknown")
        maximum_power = float(offer.get("maximum_power_mw", 0.0) or 0.0)
        offered_mwh = maximum_power * period_hours
        exact_offer_acceptance = offer_counts[asset_id] == 1
        accepted_mwh = (
            accepted_by_asset[asset_id] * period_hours
            if exact_offer_acceptance and outcome_has_order_acceptance
            else None
        )
        ledger_offer = storage_ledger.get(str(offer.get("offer_id"))) if offer.get("offer_id") is not None else None
        if ledger_offer is not None:
            accepted_mwh = float(ledger_offer["accepted_mwh"])
        cumulative_offered += offered_mwh
        if accepted_mwh is not None:
            cumulative_accepted += accepted_mwh
        result_offers.append({
            **offer,
            "input_order": input_order,
            "execution_order": execution_order,
            "technology": canonical_technology(
                asset_id,
                asset_type=str(offer.get("asset_type") or ""),
                declared_technology=str(offer.get("resource_kind") or ""),
            ),
            "offered_mwh": offered_mwh,
            "accepted_mwh": accepted_mwh,
            "asset_accepted_mwh": (
                accepted_by_asset[asset_id] * period_hours
                if outcome_has_order_acceptance else None
            ),
            "acceptance_granularity": (
                "storage_offer_ledger" if ledger_offer is not None
                else "stage_summary" if not outcome_has_order_acceptance
                else "offer" if exact_offer_acceptance else "asset_aggregate"
            ),
            "offer_status": None if ledger_offer is None else str(ledger_offer["status"]),
            "offer_reason_code": None if ledger_offer is None else str(ledger_offer["reason_code"]),
            "cumulative_offered_mwh": cumulative_offered,
            "cumulative_exact_accepted_mwh": cumulative_accepted,
        })
    target_power = next((
        float(payload[key]) for key in (
            "target_power_mw", "remaining_target_power_mw", "surplus_target_power_mw"
        ) if payload.get(key) is not None
    ), 0.0)
    exact_accepted_prices = [
        float(value)
        for values in prices_by_asset.values()
        for value in values
    ]
    marginal_price = max(exact_accepted_prices) if exact_accepted_prices else None
    return {
        "schema_version": AUCTION_VIEW_SCHEMA,
        "year": int(year),
        "period": int(period),
        "stage": stage,
        "information_scope": str(row["information_scope"]),
        "input_sha256": str(row["input_sha256"]),
        "declared_before_clearing": bool(row["declared_before_clearing"]),
        "period_hours": period_hours,
        "requirement_mwh": target_power * period_hours,
        "offers": result_offers,
        "outcome": outcome,
        "pricing_rule": (
            "retained_bid_at_cost_pay_as_clear_income" if stage == "ahead"
            else "retained_stage_specific_settlement"
        ),
        "marginal_offer_price_gbp_per_mwh": marginal_price,
        "marginal_offer_status": (
            "defined_from_accepted_outcome_prices" if marginal_price is not None
            else "not_separately_defined_by_stage_outcome"
        ),
        "offer_acceptance_coverage": (
            "stage_summary_only" if not outcome_has_order_acceptance
            else "complete" if all(item["acceptance_granularity"] in {"offer", "storage_offer_ledger"} for item in result_offers)
            else "asset_aggregate_for_multi_tranche_resources"
        ),
        "offer_ordering": "ascending offer price; stable input order for ties",
        "source_artifact_sha256": _artifact_hash(database),
        "units": {"energy": "MWh/period", "power": "MW", "price": "GBP/MWh"},
    }


def _period_hours(semantic: Mapping[str, object]) -> float:
    value = semantic.get("period_hours", 0.5)
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = 0.5
    return result if result > 0 else 0.5


def _model_timestamp(year: int, period: int, period_hours: float) -> str:
    # S-中1: the model clock is UTC on a fixed 365-day year (gridform_core.model_clock).
    return period_start_iso(year, period, period_hours)


def query_dispatch_timeline(
    database: Path,
    *,
    year: int,
    resolution: str = "daily",
    start_period: int | None = None,
    end_period: int | None = None,
    period_from: int | None = None,
    period_to: int | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, object]:
    if resolution not in {"half_hour", "daily", "weekly"}:
        raise ValueError("resolution must be half_hour, daily or weekly")
    semantic = _semantic_metadata(database)
    period_hours = _period_hours(semantic)
    bucket_periods = {
        "half_hour": 1,
        "daily": max(int(round(24 / period_hours)), 1),
        "weekly": max(int(round(168 / period_hours)), 1),
    }[resolution]
    try:
        limit, offset = int(limit), int(offset)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be integers") from exc
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    if offset < 0:
        raise ValueError("offset cannot be negative")
    if period_from is not None and start_period is not None:
        raise ValueError("period_from cannot be combined with start_period")
    if period_to is not None and end_period is not None:
        raise ValueError("period_to cannot be combined with end_period")
    start_period = int(period_from if period_from is not None else start_period or 0)
    selected_end = period_to if period_to is not None else end_period
    if start_period < 0:
        raise ValueError("period_from cannot be negative")
    if selected_end is not None and int(selected_end) < start_period:
        raise ValueError("period_to must be at least period_from")
    with _read_only_connection(database) as connection:
        connection.row_factory = sqlite3.Row
        tables = _tables(connection)
        if "period_summary" not in tables:
            raise LookupError("This run does not contain period summaries")
        maximum = connection.execute(
            "SELECT MAX(period) FROM period_summary WHERE year=?", (int(year),)
        ).fetchone()[0]
        if maximum is None:
            raise LookupError("The requested year is not available")
        end = min(int(selected_end) if selected_end is not None else int(maximum), int(maximum))
        if end < start_period:
            raise ValueError("end_period must be at least start_period")
        schema_row = connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone() if "metadata" in tables else None
        ledger_schema_version = str(schema_row[0]) if schema_row else "unknown"
        price_basis, price_basis_source = period_price_basis(semantic, ledger_schema_version)
        supply_boundary = accepted_supply_boundary(connection)
        if ledger_schema_version == "value.market-ledger/v8":
            dispatch_source = "dispatch_summary"
        elif ledger_schema_version in {
            "value.market-ledger/v4", "value.market-ledger/v5",
            "value.market-ledger/v6", "value.market-ledger/v7",
            "gridform.market-ledger/v4", "gridform.market-ledger/v5",
            "gridform.market-ledger/v6", "gridform.market-ledger/v7",
        }:
            dispatch_source = "physical_dispatch"
        else:
            raise LookupError(
                f"Unsupported market ledger schema for replay: {ledger_schema_version}"
            )
        bucket_expression = "CAST((period-?)/? AS INTEGER)"
        range_values = (start_period, bucket_periods, int(year), start_period, end)
        total_buckets = int(connection.execute(
            "SELECT COUNT(*) FROM (SELECT " + bucket_expression + " AS bucket "
            "FROM period_summary WHERE year=? AND period BETWEEN ? AND ? "
            "GROUP BY bucket)",
            range_values,
        ).fetchone()[0])
        selected_buckets = [
            int(row[0])
            for row in connection.execute(
                "SELECT " + bucket_expression + " AS bucket FROM period_summary "
                "WHERE year=? AND period BETWEEN ? AND ? GROUP BY bucket "
                "ORDER BY bucket LIMIT ? OFFSET ?",
                (*range_values, limit, offset),
            )
        ]
        if not selected_buckets:
            return {
                "schema_version": DISPATCH_TIMELINE_SCHEMA,
                "year": int(year), "resolution": resolution,
                "total": total_buckets, "limit": limit, "offset": offset,
                "dispatch_source": dispatch_source,
                "dispatch_summary_available": False,
                "price_basis": price_basis, "price_basis_source": price_basis_source,
                "items": [], "units": {"energy": "MWh", "price": "GBP/MWh"},
            }
        bucket_placeholders = ",".join("?" for _ in selected_buckets)
        summary_rows = connection.execute(
            f"""
            SELECT CAST((period-?)/? AS INTEGER) AS bucket,
                   MIN(period) AS period_start, MAX(period) AS period_end,
                   COUNT(DISTINCT period) AS period_count,
                   SUM(forecast_demand_mwh) AS forecast_demand_mwh,
                   SUM(real_demand_mwh) AS real_demand_mwh,
                   SUM(accepted_supply_mwh) AS accepted_supply_mwh,
                   SUM(storage_charge_mwh) AS storage_charge_mwh,
                   SUM(storage_discharge_mwh) AS storage_discharge_mwh,
                   SUM(flexible_demand_mwh) AS flexible_demand_mwh,
                   SUM(export_mwh) AS export_mwh,
                   SUM(vre_available_mwh) AS vre_available_mwh,
                   SUM(vre_accepted_mwh) AS vre_accepted_mwh,
                   SUM(curtailed_mwh) AS curtailed_mwh,
                   SUM(import_mwh) AS import_mwh,
                   CASE WHEN SUM(real_demand_mwh)>0
                        THEN SUM(clearing_price_gbp_per_mwh*real_demand_mwh)/SUM(real_demand_mwh)
                        ELSE AVG(clearing_price_gbp_per_mwh) END AS price_gbp_per_mwh,
                   SUM(blackout_mwh) AS blackout_mwh,
                   SUM(excess_mwh) AS excess_mwh,
                   SUM(ABS(energy_balance_residual_mwh)) AS energy_balance_residual_mwh,
                   SUM(ABS(compatibility_adjustment_mwh)) AS compatibility_adjustment_mwh,
                   SUM(ABS(raw_energy_balance_residual_mwh)) AS raw_energy_balance_residual_mwh
            FROM period_summary
            WHERE year=? AND period BETWEEN ? AND ?
              AND CAST((period-?)/? AS INTEGER) IN ({bucket_placeholders})
            GROUP BY bucket ORDER BY bucket
            """,
            (
                start_period, bucket_periods, int(year), start_period, end,
                start_period, bucket_periods, *selected_buckets,
            ),
        ).fetchall()
        stress_by_bucket = _bucket_stress(
            connection, tables,
            year=int(year), start_period=start_period, end_period=end,
            bucket_periods=bucket_periods, buckets=selected_buckets,
        )
        flows_by_bucket: defaultdict[int, list[dict[str, object]]] = defaultdict(list)
        dispatch_summary_rows = 0
        if dispatch_source == "dispatch_summary" and "dispatch_summary" in tables:
            dispatch_summary_rows = int(connection.execute(
                "SELECT COUNT(*) FROM dispatch_summary "
                f"WHERE year=? AND period BETWEEN ? AND ? "
                f"AND CAST((period-?)/? AS INTEGER) IN ({bucket_placeholders})",
                (
                    int(year), start_period, end, start_period, bucket_periods,
                    *selected_buckets,
                ),
            ).fetchone()[0])
        if dispatch_source == "dispatch_summary" and dispatch_summary_rows:
            for row in connection.execute(
                f"""
                SELECT CAST((period-?)/? AS INTEGER) AS bucket,
                       stage, zone_id, technology,
                       SUM(accepted_dispatch_mwh) AS energy_mwh
                FROM dispatch_summary
                WHERE year=? AND period BETWEEN ? AND ?
                  AND CAST((period-?)/? AS INTEGER) IN ({bucket_placeholders})
                GROUP BY bucket, stage, zone_id, technology
                ORDER BY bucket, stage, zone_id, technology
                """,
                (
                    start_period, bucket_periods, int(year), start_period, end,
                    start_period, bucket_periods, *selected_buckets,
                ),
            ):
                raw_technology = str(row["technology"])
                flows_by_bucket[int(row["bucket"])].append({
                    # R3-02: the staged writer records raw technology names
                    # ("CCGT", "onshore"); the read model sends the canonical
                    # group and keeps the raw name.
                    "technology": canonical_technology(raw_technology, declared_technology=raw_technology),
                    "raw_technology": raw_technology,
                    "flow_type": "accepted_dispatch",
                    "role": v8_summary_flow_role(str(row["stage"]), float(row["energy_mwh"])),
                    "stage": str(row["stage"]),
                    "zone_id": str(row["zone_id"]),
                    "evidence_scope": (
                        f"zone:{row['zone_id']};stage:{row['stage']}"
                    ),
                    "energy_mwh": float(row["energy_mwh"]),
                    "balance_component_mwh": float(row["energy_mwh"]),
                })
        elif dispatch_source == "physical_dispatch" and "physical_dispatch" in tables:
            for row in connection.execute(
                f"""
                SELECT CAST((period-?)/? AS INTEGER) AS bucket,
                       technology, flow_type, evidence_scope,
                       SUM(energy_mwh) AS energy_mwh,
                       SUM(balance_component_mwh) AS balance_component_mwh
                FROM physical_dispatch
                WHERE year=? AND period BETWEEN ? AND ?
                  AND CAST((period-?)/? AS INTEGER) IN ({bucket_placeholders})
                GROUP BY bucket, technology, flow_type, evidence_scope
                ORDER BY bucket, flow_type, technology
                """,
                (
                    start_period, bucket_periods, int(year), start_period, end,
                    start_period, bucket_periods, *selected_buckets,
                ),
            ):
                flows_by_bucket[int(row["bucket"])].append({
                    "technology": str(row["technology"]),
                    "flow_type": str(row["flow_type"]),
                    "role": flow_role(str(row["flow_type"])),
                    "evidence_scope": str(row["evidence_scope"]),
                    "energy_mwh": float(row["energy_mwh"]),
                    "balance_component_mwh": float(row["balance_component_mwh"]),
                })
    items = []
    for row in summary_rows:
        bucket = int(row["bucket"])
        value = {key: row[key] for key in row.keys() if key != "bucket"}
        value = {
            key: (float(item) if isinstance(item, float) else int(item) if isinstance(item, int) else item)
            for key, item in value.items()
        }
        value.update({
            "timestamp_start": _model_timestamp(int(year), int(row["period_start"]), period_hours),
            "timestamp_end": _model_timestamp(int(year), int(row["period_end"]) + 1, period_hours),
            "flows": flows_by_bucket.get(bucket, []),
        })
        if stress_by_bucket is not None:
            value.update(stress_by_bucket.get(bucket, _empty_stress(stress_basis(stress_by_bucket))))
        items.append(value)
    return {
        "schema_version": DISPATCH_TIMELINE_SCHEMA,
        "physical_dispatch_schema_version": PHYSICAL_DISPATCH_SCHEMA,
        "year": int(year),
        "resolution": resolution,
        "period_hours": period_hours,
        **ledger_clock(semantic),
        "total": total_buckets,
        "limit": limit,
        "offset": offset,
        "dispatch_source": dispatch_source,
        "dispatch_summary_available": dispatch_summary_rows > 0,
        "items": items,
        "source_artifact_sha256": _artifact_hash(database),
        "price_aggregation": "demand_weighted_mean_gbp_per_mwh",
        "price_basis": price_basis,
        "price_basis_source": price_basis_source,
        # P0-4 S3: residuals and adjustments are summed as absolute values, so
        # a +2 and a -2 in one window show 4, not a cancelled 0.
        "residual_aggregation": "sum_of_absolute_period_values",
        "stress_recorded": stress_by_bucket is not None,
        "accepted_supply_boundary": supply_boundary,
        "units": {"energy": "MWh", "price": "GBP/MWh"},
    }


STRESS_COLUMNS = (
    "period", "stage", "forecast_demand_mwh", "real_demand_mwh", "accepted_supply_mwh",
    "storage_charge_mwh", "flexible_demand_mwh", "export_mwh", "blackout_mwh",
    "excess_mwh", "curtailed_mwh",
)


def _empty_stress(basis: str) -> dict[str, object]:
    return {
        "shortfall_mwh": 0.0, "shortfall_upper_mwh": 0.0, "shortfall_basis": basis,
        "stress_periods": 0, "possible_stress_periods": 0,
    }


def accepted_supply_boundary(connection: sqlite3.Connection) -> dict[str, object]:
    """The energy-balance boundary ``accepted_supply_mwh`` is recorded at (R5 R-低10).

    The corrected PSM records gross supply at the full node (it covers demand
    plus storage charge, export and flexible load); the doctoral PSM records
    supply at its source-classified node, where storage charged from
    pre-balancing surplus is routed outside accepted supply.  The UI states
    the boundary next to the "Accepted supply" figure.
    """

    from . import energy_balance_contract as balance
    from .energy_balance_oracle import read_metadata, resolve_boundary

    try:
        boundary = resolve_boundary(read_metadata(connection))
    except (sqlite3.Error, ValueError, TypeError):
        return {"boundary_id": balance.UNKNOWN_BOUNDARY, "formula": None, "description": None}
    definition = balance.BOUNDARIES.get(str(boundary.get("boundary_id")))
    return {
        "boundary_id": str(boundary.get("boundary_id")),
        "formula": definition.formula if definition else None,
        "description": definition.description if definition else None,
    }


def stress_basis(stress_by_bucket: Mapping[int, Mapping[str, object]]) -> str:
    return next((str(row["shortfall_basis"]) for row in stress_by_bucket.values()), "lower_bound")


def _bucket_stress(
    connection: sqlite3.Connection,
    tables: set[str],
    *,
    year: int,
    start_period: int,
    end_period: int,
    bucket_periods: int,
    buckets: list[int],
) -> dict[int, dict[str, object]] | None:
    """A2 stress events per window bucket, from the same contract as the oracle.

    ``shortfall_mwh`` is the certain shortfall summed over stress periods,
    estimated by :func:`energy_balance_contract.estimate_shortfall` on the
    boundary the oracle evaluates (declared in the ledger with every input it
    needs), so window sums equal the run-level stress: exact on a declared
    full-node boundary or with the surplus routing, otherwise the demand that
    accepted supply did not meet (``shortfall_basis='lower_bound'``;
    ``shortfall_upper_mwh`` bounds it).  Only the final dispatch row of a
    period counts when a period has several stages.  None when the ledger
    lacks the period columns (the UI then shows "not recorded").
    """

    from . import energy_balance_contract as balance
    from .energy_balance_oracle import read_metadata, read_surplus_routing, resolve_boundary

    if "period_summary" not in tables:
        return None
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(period_summary)")}
    if any(column not in columns for column in STRESS_COLUMNS):
        return None
    boundary = resolve_boundary(read_metadata(connection))
    tier = boundary["tolerance_tier"]
    routing, _missing = read_surplus_routing(
        connection, year=year, first_period=start_period, last_period=end_period,
    )
    declared = boundary["source"] == "metadata" and boundary["known"]
    needs_routing = boundary["boundary_id"] == balance.DEFAULT_PSM_SURPLUS_NODE_V1
    evaluable = boundary["boundary_id"] if declared and (routing is not None or not needs_routing) else None
    placeholders = ",".join("?" for _ in buckets)
    rows_by_period: dict[int, list[sqlite3.Row]] = defaultdict(list)
    previous_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        for row in connection.execute(
            "SELECT " + ", ".join(STRESS_COLUMNS) + " FROM period_summary "
            "WHERE year=? AND period BETWEEN ? AND ? "
            f"AND CAST((period-?)/? AS INTEGER) IN ({placeholders})",
            (year, start_period, end_period, start_period, bucket_periods, *buckets),
        ):
            rows_by_period[int(row["period"])].append(row)
    finally:
        connection.row_factory = previous_factory
    result: dict[int, dict[str, object]] = {}
    exact_all = True
    for period, rows in sorted(rows_by_period.items()):
        if len(rows) > 1:
            rows = [row for row in rows if str(row["stage"]) == "final_dispatch"]
        if len(rows) != 1:
            continue
        row = rows[0]
        u_out = w_in = None
        if routing is not None:
            u_out, w_in = balance.surplus_terms(routing.get((year, period), []))
        flows = balance.PeriodFlows(
            year=year, period=period, stage=str(row["stage"]),
            supply_mwh=float(row["accepted_supply_mwh"]), blackout_mwh=float(row["blackout_mwh"]),
            demand_mwh=float(row["real_demand_mwh"]), storage_charge_mwh=float(row["storage_charge_mwh"]),
            export_mwh=float(row["export_mwh"]), flexible_demand_mwh=float(row["flexible_demand_mwh"]),
            excess_mwh=float(row["excess_mwh"]), curtailed_mwh=float(row["curtailed_mwh"]),
            forecast_demand_mwh=float(row["forecast_demand_mwh"]), u_out_mwh=u_out, w_in_mwh=w_in,
        )
        if not flows.is_finite():
            continue
        estimate = balance.estimate_shortfall(flows, evaluable)
        exact_all = exact_all and estimate.exact
        tol = balance.tolerance(tier, flows.demand_mwh, flows.supply_mwh)
        bucket = (period - start_period) // bucket_periods
        stats = result.setdefault(bucket, {
            "shortfall_mwh": 0.0, "shortfall_upper_mwh": 0.0,
            "stress_periods": 0, "possible_stress_periods": 0,
        })
        if estimate.lower_mwh > tol:
            stats["stress_periods"] = int(stats["stress_periods"]) + 1
            stats["shortfall_mwh"] = float(stats["shortfall_mwh"]) + estimate.lower_mwh
        if estimate.upper_mwh > tol:
            stats["possible_stress_periods"] = int(stats["possible_stress_periods"]) + 1
            stats["shortfall_upper_mwh"] = float(stats["shortfall_upper_mwh"]) + estimate.upper_mwh
    basis = "exact" if exact_all and rows_by_period else "lower_bound"
    for stats in result.values():
        stats["shortfall_basis"] = basis
        stats["shortfall_mwh"] = float(f"{float(stats['shortfall_mwh']):.12g}")
        stats["shortfall_upper_mwh"] = float(f"{float(stats['shortfall_upper_mwh']):.12g}")
    for bucket in buckets:
        result.setdefault(bucket, _empty_stress(basis))
    return result


def _event_statistics(
    values: list[float], periods: list[int], year: int, period_hours: float, basis: str,
) -> dict[str, object]:
    """Affected periods, longest run and peak of one per-period event series."""

    longest = 0
    current = 0
    for value in values:
        if value > 1e-9:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    peak_index = max(range(len(values)), key=values.__getitem__) if values else None
    peak_period = periods[peak_index] if peak_index is not None else None
    return {
        "basis": basis,
        "affected_periods": sum(value > 1e-9 for value in values),
        "longest_event_periods": longest,
        "longest_event_hours": longest * period_hours,
        "peak_event_mwh": values[peak_index] if peak_index is not None else None,
        "peak_event_period": peak_period,
        "peak_event_timestamp": (
            _model_timestamp(year, peak_period, period_hours) if peak_period is not None else None
        ),
    }


def query_vre_curtailment_summary(database: Path) -> dict[str, object]:
    semantic = _semantic_metadata(database)
    period_hours = _period_hours(semantic)
    expected_periods = int(round(8760 / period_hours))
    relationship = str(semantic.get("excess_relationship", "unknown"))
    excess_scope = str(semantic.get("excess_scope", "unknown"))
    curtailment_semantics = str(semantic.get("curtailment_semantics", "unknown"))
    # C20 (P0-6 column semantics, P0-9 M7): under the corrected rule set
    # ``curtailed`` is VRE availability minus gross VRE output and ``excess`` is
    # the non-VRE spill, so "excess + curtailment" is not a VRE event basis; the
    # unused-VRE events then carry the third basis ``corrected_unused_vre``.
    corrected_columns = curtailment_semantics == CORRECTED_CURTAILMENT_SEMANTICS
    with _read_only_connection(database) as connection:
        connection.row_factory = sqlite3.Row
        if "period_summary" not in _tables(connection):
            raise LookupError("This run does not contain VRE period evidence")
        years = [int(row[0]) for row in connection.execute(
            "SELECT DISTINCT year FROM period_summary ORDER BY year"
        )]
        results = []
        for year in years:
            rows = connection.execute(
                """
                SELECT period, vre_available_mwh, vre_accepted_mwh,
                       curtailed_mwh, excess_mwh, storage_charge_mwh,
                       export_mwh, flexible_demand_mwh
                FROM period_summary WHERE year=? ORDER BY period
                """,
                (year,),
            ).fetchall()
            available = sum(float(row["vre_available_mwh"]) for row in rows)
            accepted = sum(float(row["vre_accepted_mwh"]) for row in rows)
            neutral_unused = sum(max(
                float(row["vre_available_mwh"]) - float(row["vre_accepted_mwh"]), 0.0
            ) for row in rows)
            balancing_curtailment = sum(float(row["curtailed_mwh"]) for row in rows)
            excess = sum(float(row["excess_mwh"]) for row in rows)
            split_excess: float | None = None
            split_curtailment: float | None = None
            if relationship == "separate_prebalancing":
                split_excess = excess
                split_curtailment = balancing_curtailment
            reconciliation = available - accepted - neutral_unused
            # G1-08 (P0-9 S8): the two event bases are reported separately so the
            # UI never mixes unused VRE with pre-balancing excess plus
            # curtailment; the legacy top-level event fields are the statistics
            # of the run's event basis (excess + curtailment when the ledger
            # separates them, unused VRE otherwise).
            periods = [int(row["period"]) for row in rows]
            unused_values = [max(
                float(row["vre_available_mwh"]) - float(row["vre_accepted_mwh"]), 0.0
            ) for row in rows]
            unused_vre_events = _event_statistics(
                unused_values, periods, year, period_hours,
                "corrected_unused_vre" if corrected_columns else "unused_vre",
            )
            excess_curtailment_events = (
                _event_statistics(
                    [float(row["curtailed_mwh"]) + float(row["excess_mwh"]) for row in rows],
                    periods, year, period_hours, "excess_plus_balancing_curtailment",
                )
                if relationship == "separate_prebalancing" and not corrected_columns else None
            )
            legacy_events = {
                key: value
                for key, value in (excess_curtailment_events or unused_vre_events).items()
                if key != "basis"
            }
            results.append({
                "year": year,
                "period_count": len(rows),
                "first_period": int(rows[0]["period"]) if rows else None,
                "last_period": int(rows[-1]["period"]) if rows else None,
                # A full chronology covers periods 0..N-1 exactly, not just N rows.
                "full_chronology": (
                    len(rows) == expected_periods
                    and bool(rows)
                    and int(rows[0]["period"]) == 0
                    and int(rows[-1]["period"]) == expected_periods - 1
                ),
                "available_vre_mwh": available,
                "accepted_vre_mwh": accepted,
                "neutral_unused_vre_mwh": neutral_unused,
                "pre_balancing_excess_mwh": split_excess,
                "pre_balancing_excess_scope": excess_scope,
                "balancing_curtailment_mwh": split_curtailment,
                "reported_excess_mwh": excess if relationship != "unknown" else None,
                "reported_balancing_curtailment_mwh": balancing_curtailment if relationship != "unknown" else None,
                "vre_utilisation_fraction": accepted / available if available > 0 else None,
                "average_unused_vre_fraction": neutral_unused / available if available > 0 else None,
                **legacy_events,
                "storage_charge_mwh": sum(float(row["storage_charge_mwh"]) for row in rows),
                "export_mwh": sum(float(row["export_mwh"]) for row in rows),
                "flexible_demand_mwh": sum(float(row["flexible_demand_mwh"]) for row in rows),
                "vre_identity_residual_mwh": reconciliation,
                "coverage_status": (
                    "complete_vre_boundary_with_separate_inflexible_excess"
                    if excess_scope == "inflexible_mixed" and relationship == "separate_prebalancing"
                    else "complete_unsplit_vre_unused"
                    if relationship == "alias_of_unused_vre"
                    else "partial_semantic_attribution"
                ),
                "event_basis": (
                    "corrected_unused_vre" if corrected_columns
                    else "excess_plus_balancing_curtailment"
                    if relationship == "separate_prebalancing" else "unused_vre"
                ),
                "unused_vre_events": unused_vre_events,
                "excess_curtailment_events": excess_curtailment_events,
                "marginal_curtailment_status": "not_evaluated",
                "marginal_curtailment_reason": "No versioned marginal-capacity experiment artifact is attached to this run.",
            })
    return {
        "schema_version": VRE_SUMMARY_SCHEMA,
        "definition_id": "value.vre-excess-curtailment-accounting/v1",
        "years": results,
        "period_hours": period_hours,
        **ledger_clock(semantic),
        "excess_relationship": relationship,
        "excess_scope": excess_scope,
        "curtailment_semantics": curtailment_semantics,
        "source_artifact_sha256": _artifact_hash(database),
        "units": {"energy": "MWh", "rate": "fraction"},
    }


def query_vre_curtailment_timeline(database: Path, **kwargs: object) -> dict[str, object]:
    timeline = query_dispatch_timeline(database, **kwargs)
    items = []
    for raw in timeline["items"]:  # type: ignore[index]
        row = dict(raw)
        available = float(row.get("vre_available_mwh", 0.0) or 0.0)
        accepted = float(row.get("vre_accepted_mwh", 0.0) or 0.0)
        row["neutral_unused_vre_mwh"] = max(available - accepted, 0.0)
        items.append(row)
    return {
        **timeline,
        "schema_version": VRE_TIMELINE_SCHEMA,
        "dispatch_timeline_schema_version": DISPATCH_TIMELINE_SCHEMA,
        "items": items,
    }


STRESS_EVENT_PAGE_LIMIT = 200


def query_stress_events(
    database: Path,
    *,
    year: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    """A2 stress events of a run, full year, paged and ordered by start period.

    Read-only view of the ledger's ``stress_event`` table (contiguous periods in
    which accepted supply fell short of demand; the shortfall is booked as
    unserved energy, dispatch is unchanged).  A ledger written before the
    table existed returns ``status='not_recorded'`` and no items: the UI then
    says so instead of "no stress events" (spec 4.4, P0-9 M7).
    """

    limit = max(1, min(int(limit), STRESS_EVENT_PAGE_LIMIT))
    offset = max(0, int(offset))
    semantic = _semantic_metadata(database)
    period_hours = _period_hours(semantic)
    result: dict[str, object] = {
        "schema_version": STRESS_EVENTS_SCHEMA,
        "status": "not_recorded",
        "year": year,
        "items": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "has_more": False,
        "order": "start_period ascending (numeric)",
        "event_type": "stress",
        "event_definition": "contiguous periods in which accepted supply fell short of demand (decision A2)",
        "shortfall_basis": "exact",
        **ledger_clock(semantic),
        "period_hours": period_hours,
        "source_artifact_sha256": _artifact_hash(database),
        "units": {"energy": "MWh"},
    }
    with _read_only_connection(database) as connection:
        if "stress_event" not in _tables(connection):
            return result
        where, parameters = ("WHERE year=?", (int(year),)) if year is not None else ("", ())
        total, periods, shortfall = connection.execute(
            f"SELECT COUNT(*), COALESCE(SUM(periods), 0), COALESCE(SUM(shortfall_mwh), 0.0) FROM stress_event {where}",
            parameters,
        ).fetchone()
        rows = connection.execute(
            "SELECT year, event_index, first_period, last_period, periods, shortfall_mwh, "
            f"recorded_unserved_mwh, hidden_unserved_mwh, boundary_id FROM stress_event {where} "
            "ORDER BY year, first_period, event_index LIMIT ? OFFSET ?",
            (*parameters, limit, offset),
        ).fetchall()
    result.update(
        status="recorded",
        total=int(total),
        has_more=offset + len(rows) < int(total),
        stress_periods=int(periods),
        shortfall_mwh=float(shortfall),
        items=[
            {
                "year": int(row[0]),
                "event_index": int(row[1]),
                "start_period": int(row[2]),
                "last_period": int(row[3]),
                "periods": int(row[4]),
                "start_timestamp": _model_timestamp(int(row[0]), int(row[2]), period_hours),
                "shortfall_mwh": float(row[5]),
                "recorded_unserved_mwh": float(row[6]),
                "hidden_unserved_mwh": float(row[7]),
                "boundary_id": str(row[8]),
                "event_type": "stress",
            }
            for row in rows
        ],
    )
    return result
