"""Validated anti-corruption boundary for the retained 41-field Scheme C tuple."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ...v2.contracts import MarketYearResult


class SchemeCResultCompatibilityError(RuntimeError):
    """The retained result no longer matches the supported Scheme C layout."""


_LEGACY_FIELD_ORDER = (
    "prices_gbp_per_mwh",
    "storage_fees_gbp",
    "storage_charge_by_period",
    "generation_cost_gbp_by_period",
    "storage_pool_by_period",
    "total_storage_pool_by_period",
    "storage_pool_composition_by_period",
    "storage_usage_composition_by_period",
    "average_generation_fees_gbp",
    "average_curtailment_fees_gbp",
    "average_balancing_fees_gbp",
    "average_storage_fees_gbp",
    "ahead_renewables_mwh",
    "ahead_other_mwh",
    "ahead_traditional_mwh",
    "ahead_nuclear_mwh",
    "balancing_renewables_mwh",
    "balancing_other_mwh",
    "balancing_traditional_mwh",
    "balancing_nuclear_mwh",
    "dispatch_by_period",
    "curtailed_electricity_mwh_by_period",
    "excess_electricity_mwh_by_period",
    "total_cost_gbp_by_period",
    "real_demand_mwh_by_period",
    "carbon_emissions_by_period",
    "sold_fees_gbp_by_period",
    "purchase_fees_gbp_by_period",
    "traditional_generation_summary",
    "green_hydrogen_by_period",
    "total_renewable_capacity_by_period",
    "renewable_capacity_by_period",
    "energy_cell_by_period",
    "market_income_gbp_by_agent",
    "excess_energy_by_agent",
    "final_excess_energy_by_agent",
    "curtailed_energy_by_agent",
    "renewable_hydrogen_by_agent",
    "flexible_demand_mwh_by_period",
    "interconnector_exports_mwh_by_period",
    "blackout_mwh_by_period",
)


@dataclass(frozen=True)
class SchemeCSimulationResult:
    year: int
    periods: int
    period_hours: float
    prices_gbp_per_mwh: Sequence[object]
    storage_fees_gbp: object
    storage_charge_by_period: Sequence[object]
    generation_cost_gbp_by_period: Sequence[object]
    storage_pool_by_period: object
    total_storage_pool_by_period: object
    storage_pool_composition_by_period: object
    storage_usage_composition_by_period: object
    average_generation_fees_gbp: object
    average_curtailment_fees_gbp: object
    average_balancing_fees_gbp: object
    average_storage_fees_gbp: object
    ahead_renewables_mwh: object
    ahead_other_mwh: object
    ahead_traditional_mwh: object
    ahead_nuclear_mwh: object
    balancing_renewables_mwh: object
    balancing_other_mwh: object
    balancing_traditional_mwh: object
    balancing_nuclear_mwh: object
    dispatch_by_period: Sequence[Sequence[object]]
    curtailed_electricity_mwh_by_period: object
    excess_electricity_mwh_by_period: Sequence[object]
    total_cost_gbp_by_period: Sequence[object]
    real_demand_mwh_by_period: Sequence[object]
    carbon_emissions_by_period: object
    sold_fees_gbp_by_period: object
    purchase_fees_gbp_by_period: object
    traditional_generation_summary: object
    green_hydrogen_by_period: object
    total_renewable_capacity_by_period: object
    renewable_capacity_by_period: object
    energy_cell_by_period: object
    market_income_gbp_by_agent: Mapping[object, object]
    excess_energy_by_agent: object
    final_excess_energy_by_agent: object
    curtailed_energy_by_agent: object
    renewable_hydrogen_by_agent: object
    flexible_demand_mwh_by_period: object
    interconnector_exports_mwh_by_period: object
    blackout_mwh_by_period: Sequence[object]

    def generation_mwh_by_asset(self) -> dict[str, float]:
        """Preserve the existing adapter conversion: dispatch energy times period hours."""
        generation: defaultdict[str, float] = defaultdict(float)
        for period in self.dispatch_by_period:
            for asset, raw_energy in period:  # type: ignore[misc]
                name = str(getattr(asset, "name", asset.__class__.__name__))
                generation[name] += float(raw_energy) * self.period_hours
        return dict(generation)

    def to_market_year_result(
        self,
        *,
        result_id: str,
        module_id: str,
        module_version: str,
    ) -> MarketYearResult:
        generation = self.generation_mwh_by_asset()
        operational = sum(float(value) for value in self.total_cost_gbp_by_period)
        return MarketYearResult(
            result_id=result_id,
            year=self.year,
            module_id=module_id,
            module_version=module_version,
            generation_mwh_by_asset=generation,
            market_income_gbp_by_agent={
                str(key): float(value)
                for key, value in self.market_income_gbp_by_agent.items()
            },
            total_system_cost_gbp=operational,
            total_operational_cost_gbp=operational,
            total_levelized_capital_cost_gbp=0.0,
            total_demand_mwh=sum(float(value) for value in self.real_demand_mwh_by_period),
            total_generation_mwh=sum(generation.values()),
            total_blackout_mwh=sum(float(value) for value in self.blackout_mwh_by_period),
            total_excess_mwh=sum(float(value) for value in self.excess_electricity_mwh_by_period),
            extensions={"legacy_kernel_has_no_annualized_capital_cost": True},
        )


class SchemeCLegacyResultAdapter:
    expected_length = len(_LEGACY_FIELD_ORDER)

    @classmethod
    def validate_and_convert(
        cls,
        raw: object,
        *,
        year: int,
        periods: int,
        period_hours: float,
    ) -> SchemeCSimulationResult:
        if not isinstance(raw, tuple):
            raise SchemeCResultCompatibilityError(
                f"Scheme C result must be a tuple, received {type(raw).__name__}"
            )
        if len(raw) != cls.expected_length:
            raise SchemeCResultCompatibilityError(
                f"Scheme C result has {len(raw)} fields; expected {cls.expected_length}"
            )
        if not isinstance(year, int) or year < 1900:
            raise SchemeCResultCompatibilityError(f"Invalid Scheme C result year: {year}")
        if not isinstance(periods, int) or periods <= 0:
            raise SchemeCResultCompatibilityError(f"Invalid period count: {periods}")
        if period_hours <= 0:
            raise SchemeCResultCompatibilityError(f"Invalid period duration: {period_hours}")

        values = dict(zip(_LEGACY_FIELD_ORDER, raw, strict=True))
        cls._numeric_sequence(values, "prices_gbp_per_mwh", periods)
        cls._numeric_sequence(values, "total_cost_gbp_by_period", periods)
        cls._numeric_sequence(values, "real_demand_mwh_by_period", periods)
        cls._numeric_sequence(values, "excess_electricity_mwh_by_period", periods)
        cls._numeric_sequence(values, "blackout_mwh_by_period", periods)
        cls._sequence(values, "storage_charge_by_period")
        dispatch = cls._sequence(values, "dispatch_by_period", expected_length=periods)
        for period_index, row in enumerate(dispatch):
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
                raise SchemeCResultCompatibilityError(
                    f"dispatch_by_period[{period_index}] is not a sequence"
                )
            for bid_index, bid in enumerate(row):
                if not isinstance(bid, (tuple, list)) or len(bid) != 2:
                    raise SchemeCResultCompatibilityError(
                        f"dispatch_by_period[{period_index}][{bid_index}] is not an (asset, energy) pair"
                    )
                try:
                    float(bid[1])
                except (TypeError, ValueError) as exc:
                    raise SchemeCResultCompatibilityError(
                        f"dispatch energy at period {period_index}, row {bid_index} is not numeric"
                    ) from exc
        if not isinstance(values["market_income_gbp_by_agent"], Mapping):
            raise SchemeCResultCompatibilityError("market_income_gbp_by_agent is not a mapping")
        return SchemeCSimulationResult(
            year=year,
            periods=periods,
            period_hours=float(period_hours),
            **values,
        )

    @staticmethod
    def _sequence(
        values: Mapping[str, object], key: str, expected_length: int | None = None
    ) -> Sequence[object]:
        value = values[key]
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise SchemeCResultCompatibilityError(f"{key} is not a sequence")
        if expected_length is not None and len(value) != expected_length:
            raise SchemeCResultCompatibilityError(
                f"{key} has {len(value)} periods; expected {expected_length}"
            )
        return value

    @classmethod
    def _numeric_sequence(
        cls, values: Mapping[str, object], key: str, expected_length: int
    ) -> Sequence[object]:
        value = cls._sequence(values, key, expected_length)
        for index, item in enumerate(value):
            try:
                float(item)
            except (TypeError, ValueError) as exc:
                raise SchemeCResultCompatibilityError(
                    f"{key}[{index}] is not numeric"
                ) from exc
        return value
