"""Generate the UI contract fixtures from the real read-model functions.

P0-9 S2 generator (plan 4.9; the generator is part of M0, captured on HEAD).

    python -B tests/ui_contract_fixtures.py --check   # default: regenerate, compare with the committed files
    python -B tests/ui_contract_fixtures.py --write   # rewrite tests/fixtures/ui-contract/

The frontend's market views are written against hand-made mocks, and R3-01 /
R3-02 showed that those mocks drift from what the API really sends.  These
fixtures are produced by the *same functions with the same arguments* that
``backend/server.py`` uses for each request the UI makes
(``app/page.tsx`` MarketReplayView/CurtailmentView, ``AuditView.tsx``), on
three ledgers:

``toy-v7``
    four half-hour periods written with ``create_market_ledger`` (the v7
    writer of the default PSM): physical-dispatch flows, ahead and
    curtailment clearing evidence, storage state.  Prices are distinct from
    every offer price, include a legitimate 0.0, and a curtailment and an
    excess period are kept apart.
``toy-v8``
    four periods, two zones, written with ``create_staged_market_ledger_v8``
    at trace level ``summary`` (the VALUE-UK default): ``dispatch_summary``
    rows with the raw technology names the staged writer records, the same
    technology in both zones, and no physical-dispatch detail.
``value-101-day``
    a real ``value_101_day`` Run of golden case C3 (frozen project
    ``tests/golden/projects/C3.json``: default chain, dynamic storage cost,
    full market trace) run with ``run_project_application`` in a temporary
    directory.

Every fixture records the request it answers (``request.path`` and
``request.query``) so that unit tests and e2e route mocks can use the
payload as-is.  The one value that identifies the artifact rather than the
contract, the SHA-256 of the SQLite file bytes (``source_artifact_sha256``:
it depends on SQLite's page layout and version and changes with any value in
any table), is replaced by :data:`VOLATILE_PLACEHOLDER`; nothing else is
rewritten.  ``--check``
compares numbers with a relative tolerance of :data:`RELATIVE_TOLERANCE`, so
an intentional read-model or model change shows up as an explicit
regeneration in the same commit.

Two physical invariants are evaluated on the generated payloads
(:func:`invariant_report`): in every dispatch bucket the supply flows add up
to ``accepted_supply_mwh`` (supply = ``generation``/``import``/
``storage_discharge`` flows of a v4-v7 ledger, ``final_dispatch`` rows of a
v8 dispatch summary), and every period of a v8 ledger conserves energy
(per-period supply sum equals ``accepted_supply_mwh``, and the balance
recomputed from the payload's own terms is zero and agrees with the recorded
residual; a missing term is a violation).  The supply classification here
encodes HEAD semantics; P0-9 S4 replaces it with the backend's flow ``role``.

Budgets (plan 4.9 S2): one generation <= 30 s, all fixtures <= 200 KB.
"""

from __future__ import annotations

# P0 rule (P0_CONVENTIONS section 2): never write bytecode, even when started
# without -B.  Inherited by every subprocess through the environment.
import os as _os
import sys as _sys

_sys.dont_write_bytecode = True
_os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
import contextlib
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "ui-contract"
SCHEMA_VERSION = "value.ui-contract-fixture/v1"
INDEX_SCHEMA_VERSION = "value.ui-contract-fixture-index/v1"
INDEX_NAME = "index.json"
GENERATOR = "tests/ui_contract_fixtures.py"
REAL_CASE = "C3"
RUN_ID = "ui-contract-run"
YEAR = 2025
SIZE_BUDGET_BYTES = 200_000
TIME_BUDGET_SECONDS = 30.0
RELATIVE_TOLERANCE = 1e-9
ABSOLUTE_TOLERANCE = 1e-12
INVARIANT_TOLERANCE_MWH = 1e-6
VOLATILE_PLACEHOLDER = "<sqlite-file-sha256>"
# Keys whose value is a hash of the SQLite file bytes.  Reproducible on one
# host, but tied to SQLite's page layout and version, and any change anywhere
# in the ledger would rewrite it in every fixture of that source.
VOLATILE_KEYS = frozenset({"source_artifact_sha256"})
SOURCES = ("toy-v7", "toy-v8", "value-101-day")
V7_SUPPLY_FLOW_TYPES = frozenset({"generation", "import", "storage_discharge"})
V8_SUPPLY_STAGE = "final_dispatch"
SEMANTIC_METADATA = {
    "period_hours": 0.5,
    "timezone": "Europe/London",
    "calendar": "fixed_365_day_local_periods",
    "excess_scope": "inflexible_mixed",
    "excess_relationship": "separate_prebalancing",
}


