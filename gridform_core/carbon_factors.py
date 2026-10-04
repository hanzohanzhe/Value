"""Read-only access to the audited carbon-factor catalogue."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_DATABASE = Path(__file__).resolve().parent / "data" / "carbon" / "value_carbon_factors.sqlite"


@dataclass(frozen=True)
class CarbonFactor:
    record_id: str
    dataset_id: str
    technology: str
    variant: str
    component: str
    factor_kind: str
    value: float
    unit: str
    basis: str
    lifecycle_scope: str
    geography: str
    scenario: str
    source_id: str
    source_title: str
    source_url: str
    status: str
    quality_note: str


class CarbonFactorDatabase:
    """Query factors without silently mixing datasets, variants, or boundaries."""

    def __init__(self, path: Path | str = DEFAULT_DATABASE) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(
                f"Carbon database not found at {self.path}. "
                "Run `py -3.10 scripts/build_carbon_factor_database.py`."
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.path.resolve()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def list_datasets(self) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM datasets ORDER BY dataset_id").fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def query(
        self,
        *,
        dataset_id: str | None = None,
        technology: str | None = None,
        factor_kind: str | None = None,
        scenario: str | None = None,
        component: str | None = None,
    ) -> list[CarbonFactor]:
        filters: list[str] = []
        values: list[str] = []
        for column, value in (
            ("dataset_id", dataset_id),
            ("technology", technology),
            ("factor_kind", factor_kind),
            ("scenario", scenario),
            ("component", component),
        ):
            if value is not None:
                filters.append(f"{column} = ?")
                values.append(value)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        sql = (
            "SELECT record_id, dataset_id, technology, variant, component, factor_kind, "
            "value, unit, basis, lifecycle_scope, geography, scenario, source_id, "
            "source_title, source_url, status, quality_note "
            f"FROM factor_records{where} ORDER BY dataset_id, technology, variant, record_id"
        )
        connection = self._connect()
        try:
            rows = connection.execute(sql, values).fetchall()
        finally:
            connection.close()
        return [CarbonFactor(**dict(row)) for row in rows]

    def get_unique(
        self,
        *,
        dataset_id: str,
        technology: str,
        factor_kind: str,
        variant: str | None = None,
        scenario: str | None = None,
    ) -> CarbonFactor:
        rows = self.query(
            dataset_id=dataset_id,
            technology=technology,
            factor_kind=factor_kind,
            scenario=scenario,
        )
        if variant is not None:
            rows = [row for row in rows if row.variant == variant]
        if len(rows) != 1:
            raise LookupError(
                "Expected exactly one factor; found "
                f"{len(rows)} for dataset={dataset_id!r}, technology={technology!r}, "
                f"kind={factor_kind!r}, variant={variant!r}, scenario={scenario!r}. "
                "Specify the scientific variant/boundary explicitly."
            )
        return rows[0]
