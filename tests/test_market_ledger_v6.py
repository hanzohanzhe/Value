from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import gridform_core.market_ledger as market_ledger
from gridform_core.errors import InvariantError
from gridform_core.vre_curtailment_attribution import (
    VRECounterfactualRow,
    VRECounterfactualSnapshot,
    attribute_vre_curtailment,
)


def _semantic_metadata() -> dict[str, object]:
    return {
        "run_id": "run",
        "run_parent_id": None,
        "data_pack_id": "pack",
        "network_pack_id": "network",
        "module_ids": ["psm", "balancing"],
    }


def build_legacy_fixture(database: Path, version: str) -> Path:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE period_summary(year INTEGER, period INTEGER, stage TEXT);
            INSERT INTO period_summary VALUES(2025, 0, 'final_dispatch');
            """
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
            (version,),
        )
        connection.commit()
    return database


def build_v5_fixture(database: Path) -> Path:
    build_legacy_fixture(database, "value.market-ledger/v5")
    schema = (
        Path(__file__).resolve().parents[1]
        / "gridform_core"
        / "data"
        / "contracts"
        / "market-ledger-v5.schema.sql"
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(schema.read_text(encoding="utf-8"))
        connection.commit()
    return database


def _accounting() -> SimpleNamespace:
    return SimpleNamespace(
        year=2025,
        period=6,
        period_id="2025:6",
        system_resource_cost_gbp=145.0,
        transmission_constraint_resource_cost_gbp=25.0,
        national_settlement_gbp=500.0,
        redispatch_settlement_gbp=30.0,
        policy_transfer_gbp=7.0,
        perfect_forecast_resource_cost_gbp=100.0,
        realised_copperplate_resource_cost_gbp=120.0,
        zonal_resource_cost_gbp=145.0,
        forecast_error_cost_gbp=20.0,
        total_deviation_cost_gbp=45.0,
        blackout_mwh=0.0,
        counterfactual_realised_input_sha256="a" * 64,
        accounting_status="reconciled",
    )


def _attribution():
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=6,
        period_id="2025:6",
        realised_input_sha256="a" * 64,
        rows=(
            VRECounterfactualRow(
                asset_id="wind-1",
                owner_id="owner-1",
                canonical_technology="Onshore wind",
                zone_id="north",
                bid_tranche_id="vre-onshore-0",
                realised_available_vre_mwh=10.0,
                perfect_forecast_copperplate_dispatch_mwh=7.0,
                realised_copperplate_dispatch_mwh=7.0,
                zonal_final_dispatch_mwh=10.0,
            ),
        ),
    )
    return attribute_vre_curtailment(snapshot)


def test_new_ledger_is_v7_and_has_separate_authoritative_tables(
    tmp_path: Path,
) -> None:
    ledger = market_ledger.SQLiteMarketLedger(
        tmp_path / "market.sqlite",
        trace_level="summary",
        semantic_metadata=_semantic_metadata(),
    )
    ledger.close()

    with sqlite3.connect(tmp_path / "market.sqlite") as connection:
        version = connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert version == "value.market-ledger/v7"
    assert {
        "zonal_period_accounting",
        "vre_curtailment_period",
        "vre_curtailment_detail",
        "network_solver_diagnostics",
    }.issubset(tables)


@pytest.mark.parametrize(
    "version", ("value.market-ledger/v4", "value.market-ledger/v5")
)
def test_legacy_reader_does_not_modify_historical_database(
    tmp_path: Path, version: str
) -> None:
    database = build_legacy_fixture(tmp_path / "market.sqlite", version)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    capabilities = market_ledger.market_ledger_capabilities(database)

    after = hashlib.sha256(database.read_bytes()).hexdigest()
    assert before == after
    assert capabilities["ledger_schema_version"] == version
    assert capabilities["attribution_status"] == "legacy_partial"
    assert capabilities["redispatch_avoided_curtailment_available"] is False


def test_v5_database_cannot_resume_with_v7_writer(tmp_path: Path) -> None:
    database = build_v5_fixture(tmp_path / "market.sqlite")
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    with pytest.raises(
        InvariantError,
        match=(
            "GF_LEDGER_SCHEMA_RESUME_MISMATCH.*new run ID.*portable checkpoint"
        ),
    ):
        market_ledger.SQLiteMarketLedger(
            database, trace_level="summary", semantic_metadata={}
        )

    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_v7_batch_writes_copy_authoritative_attribution_without_v5_fillers(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.sqlite"
    ledger = market_ledger.SQLiteMarketLedger(
        database,
        trace_level="summary",
        batch_size=1,
        semantic_metadata=_semantic_metadata(),
    )
    attribution = _attribution()

    ledger.record_zonal_accounting(
        (market_ledger.ZonalAccountingLedgerRow.from_accounting(_accounting()),)
    )
    ledger.record_vre_curtailment_periods(
        (market_ledger.VRECurtailmentPeriodRow.from_attribution(attribution),)
    )
    ledger.record_vre_curtailment_details(
        market_ledger.VRECurtailmentDetailRow.from_attribution(attribution)
    )
    metadata = ledger.close()

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        accounting = dict(
            connection.execute("SELECT * FROM zonal_period_accounting").fetchone()
        )
        period = dict(
            connection.execute("SELECT * FROM vre_curtailment_period").fetchone()
        )
        detail = dict(
            connection.execute("SELECT * FROM vre_curtailment_detail").fetchone()
        )
        obsolete_rows = connection.execute(
            "SELECT COUNT(*) FROM zonal_period_summary"
        ).fetchone()[0]

    assert accounting["network_constraint_cost_gbp"] == 25.0
    assert period["economic_curtailment_mwh"] == 3.0
    assert period["redispatch_added_curtailment_mwh"] == 0.0
    assert period["redispatch_avoided_curtailment_mwh"] == 3.0
    assert period["redispatch_net_impact_mwh"] == -3.0
    assert period["total_curtailment_mwh"] == 0.0
    assert detail["zone_id"] == "north"
    assert detail["technology"] == "Onshore wind"
    assert detail["redispatch_avoided_curtailment_mwh"] == 3.0
    assert detail["evidence_level"] == "deterministic_reference_allocation"
    assert obsolete_rows == 0
    assert metadata["rows"]["zonal_period_accounting"] == 1
    assert metadata["rows"]["vre_curtailment_period"] == 1
    assert metadata["rows"]["vre_curtailment_detail"] == 1


def test_v7_contract_has_query_indexes_and_validates(tmp_path: Path) -> None:
    database = tmp_path / "market.sqlite"
    market_ledger.SQLiteMarketLedger(
        database,
        trace_level="summary",
        semantic_metadata=_semantic_metadata(),
    ).close()

    with sqlite3.connect(database) as connection:
        detail_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(vre_curtailment_detail)")
        }

    assert {
        "vre_curtailment_detail_period",
        "vre_curtailment_detail_zone_technology_year",
        "vre_curtailment_detail_asset_year_period",
    }.issubset(detail_indexes)
    assert market_ledger.validate_market_ledger_file(database) == {
        "valid": True,
        "schema_version": "value.market-ledger/v7",
        "integrity": "ok",
        "errors": [],
    }


@pytest.mark.parametrize(
    "version", ("value.market-ledger/v4", "value.market-ledger/v5")
)
def test_completed_legacy_ledgers_remain_valid_read_only_contracts(
    tmp_path: Path, version: str
) -> None:
    database = (
        build_v5_fixture(tmp_path / "market.sqlite")
        if version == "value.market-ledger/v5"
        else build_legacy_fixture(tmp_path / "market.sqlite", version)
    )
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    result = market_ledger.validate_market_ledger_file(database)

    assert result["valid"] is True
    assert result["schema_version"] == version
    assert result["integrity"] == "ok"
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_v5_validation_rejects_an_incomplete_declared_contract(
    tmp_path: Path,
) -> None:
    database = build_legacy_fixture(
        tmp_path / "market.sqlite", "value.market-ledger/v5"
    )

    result = market_ledger.validate_market_ledger_file(database)

    assert result["valid"] is False
    assert "missing_table:zonal_period_summary" in result["errors"]