# --------------------------------------------------------------------------
# Ledgers
# --------------------------------------------------------------------------

def _period_row(period: int, **values: float) -> Any:
    from gridform_core.market_ledger import PeriodLedgerRow

    base = dict(
        year=YEAR, period=period, stage="final_dispatch",
        forecast_demand_mwh=values.get("real_demand_mwh", 0.0),
        real_demand_mwh=0.0, accepted_supply_mwh=0.0,
        storage_charge_mwh=0.0, storage_discharge_mwh=0.0, flexible_demand_mwh=0.0,
        export_mwh=0.0, vre_available_mwh=0.0, vre_accepted_mwh=0.0, curtailed_mwh=0.0,
        import_mwh=0.0, clearing_price_gbp_per_mwh=0.0, physical_resource_cost_gbp=0.0,
        market_payment_gbp=0.0, policy_transfer_gbp=0.0, blackout_mwh=0.0, excess_mwh=0.0,
        energy_balance_residual_mwh=0.0,
    )
    base.update(values)
    return PeriodLedgerRow(**base)


# (demand, price, solar, ccgt, import, storage charge, storage discharge, curtailment, excess)
TOY_V7_PERIODS = (
    (10.0, 61.25, 4.0, 6.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (12.0, 70.5, 5.0, 8.0, 0.0, 1.0, 0.0, 0.0, 0.0),
    (9.0, 0.0, 6.0, 3.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    (11.0, 85.0, 0.5, 8.0, 1.5, 0.0, 1.0, 0.0, 2.0),
)


def build_toy_v7(folder: Path) -> Path:
    """Four periods through the v7 writer used by the default PSM."""

    from gridform_core.clearing_inputs import ClearingInputRow, ClearingOutcomeRow
    from gridform_core.market_ledger import PhysicalDispatchRow, StorageStateRow, create_market_ledger

    database = folder / "market.sqlite"
    ledger = create_market_ledger(
        database, "full", storage_cost_module_id="dynamic-annual-storage-cost",
        semantic_metadata=dict(SEMANTIC_METADATA, period_price_semantics="demand_normalised_total_period_cost; not a stage clearing-price proof"),
    )
    state = 2.0
    for period, (demand, price, solar, ccgt, imported, charge, discharge, curtailed, excess) in enumerate(TOY_V7_PERIODS):
        supply = solar + ccgt + imported + discharge
        available = solar + curtailed
        ledger.record_period(_period_row(
            period, real_demand_mwh=demand, accepted_supply_mwh=supply, storage_charge_mwh=charge,
            storage_discharge_mwh=discharge, vre_available_mwh=available, vre_accepted_mwh=solar,
            curtailed_mwh=curtailed, import_mwh=imported, clearing_price_gbp_per_mwh=price,
            physical_resource_cost_gbp=ccgt * 55.0, market_payment_gbp=demand * price, excess_mwh=excess,
            energy_balance_residual_mwh=supply - demand - charge,
        ))
        flows = [
            PhysicalDispatchRow(YEAR, period, "solar-a", "solar", "generation", solar, solar, "final_demand_serving_generation"),
            PhysicalDispatchRow(YEAR, period, "gas-a", "ccgt", "generation", ccgt, ccgt, "final_demand_serving_generation"),
        ]
        if imported:
            flows.append(PhysicalDispatchRow(YEAR, period, "ifa-link", "boundary_import", "import", imported, imported, "final_boundary_import"))
        if charge:
            flows.append(PhysicalDispatchRow(YEAR, period, "battery-a", "battery_storage", "storage_charge", charge, -charge, "final_storage_input"))
        if discharge:
            flows.append(PhysicalDispatchRow(YEAR, period, "battery-a", "battery_storage", "storage_discharge", discharge, discharge, "final_storage_output"))
        if curtailed:
            flows.append(PhysicalDispatchRow(YEAR, period, "vre", "vre_aggregate", "balancing_curtailment", curtailed, 0.0, "reported balancing-stage curtailment"))
        if excess:
            flows.append(PhysicalDispatchRow(YEAR, period, "inflexible", "inflexible_mixed", "excess_generation", excess, 0.0, "pre-balancing excess may include VRE, nuclear or natural-flow hydro"))
        ledger.record_physical_dispatch(flows)
        state = state + charge - discharge
        ledger.record_storage((StorageStateRow(YEAR, period, "battery-a", state, charge, discharge, 2.0, 4.0),))
    ahead = ClearingInputRow.create(
        year=YEAR, period=0, stage="ahead", information_scope="forecast demand and eligible offers",
        payload={
            "period_hours": 0.5, "target_power_mw": 20.0,
            "offers": [
                {"offer_id": "gas-a:0", "asset_id": "gas-a", "asset_type": "CCGTGenerator", "resource_kind": "thermal", "offer_price_gbp_per_mwh": 50.0, "maximum_power_mw": 16.0},
                {"offer_id": "solar-a:0", "asset_id": "solar-a", "asset_type": "SolarGenerator", "resource_kind": "vre", "offer_price_gbp_per_mwh": 0.0, "maximum_power_mw": 8.0},
                {"offer_id": "battery-a:0", "asset_id": "battery-a", "asset_type": "Battery", "resource_kind": "storage_discharge", "offer_price_gbp_per_mwh": 20.0, "maximum_power_mw": 2.0},
                {"offer_id": "battery-a:1", "asset_id": "battery-a", "asset_type": "Battery", "resource_kind": "storage_discharge", "offer_price_gbp_per_mwh": 30.0, "maximum_power_mw": 2.0},
            ],
        },
    )
    ledger.record_clearing_input(ahead)
    ledger.record_clearing_outcome(ClearingOutcomeRow.create(ahead.input_sha256, {"accepted": [
        {"asset_id": "solar-a", "accepted_power_mw": 8.0, "offer_price_gbp_per_mwh": 0.0},
        {"asset_id": "gas-a", "accepted_power_mw": 12.0, "offer_price_gbp_per_mwh": 50.0},
    ]}))
    curtailment = ClearingInputRow.create(
        year=YEAR, period=2, stage="curtailment", information_scope="realised demand and post-ahead schedule",
        payload={"period_hours": 0.5, "surplus_target_power_mw": 2.0, "actions": [
            {"offer_id": "charge", "asset_id": "battery-a", "asset_type": "Battery", "resource_kind": "storage_charge", "offer_price_gbp_per_mwh": 1.0, "maximum_power_mw": 2.0},
        ]},
    )
    ledger.record_clearing_input(curtailment)
    ledger.record_clearing_outcome(ClearingOutcomeRow.create(curtailment.input_sha256, {"storage_charge_power_mw": 0.0, "remaining_excess_power_mw": 2.0}))
    ledger.close()
    return database


# (demand, price, [(zone, technology, MWh)], storage charge, storage discharge)
TOY_V8_PERIODS = (
    (20.0, 61.25, [("north", "onshore", 9.0), ("north", "CCGT", 4.0), ("south", "CCGT", 7.0)], 0.0, 0.0),
    (22.0, 64.0, [("north", "onshore", 6.0), ("north", "CCGT", 6.0), ("south", "CCGT", 9.0), ("south", "battery", 1.0)], 0.0, 1.0),
    (18.0, 0.0, [("north", "onshore", 14.0), ("south", "CCGT", 5.0)], 1.0, 0.0),
    (21.0, 72.75, [("north", "CCGT", 10.0), ("south", "CCGT", 9.5), ("south", "interconnector", 1.5)], 0.0, 0.0),
)


def build_toy_v8(folder: Path) -> Path:
    """Four two-zone periods through the staged (v8) writer at summary trace."""

    from gridform_core.market_ledger import (
        DispatchSummaryRow, StorageSummaryRow, build_market_period_batch, create_staged_market_ledger_v8,
    )

    database = folder / "market.sqlite"
    ledger = create_staged_market_ledger_v8(
        database, "summary", storage_cost_module_id="dynamic-annual-storage-cost",
        semantic_metadata=dict(SEMANTIC_METADATA, psm_module_id="value-staged-bid-at-cost-psm"),
    )
    for period, (demand, price, dispatch, charge, discharge) in enumerate(TOY_V8_PERIODS):
        supply = sum(energy for _, _, energy in dispatch)
        onshore = sum(energy for _, technology, energy in dispatch if technology == "onshore")
        ledger.record_period_batch(build_market_period_batch(
            period=_period_row(
                period, real_demand_mwh=demand, accepted_supply_mwh=supply, storage_charge_mwh=charge,
                storage_discharge_mwh=discharge, vre_available_mwh=onshore, vre_accepted_mwh=onshore,
                import_mwh=sum(energy for _, technology, energy in dispatch if technology == "interconnector"),
                clearing_price_gbp_per_mwh=price, market_payment_gbp=demand * price,
                energy_balance_residual_mwh=supply - demand - charge,
            ),
            dispatch_summary=[DispatchSummaryRow(YEAR, period, V8_SUPPLY_STAGE, zone, technology, energy) for zone, technology, energy in dispatch],
            storage_summary=[StorageSummaryRow(YEAR, period, "south", "battery", charge, discharge, 2.0)],
        ))
    ledger.close()
    return database


def run_value_101_day(folder: Path) -> Path:
    """Golden case C3 (frozen project) as a real Run; returns its market.sqlite."""

    sys.path.insert(0, str(ROOT / "scripts" / "golden"))
    try:
        import run_case  # scripts/golden/run_case.py: frozen project + derived acknowledgements
    finally:
        sys.path.remove(str(ROOT / "scripts" / "golden"))
    from gridform_core.application import run_project_application

    case = dict(run_case.load_cases()[REAL_CASE], id=REAL_CASE)
    project = run_case.build_project(case)
    output = folder / "run" / "model-output"
    log = folder / "run.log"
    try:
        with log.open("w", encoding="utf-8") as handle, contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            run_project_application(
                project, run_id=RUN_ID, pack_root=(ROOT / case["pack"]).resolve(),
                output_dir=output, mode=str(case["mode"]),
            )
    except BaseException:
        sys.stderr.write(log.read_text(encoding="utf-8", errors="replace")[-4000:] if log.exists() else "")
        raise
    # The server reads <run>/model-output/market/market.sqlite.
    return output / "market" / "market.sqlite"


# --------------------------------------------------------------------------
# Requests (the same calls backend/server.py makes for the UI's queries)
# --------------------------------------------------------------------------

def _first_period(database: Path, stage: str) -> int | None:
    from gridform_core.market_ledger import _read_only_connection

    with _read_only_connection(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "clearing_inputs" not in tables:
            return None
        row = connection.execute("SELECT MIN(period) FROM clearing_inputs WHERE year=? AND stage=?", (YEAR, stage)).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def _requests(database: Path) -> list[tuple[str, str, dict[str, Any], Callable[[], dict[str, Any]]]]:
    """(name, endpoint, query, call) for every market request the UI makes."""

    from gridform_core.market_ledger import query_market_table
    from gridform_core.market_replay import (
        market_replay_capabilities, query_auction_view, query_dispatch_timeline,
        query_vre_curtailment_summary, query_vre_curtailment_timeline,
    )

    def capabilities() -> dict[str, Any]:
        payload = market_replay_capabilities(database)
        # backend/server.py adds these two keys for a run with market.sqlite.
        payload["legacy_staged_market_jsonl"] = False
        payload["legacy_jsonl_resource"] = None
        return payload

    def table(name: str, **query: Any) -> Callable[[], dict[str, Any]]:
        def call() -> dict[str, Any]:
            page = query_market_table(database, name, **query)
            metadata_path = database.parent / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
            page["trace_level"] = metadata.get("trace_level", "off")
            return page
        return call

    # MarketReplayView: 24-hour window from period 0 (period_to = 47), limit 96.
    window = {"year": YEAR, "period_from": 0, "period_to": 47, "limit": 96, "offset": 0}
    requests: list[tuple[str, str, dict[str, Any], Callable[[], dict[str, Any]]]] = [
        ("capabilities", "capabilities", {}, capabilities),
        ("dispatch-daily", "dispatch", {**window, "resolution": "daily"},
         lambda: query_dispatch_timeline(database, resolution="daily", **window)),
        ("dispatch-half-hour", "dispatch", {**window, "resolution": "half_hour"},
         lambda: query_dispatch_timeline(database, resolution="half_hour", **window)),
        ("vre-summary", "vre-summary", {}, lambda: query_vre_curtailment_summary(database)),
        ("vre-timeline-daily", "vre-timeline", {"year": YEAR, "resolution": "daily", "limit": 500},
         lambda: query_vre_curtailment_timeline(database, year=YEAR, resolution="daily", limit=500)),
        ("periods", "periods", {"limit": 50, "offset": 0}, table("period_summary", limit=50, offset=0)),
    ]
    for stage in ("ahead", "balancing", "curtailment"):
        period = _first_period(database, stage)
        if period is not None:
            requests.append((f"auction-{stage}", "auction", {"year": YEAR, "period": period, "stage": stage},
                             lambda period=period, stage=stage: query_auction_view(database, year=YEAR, period=period, stage=stage)))
    requests.append(("storage", "storage", {"year": YEAR, "period": 1, "limit": 100},
                     table("storage_state", year=YEAR, period=1, limit=100)))
    return requests


# --------------------------------------------------------------------------
# Normalisation, documents, comparison
# --------------------------------------------------------------------------

def normalise(value: Any) -> Any:
    """JSON round trip plus the volatile-hash placeholder; nothing else changes."""

    def walk(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {
                str(key): (VOLATILE_PLACEHOLDER if key in VOLATILE_KEYS and isinstance(child, str) else walk(child))
                for key, child in item.items()
            }
        if isinstance(item, (list, tuple)):
            return [walk(child) for child in item]
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"non-finite number in a UI contract payload: {item!r}")
        return item

    return json.loads(json.dumps(walk(value), allow_nan=False))


def fixture_name(source: str, request: str) -> str:
    return f"{source}.{request}.json"


def build_documents(databases: Mapping[str, Path]) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for source in SOURCES:
        for name, endpoint, query, call in _requests(databases[source]):
            documents[fixture_name(source, name)] = {
                "schema_version": SCHEMA_VERSION,
                "generated_by": GENERATOR,
                "source": source,
                "request": {"path": f"/api/runs/{{run_id}}/market/{endpoint}", "query": query},
                "payload": normalise(call()),
            }
    return documents


def generate(scratch: Path | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Build the three ledgers in a temporary folder and return (documents, invariants)."""

    started = time.monotonic()
    folder = Path(tempfile.mkdtemp(prefix="value-ui-contract-", dir=scratch))
    previous_home = os.environ.get("VALUE_DATA_HOME")
    os.environ["VALUE_DATA_HOME"] = str(folder / "data-home")
    try:
        databases = {}
        for source, builder in (("toy-v7", build_toy_v7), ("toy-v8", build_toy_v8), ("value-101-day", run_value_101_day)):
            target = folder / source
            target.mkdir()
            databases[source] = builder(target)
        documents = build_documents(databases)
    finally:
        if previous_home is None:
            os.environ.pop("VALUE_DATA_HOME", None)
        else:
            os.environ["VALUE_DATA_HOME"] = previous_home
        shutil.rmtree(folder, ignore_errors=True)
    report = invariant_report(documents)
    report["seconds"] = round(time.monotonic() - started, 2)
    return documents, report


def render(document: Mapping[str, Any]) -> str:
    """Line-oriented JSON: objects are expanded down to the row level, and each
    row (a list element or a leaf object) stays on one compact line, so a
    regeneration diffs row by row while the files stay within the budget."""

    def compact(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    def block(value: Any, indent: str) -> str:
        inner = indent + " "
        if isinstance(value, Mapping) and any(isinstance(child, (Mapping, list)) and child for child in value.values()):
            lines = [f"{inner}{compact(key)}: {block(child, inner)}" for key, child in value.items()]
            return "{\n" + ",\n".join(lines) + f"\n{indent}}}"
        if isinstance(value, list) and value and all(isinstance(child, (Mapping, list)) for child in value):
            return "[\n" + ",\n".join(f"{inner}{compact(child)}" for child in value) + f"\n{indent}]"
        return compact(value)

    return block(document, "") + "\n"


def index_document(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_by": GENERATOR,
        "real_case": REAL_CASE,
        "relative_tolerance": RELATIVE_TOLERANCE,
        "volatile_placeholder": VOLATILE_PLACEHOLDER,
        "fixtures": [
            {"file": name, "source": document["source"], "path": document["request"]["path"], "query": document["request"]["query"]}
            for name, document in sorted(documents.items())
        ],
    }


def differences(expected: Any, actual: Any, where: str = "$", limit: int = 20) -> list[str]:
    """Structural comparison; numbers within RELATIVE_TOLERANCE / ABSOLUTE_TOLERANCE."""

    found: list[str] = []

    def visit(left: Any, right: Any, path: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(left, bool) or isinstance(right, bool):
            if left is not right:
                found.append(f"{path}: {left!r} != {right!r}")
            return
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if type(left) is not type(right) and not (float(left) == float(right) == 0.0):
                found.append(f"{path}: type {type(left).__name__} != {type(right).__name__} ({left!r} vs {right!r})")
            elif not math.isclose(float(left), float(right), rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE):
                found.append(f"{path}: {left!r} != {right!r}")
            return
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            if list(left) != list(right):
                missing = [key for key in left if key not in right]
                extra = [key for key in right if key not in left]
                found.append(f"{path}: keys differ (missing {missing}, new {extra})" if missing or extra else f"{path}: key order differs")
            for key in left:
                if key in right:
                    visit(left[key], right[key], f"{path}.{key}")
            return
        if isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                found.append(f"{path}: length {len(left)} != {len(right)}")
            for position, (one, two) in enumerate(zip(left, right)):
                visit(one, two, f"{path}[{position}]")
            return
        if left != right:
            found.append(f"{path}: {left!r} != {right!r}")

    visit(expected, actual, where)
    return found


# --------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------

def _supply_flows(payload: Mapping[str, Any], item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    flows = list(item.get("flows") or [])
    if payload.get("dispatch_source") == "dispatch_summary":
        return [flow for flow in flows if flow.get("flow_type") == "accepted_dispatch"
                and f";stage:{V8_SUPPLY_STAGE}" in str(flow.get("evidence_scope", ""))]
    return [flow for flow in flows if flow.get("flow_type") in V7_SUPPLY_FLOW_TYPES]


def supply_flow_violations(payload: Mapping[str, Any]) -> list[str]:
    """Every bucket: sum of supply flows == accepted_supply_mwh."""

    problems = []
    for item in payload.get("items") or []:
        supply = sum(float(flow["energy_mwh"]) for flow in _supply_flows(payload, item))
        expected = float(item["accepted_supply_mwh"])
        if not math.isclose(supply, expected, rel_tol=1e-9, abs_tol=INVARIANT_TOLERANCE_MWH):
            problems.append(f"bucket {item['period_start']}-{item['period_end']}: supply flows {supply!r} != accepted_supply_mwh {expected!r}")
    return problems


# The terms of the v8 (staged PSM) period balance as the read model sends them.
# staged_psm.py: accepted_supply = sum of positive final dispatch, storage
# charge and export are the negative final dispatch, and the balancing residual
# is sum(final dispatch) + blackout - real demand.  excess_mwh is
# max(vre_available - vre_accepted, 0): VRE that was never dispatched, so it is
# outside this balance and is deliberately not a term here.
V8_BALANCE_TERMS = (
    "accepted_supply_mwh", "blackout_mwh", "real_demand_mwh", "storage_charge_mwh",
    "export_mwh", "flexible_demand_mwh", "energy_balance_residual_mwh",
)


def v8_recomputed_balance_mwh(item: Mapping[str, Any]) -> float:
    """supply + blackout - demand - storage charge - export - flexible demand."""

    return math.fsum((
        float(item["accepted_supply_mwh"]), float(item["blackout_mwh"]), -float(item["real_demand_mwh"]),
        -float(item["storage_charge_mwh"]), -float(item["export_mwh"]), -float(item["flexible_demand_mwh"]),
    ))


def v8_period_conservation_violations(payload: Mapping[str, Any]) -> list[str]:
    """A half-hour v8 timeline: every period conserves energy.

    The balance is recomputed from the payload's own terms rather than read
    back from ``energy_balance_residual_mwh`` (the writer already rejects a
    residual above tolerance, so reading it back proves nothing).  A missing
    term is a violation, never zero (F1-07), and a recorded residual that
    disagrees with the recomputed balance is reported as well.
    """

    problems = supply_flow_violations(payload)
    for item in payload.get("items") or []:
        where = f"period {item.get('period_start')}"
        missing = [key for key in V8_BALANCE_TERMS if item.get(key) is None]
        if missing:
            problems.append(f"{where}: balance terms missing from the payload: {missing}")
            continue
        balance = v8_recomputed_balance_mwh(item)
        recorded = float(item["energy_balance_residual_mwh"])
        if abs(balance) > INVARIANT_TOLERANCE_MWH:
            problems.append(f"{where}: recomputed balance {balance!r} MWh != 0")
        if abs(balance - recorded) > INVARIANT_TOLERANCE_MWH:
            problems.append(f"{where}: recorded energy_balance_residual_mwh {recorded!r} != recomputed {balance!r}")
    return problems


def invariant_report(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    checks: dict[str, list[str]] = {}
    for name, document in sorted(documents.items()):
        if document["request"]["path"].endswith("/market/dispatch"):
            checks[f"supply_flows:{name}"] = supply_flow_violations(document["payload"])
            if document["payload"].get("dispatch_source") == "dispatch_summary" and document["request"]["query"].get("resolution") == "half_hour":
                checks[f"v8_period_conservation:{name}"] = v8_period_conservation_violations(document["payload"])
    return {"checks": checks, "passed": not any(checks.values())}


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------

def expected_files(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    files = {name: render(document) for name, document in documents.items()}
    files[INDEX_NAME] = render(index_document(documents))
    return files


def write(documents: Mapping[str, Mapping[str, Any]], directory: Path = FIXTURE_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    files = expected_files(documents)
    for stale in directory.glob("*.json"):
        if stale.name not in files:
            stale.unlink()
    written = []
    for name, text in sorted(files.items()):
        path = directory / name
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def check(documents: Mapping[str, Mapping[str, Any]], directory: Path = FIXTURE_DIR) -> list[str]:
    """Differences between freshly generated fixtures and the committed files."""

    problems: list[str] = []
    files = expected_files(documents)
    present = {path.name for path in directory.glob("*.json")} if directory.is_dir() else set()
    for name in sorted(present - set(files)):
        problems.append(f"{name}: committed but no longer generated")
    for name in sorted(set(files) - present):
        problems.append(f"{name}: generated but not committed (run --write)")
    for name in sorted(set(files) & present):
        committed = json.loads((directory / name).read_text(encoding="utf-8"))
        problems.extend(f"{name} {line}" for line in differences(committed, json.loads(files[name])))
    return problems


def total_bytes(directory: Path = FIXTURE_DIR) -> int:
    return sum(path.stat().st_size for path in directory.glob("*.json"))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="rewrite tests/fixtures/ui-contract")
    mode.add_argument("--check", action="store_true", help="compare with the committed fixtures (default)")
    parser.add_argument("--directory", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--scratch", type=Path, help="parent folder for the temporary ledgers and Run")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    documents, invariants = generate(arguments.scratch)
    summary: dict[str, Any] = {"fixtures": len(documents), "seconds": invariants.pop("seconds"), "invariants": invariants}
    status = 0
    if arguments.write:
        write(documents, arguments.directory)
        summary["written"] = str(arguments.directory)
    else:
        problems = check(documents, arguments.directory)
        summary["differences"] = problems
        status = 1 if problems else 0
    summary["bytes"] = total_bytes(arguments.directory) if arguments.directory.is_dir() else 0
    budgets = []
    if summary["bytes"] > SIZE_BUDGET_BYTES:
        budgets.append(f"fixtures use {summary['bytes']} bytes > {SIZE_BUDGET_BYTES}")
    if summary["seconds"] > TIME_BUDGET_SECONDS:
        budgets.append(f"generation took {summary['seconds']} s > {TIME_BUDGET_SECONDS}")
    summary["budget_violations"] = budgets
    if budgets or not invariants["passed"]:
        status = 1
    sys.stdout.write(json.dumps(summary, indent=1) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
