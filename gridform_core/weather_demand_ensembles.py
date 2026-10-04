"""Declared weather/demand experiment designs and rate accounting."""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ProfileRealisation:
    profile_id: str
    source_revision: str
    uncertainty_dimension: str
    historical_or_model_year: int
    timezone: str
    interval_minutes: int
    transformation: str = "none"
    uncertainty_type: str = "scenario"


@dataclass(frozen=True)
class ExperimentDesign:
    design_id: str
    weather: tuple[ProfileRealisation, ...]
    demand: tuple[ProfileRealisation, ...]
    design: str = "full_factorial"
    selected_pairs: tuple[tuple[str, str], ...] = ()
    schema_version: str = "value.weather-demand-design/v1"

    def members(self) -> tuple[dict[str, object], ...]:
        weather = {row.profile_id: row for row in self.weather}
        demand = {row.profile_id: row for row in self.demand}
        if self.design == "full_factorial":
            pairs = tuple(itertools.product(weather, demand))
        elif self.design == "explicit_reduced":
            pairs = self.selected_pairs
            if not pairs:
                raise ValueError("explicit_reduced requires selected_pairs")
        else:
            raise ValueError("design must be full_factorial or explicit_reduced")
        if len(set(pairs)) != len(pairs):
            raise ValueError("Experiment design contains duplicate members")
        members = []
        for weather_id, demand_id in pairs:
            if weather_id not in weather or demand_id not in demand:
                raise ValueError("Reduced design references an undeclared profile")
            identity = json.dumps({"design": self.design_id, "weather": asdict(weather[weather_id]), "demand": asdict(demand[demand_id])}, sort_keys=True, separators=(",", ":"))
            members.append({
                "member_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
                "weather": asdict(weather[weather_id]),
                "demand": asdict(demand[demand_id]),
                "combination_inclusion": "declared",
            })
        return tuple(members)


def normalize_half_hour_year(values: Sequence[float], *, source_periods: int, source_timezone: str = "UTC") -> tuple[float, ...]:
    """Normalize one calendar year to 17,520 periods with energy conservation.

    VALUE uses UTC internally, so DST does not create missing/duplicate physical
    periods.  A leap-year input (17,568 periods) is reduced by removing 29 Feb and
    scaling the remaining interval energies so annual energy is unchanged.  Any
    other count is rejected rather than silently interpolated.
    """

    if source_timezone != "UTC":
        raise ValueError("Local-time profiles must first provide an explicit UTC mapping with DST folds/gaps resolved")
    numbers = [float(item) for item in values]
    if len(numbers) != source_periods:
        raise ValueError("Declared source_periods does not match profile length")
    if source_periods == 17_520:
        return tuple(numbers)
    if source_periods != 17_568:
        raise ValueError("A half-hour year must contain 17,520 or 17,568 periods")
    # Jan + Feb 28 days, then the 48 leap-day periods.
    start = (31 + 28) * 48
    reduced = numbers[:start] + numbers[start + 48:]
    original = sum(numbers)
    retained = sum(reduced)
    if retained == 0:
        if original != 0:
            raise ValueError("Cannot conserve leap-day energy when all retained periods are zero")
        return tuple(reduced)
    scale = original / retained
    return tuple(item * scale for item in reduced)


def experiment_rates(members: Sequence[Mapping[str, object]], *, adequacy_field: str = "adequate") -> dict[str, object]:
    requested = len(members)
    completed = [row for row in members if row.get("status") == "completed"]
    adequate = [row for row in completed if row.get(adequacy_field) is True]
    return {
        "execution_completion_rate": {
            "numerator": len(completed), "denominator": requested,
            "value": len(completed) / requested if requested else None,
        },
        "adequacy_success_rate": {
            "numerator": len(adequate), "denominator": len(completed),
            "value": len(adequate) / len(completed) if completed else None,
            "criterion": adequacy_field,
        },
        "planning_success_rate": "reported_separately_by_planning_ensemble",
        "failed_computations_are_not_inadequate_system_outcomes": True,
    }
