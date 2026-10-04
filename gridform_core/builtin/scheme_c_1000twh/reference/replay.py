"""Private historical-output reader; excluded from production module discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ....v2.contracts import AssetStateV2, PlanningProject, YearState


CAPACITY_COLUMNS = {
    "solar": "Solar_Capacity_MW",
    "onshore": "Onshore_Capacity_MW",
    "offshore": "Offshore_Capacity_MW",
    "storage": "Total_Storage_Capacity_MW",
    "CCGT": "CCGT_Capacity_MW",
    "OCGT": "OCGT_Capacity_MW",
}


@dataclass(frozen=True)
class SchemeCReplayData:
    """Typed view of already-written historical reference artifacts."""

    costs_by_year: Mapping[int, Mapping[str, object]]
    capacities_by_year: Mapping[int, Mapping[str, object]]
    investments_by_year: Mapping[int, Sequence[Mapping[str, object]]]
    headroom_by_year_module: Mapping[tuple[int, str], Mapping[str, float]]
    agent_economics_by_year: Mapping[int, Mapping[str, object]]

    def state(self, year: int, projects: Sequence[PlanningProject] = ()) -> YearState:
        row = self.capacities_by_year.get(year)
        if row is None:
            previous = max(
                (value for value in self.capacities_by_year if value < year),
                default=None,
            )
            row = self.capacities_by_year.get(previous, {}) if previous is not None else {}
        assets = tuple(
            AssetStateV2(
                f"aggregate:{technology}",
                technology,
                float(row.get(column, 0.0) or 0.0),
            )
            for technology, column in CAPACITY_COLUMNS.items()
        )
        return YearState(year, assets, tuple(projects))


class HistoricalReplayReader:
    """Non-module marker used by historical run readers and migration tests."""

    id = "scheme-c-historical-replay-reader"
    version = "1.0.0"
    execution_kind = "historical_reader"
    selectable_as_project_psm = False
