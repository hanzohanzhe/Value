"""Versioned storage technology catalogue shared by dispatch, pricing and CEM."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_CATALOGUE = (
    Path(__file__).resolve().parent
    / "data"
    / "storage"
    / "storage_technology_catalogue.json"
)


@dataclass(frozen=True)
class StorageTechnology:
    technology_id: str
    duration_hours: float
    charge_efficiency: float
    discharge_efficiency: float
    economic_lifetime_years: float
    maximum_cycles: float
    has_battery_cycle_depreciation: bool
    capex_value: float
    capex_unit: str
    fixed_opex_value: float
    fixed_opex_unit: str
    currency_base_year: int
    source: Mapping[str, object]

    @property
    def input_output_energy_ratio(self) -> float:
        return self.charge_efficiency * self.discharge_efficiency

    def energy_capacity_mwh(self, power_capacity_mw: float) -> float:
        return float(power_capacity_mw) * self.duration_hours


class StorageTechnologyCatalogue:
    def __init__(self, path: Path = DEFAULT_CATALOGUE) -> None:
        self.path = path.resolve()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "value.storage-technology-catalogue/v1":
            raise ValueError("Unsupported storage technology catalogue schema")
        self.catalogue_id = str(payload["catalogue_id"])
        self.version = str(payload["version"])
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        technologies: dict[str, StorageTechnology] = {}
        for raw in payload.get("technologies", []):
            technology = StorageTechnology(**raw)
            self._validate(technology)
            if technology.technology_id in technologies:
                raise ValueError(f"Duplicate storage technology {technology.technology_id}")
            technologies[technology.technology_id] = technology
        self.technologies = technologies

    @staticmethod
    def _validate(value: StorageTechnology) -> None:
        if value.duration_hours <= 0 or value.economic_lifetime_years <= 0:
            raise ValueError(f"Storage {value.technology_id} has non-positive duration/life")
        if not (0 < value.charge_efficiency <= 1 and 0 < value.discharge_efficiency <= 1):
            raise ValueError(f"Storage {value.technology_id} has invalid efficiency")
        if value.capex_unit not in {"GBP/MW", "GBP/MWh", "GBP/project"}:
            raise ValueError(f"Storage {value.technology_id} has ambiguous CAPEX basis")
        if value.fixed_opex_unit not in {"GBP/kW/year", "GBP/MW/year", "GBP/year"}:
            raise ValueError(f"Storage {value.technology_id} has ambiguous FOM basis")
        if value.has_battery_cycle_depreciation and value.maximum_cycles <= 0:
            raise ValueError(f"Battery {value.technology_id} requires a positive cycle life")

    def get(self, technology_id: str) -> StorageTechnology:
        try:
            return self.technologies[technology_id]
        except KeyError as exc:
            raise ValueError(f"Unknown storage technology: {technology_id}") from exc

    def validate_capacity(
        self,
        technology_id: str,
        *,
        power_capacity_mw: float,
        energy_capacity_mwh: float,
        tolerance: float = 1e-9,
    ) -> None:
        technology = self.get(technology_id)
        expected = technology.energy_capacity_mwh(power_capacity_mw)
        if not math.isclose(expected, float(energy_capacity_mwh), rel_tol=tolerance, abs_tol=tolerance):
            raise ValueError(
                f"{technology_id} requires {expected} MWh for {power_capacity_mw} MW "
                f"at {technology.duration_hours} h; received {energy_capacity_mwh} MWh"
            )


def compatibility_catalogue() -> StorageTechnologyCatalogue:
    return StorageTechnologyCatalogue()
