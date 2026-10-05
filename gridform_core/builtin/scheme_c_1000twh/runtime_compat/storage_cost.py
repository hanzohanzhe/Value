"""Storage cost recovery for the copied, modular Scheme C implementation.

The retained Scheme C files deliberately keep their historical hard-coded bid
parameters.  This module implements the thesis-consistent replacement used by
``modular_simulation_model`` only:

    battery bid(age) = cycle depreciation + age * dynamic holding recovery
    non-battery bid(age) = age * dynamic holding recovery

Only electrochemical batteries receive the fixed cycle-wear term. Pumped hydro
and hydrogen storage recover their annual cost through the holding/utilisation
term. The holding term is chosen at the start of a year from the previous
year's delivered electricity and its energy-weighted dwell time.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Mapping

from ....storage_catalogue import compatibility_catalogue


@dataclass(frozen=True)
class StorageTechnologySpec:
    duration_hours: float
    maximum_cycles: float
    economic_lifetime_years: float
    fixed_opex_gbp_per_kw_year: float
    has_cycle_depreciation: bool


# Durations and cycle lives follow the thesis' current LFP comparison (1C,
# 0.5C and 0.25C) and its long-duration technology table.  The LFP fixed O&M
# proxy is the lithium-ion value in the technology table.
_CATALOGUE = compatibility_catalogue()
STORAGE_TECHNOLOGY_SPECS: dict[str, StorageTechnologySpec] = {
    technology_id: StorageTechnologySpec(
        technology.duration_hours,
        technology.maximum_cycles,
        technology.economic_lifetime_years,
        technology.fixed_opex_value,
        technology.has_battery_cycle_depreciation,
    )
    for technology_id, technology in _CATALOGUE.technologies.items()
}


def technology_spec(battery_type: str | None) -> StorageTechnologySpec:
    key = (battery_type or "").strip().lower()
    if key not in STORAGE_TECHNOLOGY_SPECS:
        raise ValueError(f"Unsupported modular storage technology: {battery_type!r}")
    return STORAGE_TECHNOLOGY_SPECS[key]


def capital_recovery_factor(discount_rate: float, lifetime_years: float) -> float:
    if lifetime_years <= 0:
        raise ValueError("Storage economic lifetime must be positive")
    if discount_rate <= 0:
        return 1.0 / lifetime_years
    growth = (1.0 + discount_rate) ** lifetime_years
    return discount_rate * growth / (growth - 1.0)


@dataclass
class AnnualStorageObservation:
    year: int | None = None
    sold_energy_mwh: float = 0.0
    dwell_weighted_sold_mwh_periods: float = 0.0

    @property
    def average_dwell_periods(self) -> float:
        if self.sold_energy_mwh <= 0:
            return 0.0
        return self.dwell_weighted_sold_mwh_periods / self.sold_energy_mwh


class DynamicAnnualStorageCost:
    """Previous-year average-cost recovery with technology-specific wear."""

    def __init__(
        self,
        *,
        battery_type: str,
        discount_rate: float = 0.05,
        utilisation_floor: float = 0.0,
        period_hours: float = 0.5,
    ) -> None:
        self.battery_type = battery_type
        self.spec = technology_spec(battery_type)
        self.discount_rate = float(discount_rate)
        self.utilisation_floor = float(utilisation_floor)
        self.period_hours = float(period_hours)
        self.previous = AnnualStorageObservation()
        self.current = AnnualStorageObservation()
        self.prepared_year: int | None = None
        self.cycle_depreciation_gbp_per_mwh = 0.0
        self.holding_recovery_gbp_per_mwh_period = 0.0
        self.annual_levelized_project_cost_gbp = 0.0
        self.annualized_capital_cost_gbp = 0.0
        self.annual_fixed_opex_gbp = 0.0
        self.pricing_basis_sold_mwh = 0.0
        self.pricing_basis_average_dwell_periods = 0.0
        self.pricing_basis = "unprepared"
        # VALUE P0-6 S10 (P5-04, decision Q8): the default PSM's market rule set
        # owns the dispatch bid of this exact class.  "thesis_dwell_linear" is
        # cycle wear plus the linear dwell holding term (doctoral, and the
        # default for ROI and conformance callers); "cycle_only" bids the cycle
        # wear alone (zero for pumped hydro and hydrogen) and leaves holding
        # recovery to investment adequacy.
        self.bid_basis = "thesis_dwell_linear"

    def _reference_observation(
        self,
        *,
        energy_capacity_mwh: float,
        discharge_efficiency: float,
    ) -> AnnualStorageObservation:
        # Full economic utilisation exhausts the stated cycle life over the
        # calendar life, capped by the physical charge/discharge time.
        life_cycles_per_year = self.spec.maximum_cycles / self.spec.economic_lifetime_years
        physical_cycles_per_year = 8760.0 / max(2.0 * self.spec.duration_hours, 1e-9)
        cycles_per_year = min(life_cycles_per_year, physical_cycles_per_year)
        sold = max(energy_capacity_mwh, 0.0) * max(discharge_efficiency, 0.0) * cycles_per_year
        dwell_periods = max(self.spec.duration_hours / self.period_hours, 2.0)
        return AnnualStorageObservation(
            sold_energy_mwh=sold,
            dwell_weighted_sold_mwh_periods=sold * dwell_periods,
        )

    def prepare_year(
        self,
        year: int,
        *,
        capital_cost_gbp: float,
        power_capacity_mw: float,
        energy_capacity_mwh: float,
        discharge_efficiency: float,
    ) -> None:
        year = int(year)
        if self.prepared_year == year:
            return
        if self.prepared_year is not None:
            self.previous = self.current

        reference = self._reference_observation(
            energy_capacity_mwh=energy_capacity_mwh,
            discharge_efficiency=discharge_efficiency,
        )
        observed = self.previous
        minimum_sold = reference.sold_energy_mwh * max(self.utilisation_floor, 0.0)
        if observed.sold_energy_mwh > 0:
            basis_sold = max(observed.sold_energy_mwh, minimum_sold)
            average_dwell = max(observed.average_dwell_periods, 2.0)
            self.pricing_basis = "previous_year_sales"
        else:
            basis_sold = reference.sold_energy_mwh
            average_dwell = reference.average_dwell_periods
            self.pricing_basis = "full_utilisation_initialisation"

        capex = max(float(capital_cost_gbp), 0.0)
        usable_cycle_output = (
            max(float(energy_capacity_mwh), 0.0)
            * max(float(discharge_efficiency), 0.0)
        )
        if (
            self.spec.has_cycle_depreciation
            and usable_cycle_output > 0
            and self.spec.maximum_cycles > 0
        ):
            self.cycle_depreciation_gbp_per_mwh = capex / (
                usable_cycle_output * self.spec.maximum_cycles
            )
        else:
            self.cycle_depreciation_gbp_per_mwh = 0.0

        self.annualized_capital_cost_gbp = capex * capital_recovery_factor(
            self.discount_rate, self.spec.economic_lifetime_years
        )
        self.annual_fixed_opex_gbp = (
            max(float(power_capacity_mw), 0.0)
            * 1000.0
            * self.spec.fixed_opex_gbp_per_kw_year
        )
        self.annual_levelized_project_cost_gbp = (
            self.annualized_capital_cost_gbp + self.annual_fixed_opex_gbp
        )

        # Cycle depreciation is already recovered by the fixed bid component.
        # Only the remainder is spread over the observed dwell-weighted sales.
        expected_cycle_recovery = self.cycle_depreciation_gbp_per_mwh * basis_sold
        remaining_annual_recovery = max(
            self.annual_levelized_project_cost_gbp - expected_cycle_recovery,
            0.0,
        )
        weighted_basis = basis_sold * max(average_dwell, 1.0)
        self.holding_recovery_gbp_per_mwh_period = (
            remaining_annual_recovery / weighted_basis if weighted_basis > 0 else 0.0
        )
        if not isfinite(self.holding_recovery_gbp_per_mwh_period):
            self.holding_recovery_gbp_per_mwh_period = 0.0

        self.pricing_basis_sold_mwh = basis_sold
        self.pricing_basis_average_dwell_periods = average_dwell
        self.current = AnnualStorageObservation(year=year)
        self.prepared_year = year

    def record_sale(self, delivered_mwh: float, dwell_periods: float) -> None:
        delivered = max(float(delivered_mwh), 0.0)
        dwell = max(float(dwell_periods), 0.0)
        self.current.sold_energy_mwh += delivered
        self.current.dwell_weighted_sold_mwh_periods += delivered * dwell

    def bid_price_gbp_per_mwh(self, dwell_periods: float) -> float:
        if self.bid_basis == "cycle_only":
            return self.cycle_depreciation_gbp_per_mwh
        return self.cycle_depreciation_gbp_per_mwh + (
            max(float(dwell_periods), 0.0)
            * self.holding_recovery_gbp_per_mwh_period
        )

    def ordered_charge_periods(
        self, stored_energy: dict[int, float], current_period: int
    ):
        """Return the exact merit order without sorting a linear dwell bid.

        Charge-period keys are inserted chronologically by ``Battery``. With a
        positive holding coefficient, newer tranches have strictly lower bids;
        with a zero coefficient the retained stable-sort tie order is insertion
        order. ``current_period`` is accepted for the common policy contract.
        """
        del current_period
        if self.bid_basis == "cycle_only":
            # Equal bids for every tranche: oldest first (stable insertion order).
            return iter(stored_energy)
        if self.holding_recovery_gbp_per_mwh_period > 0:
            return reversed(stored_energy)
        return iter(stored_energy)

    def report(self) -> dict[str, float | int | str | None | dict]:
        return {
            "method": "dynamic_annual_average_depreciation_recovery",
            "technology": self.battery_type,
            "technology_spec": asdict(self.spec),
            "prepared_year": self.prepared_year,
            "pricing_basis": self.pricing_basis,
            "pricing_basis_sold_mwh": self.pricing_basis_sold_mwh,
            "pricing_basis_average_dwell_periods": self.pricing_basis_average_dwell_periods,
            "cycle_depreciation_gbp_per_mwh": self.cycle_depreciation_gbp_per_mwh,
            "holding_recovery_gbp_per_mwh_period": self.holding_recovery_gbp_per_mwh_period,
            "annual_levelized_project_cost_gbp": self.annual_levelized_project_cost_gbp,
            "annualized_capital_cost_gbp": self.annualized_capital_cost_gbp,
            "annual_fixed_opex_gbp": self.annual_fixed_opex_gbp,
            "current_cycle_depreciation_gbp": (
                self.cycle_depreciation_gbp_per_mwh * self.current.sold_energy_mwh
            ),
            "previous_year_sold_mwh": self.previous.sold_energy_mwh,
            "current_year_sold_mwh": self.current.sold_energy_mwh,
            "current_year_average_dwell_periods": self.current.average_dwell_periods,
        }


ALLOWED_FORMULA_VARIABLES = frozenset({
    "cycle_depreciation_gbp_per_mwh",
    "dwell_periods",
    "holding_recovery_gbp_per_mwh_period",
    "annual_levelized_project_cost_gbp",
    "pricing_basis_sold_mwh",
})
_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Name,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Load,
)


def compile_storage_formula(expression: str):
    """Compile arithmetic only; never permit arbitrary Python execution."""

    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("storage.cost.custom_formula must be a non-empty expression")
    if len(expression) > 500:
        raise ValueError("storage.cost.custom_formula is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("storage.cost.custom_formula is not valid arithmetic") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_AST_NODES):
            raise ValueError(
                "storage.cost.custom_formula permits arithmetic operators and approved variables only"
            )
        if isinstance(node, ast.Name) and node.id not in ALLOWED_FORMULA_VARIABLES:
            raise ValueError(f"Unknown storage-cost formula variable: {node.id}")
        if isinstance(node, ast.Constant) and (
            isinstance(node.value, bool) or not isinstance(node.value, (int, float))
        ):
            raise ValueError("Storage-cost formula constants must be numeric")
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Pow)
            and isinstance(node.right, ast.Constant)
            and abs(float(node.right.value)) > 8
        ):
                raise ValueError("Storage-cost formula exponent is outside the safe range")
    return compile(tree, "<storage-cost-formula>", "eval")


class UserFormulaAnnualStorageCost(DynamicAnnualStorageCost):
    def __init__(self, *, formula: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.formula = formula
        self._compiled_formula = compile_storage_formula(formula)

    def bid_price_gbp_per_mwh(self, dwell_periods: float) -> float:
        variables = {
            "cycle_depreciation_gbp_per_mwh": self.cycle_depreciation_gbp_per_mwh,
            "dwell_periods": max(float(dwell_periods), 0.0),
            "holding_recovery_gbp_per_mwh_period": self.holding_recovery_gbp_per_mwh_period,
            "annual_levelized_project_cost_gbp": self.annual_levelized_project_cost_gbp,
            "pricing_basis_sold_mwh": self.pricing_basis_sold_mwh,
        }
        value = float(eval(self._compiled_formula, {"__builtins__": {}}, variables))
        if not isfinite(value) or value < 0:
            raise ValueError("User storage-cost formula produced a negative or non-finite bid")
        return value

    def ordered_charge_periods(
        self, stored_energy: dict[int, float], current_period: int
    ):
        # User arithmetic may be non-monotonic. Preserve the general stable
        # sort instead of applying the built-in policies' linear shortcut.
        return iter(sorted(
            stored_energy,
            key=lambda charge_period: self.bid_price_gbp_per_mwh(
                current_period - charge_period
            ),
        ))

    def report(self) -> dict[str, float | int | str | None | dict]:
        result = super().report()
        result["method"] = "user_formula_annual_storage_cost"
        result["formula"] = self.formula
        return result


class SchemeCLegacyTariffStorageCost:
    """Historical tariff equation, isolated from the retained implementation."""

    def __init__(
        self,
        *,
        battery_type: str,
        storage_fee_gbp_per_mwh: float,
        holding_fee_gbp_per_mwh_period: float,
        period_hours: float = 0.5,
    ) -> None:
        self.battery_type = battery_type
        self.spec = technology_spec(battery_type)
        self.period_hours = float(period_hours)
        self.storage_fee_gbp_per_mwh = max(float(storage_fee_gbp_per_mwh), 0.0)
        self.holding_fee_gbp_per_mwh_period = max(
            float(holding_fee_gbp_per_mwh_period), 0.0
        )
        # Compatibility aliases consumed by the copied modular Battery.
        self.cycle_depreciation_gbp_per_mwh = self.storage_fee_gbp_per_mwh
        self.holding_recovery_gbp_per_mwh_period = self.holding_fee_gbp_per_mwh_period
        self.annual_levelized_project_cost_gbp = 0.0
        self.annualized_capital_cost_gbp = 0.0
        self.annual_fixed_opex_gbp = 0.0
        self.pricing_basis_sold_mwh = 0.0
        self.pricing_basis_average_dwell_periods = 0.0
        self.pricing_basis = "scheme_c_hard_coded_tariff"
        self.prepared_year: int | None = None
        self.previous = AnnualStorageObservation()
        self.current = AnnualStorageObservation()

    def prepare_year(self, year: int, **_kwargs) -> None:
        year = int(year)
        if self.prepared_year == year:
            return
        if self.prepared_year is not None:
            self.previous = self.current
        self.current = AnnualStorageObservation(year=year)
        self.prepared_year = year

    def record_sale(self, delivered_mwh: float, dwell_periods: float) -> None:
        delivered = max(float(delivered_mwh), 0.0)
        dwell = max(float(dwell_periods), 0.0)
        self.current.sold_energy_mwh += delivered
        self.current.dwell_weighted_sold_mwh_periods += delivered * dwell

    def bid_price_gbp_per_mwh(self, dwell_periods: float) -> float:
        return self.storage_fee_gbp_per_mwh + (
            max(float(dwell_periods), 0.0) * self.holding_fee_gbp_per_mwh_period
        )

    def ordered_charge_periods(
        self, stored_energy: dict[int, float], current_period: int
    ):
        del current_period
        if self.holding_fee_gbp_per_mwh_period > 0:
            return reversed(stored_energy)
        return iter(stored_energy)

    def report(self) -> dict[str, object]:
        return {
            "method": "scheme_c_legacy_storage_tariff",
            "technology": self.battery_type,
            "prepared_year": self.prepared_year,
            "pricing_basis": self.pricing_basis,
            "fixed_tariff_gbp_per_mwh": self.storage_fee_gbp_per_mwh,
            "holding_tariff_gbp_per_mwh_period": self.holding_fee_gbp_per_mwh_period,
            "cycle_depreciation_gbp_per_mwh": 0.0,
            "annual_levelized_project_cost_gbp": 0.0,
            "annualized_capital_cost_gbp": 0.0,
            "annual_fixed_opex_gbp": 0.0,
            "current_cycle_depreciation_gbp": 0.0,
            "pricing_basis_sold_mwh": 0.0,
            "pricing_basis_average_dwell_periods": 0.0,
            "previous_year_sold_mwh": self.previous.sold_energy_mwh,
            "current_year_sold_mwh": self.current.sold_energy_mwh,
            "current_year_average_dwell_periods": self.current.average_dwell_periods,
        }


_RUNTIME_NUMERIC_FIELDS = (
    "cycle_depreciation_gbp_per_mwh",
    "holding_recovery_gbp_per_mwh_period",
    "annual_levelized_project_cost_gbp",
    "annualized_capital_cost_gbp",
    "annual_fixed_opex_gbp",
    "pricing_basis_sold_mwh",
    "pricing_basis_average_dwell_periods",
)
_RUNTIME_STATE_FIELDS = frozenset({
    "schema_version",
    "prepared_year",
    "pricing_basis",
    "previous",
    "current",
    *_RUNTIME_NUMERIC_FIELDS,
})
_OBSERVATION_FIELDS = frozenset({
    "year",
    "sold_energy_mwh",
    "dwell_weighted_sold_mwh_periods",
})


def _finite_runtime_number(
    value: object, field_name: str, *, nonnegative: bool = False
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    if nonnegative and result < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _runtime_observation(
    value: object, field_name: str
) -> AnnualStorageObservation:
    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_FIELDS:
        raise ValueError(
            f"{field_name} fields must be exactly {sorted(_OBSERVATION_FIELDS)}"
        )
    year = value["year"]
    if year is not None and (
        isinstance(year, bool) or not isinstance(year, int)
    ):
        raise ValueError(f"{field_name}.year must be an integer or null")
    return AnnualStorageObservation(
        year=year,
        sold_energy_mwh=_finite_runtime_number(
            value["sold_energy_mwh"],
            f"{field_name}.sold_energy_mwh",
            nonnegative=True,
        ),
        dwell_weighted_sold_mwh_periods=_finite_runtime_number(
            value["dwell_weighted_sold_mwh_periods"],
            f"{field_name}.dwell_weighted_sold_mwh_periods",
            nonnegative=True,
        ),
    )


def _validate_runtime_years(
    prepared_year: int | None,
    previous: AnnualStorageObservation,
    current: AnnualStorageObservation,
) -> None:
    if prepared_year is None:
        if previous.year is not None or current.year is not None:
            raise ValueError(
                "Unprepared storage-cost state cannot contain observation years"
            )
    else:
        if current.year != prepared_year:
            raise ValueError("current observation year must equal prepared_year")
        if previous.year is not None and previous.year >= current.year:
            raise ValueError("previous observation year must precede current year")
    for field_name, observation in (("previous", previous), ("current", current)):
        if observation.year is None and (
            observation.sold_energy_mwh != 0.0
            or observation.dwell_weighted_sold_mwh_periods != 0.0
        ):
            raise ValueError(
                f"{field_name} observation without a year must have zero totals"
            )


def snapshot_storage_cost_runtime(model: object) -> Mapping[str, object]:
    """Return only mutable annual pricing state as JSON-compatible values."""

    previous = getattr(model, "previous", None)
    current = getattr(model, "current", None)
    if not isinstance(previous, AnnualStorageObservation) or not isinstance(
        current, AnnualStorageObservation
    ):
        raise TypeError("Storage-cost model does not expose annual observations")
    prepared_year = getattr(model, "prepared_year", None)
    if prepared_year is not None and (
        isinstance(prepared_year, bool) or not isinstance(prepared_year, int)
    ):
        raise ValueError("prepared_year must be an integer or null")
    pricing_basis = getattr(model, "pricing_basis", None)
    if not isinstance(pricing_basis, str) or not pricing_basis:
        raise ValueError("pricing_basis must be a non-empty string")
    previous = _runtime_observation(asdict(previous), "previous")
    current = _runtime_observation(asdict(current), "current")
    _validate_runtime_years(prepared_year, previous, current)
    payload: dict[str, object] = {
        "schema_version": "value.storage-cost-runtime-state/v1",
        "prepared_year": prepared_year,
        "pricing_basis": pricing_basis,
        "previous": asdict(previous),
        "current": asdict(current),
    }
    for field_name in _RUNTIME_NUMERIC_FIELDS:
        payload[field_name] = _finite_runtime_number(
            getattr(model, field_name, None), field_name, nonnegative=True
        )
    return payload


def restore_storage_cost_runtime(
    model: object, payload: Mapping[str, object]
) -> None:
    """Restore declared annual state onto a freshly rebuilt pricing object."""

    if not isinstance(payload, Mapping) or set(payload) != _RUNTIME_STATE_FIELDS:
        raise ValueError(
            f"Storage-cost runtime fields must be exactly {sorted(_RUNTIME_STATE_FIELDS)}"
        )
    if payload["schema_version"] != "value.storage-cost-runtime-state/v1":
        raise ValueError("Unsupported storage-cost runtime schema_version")
    prepared_year = payload["prepared_year"]
    if prepared_year is not None and (
        isinstance(prepared_year, bool) or not isinstance(prepared_year, int)
    ):
        raise ValueError("prepared_year must be an integer or null")
    pricing_basis = payload["pricing_basis"]
    if not isinstance(pricing_basis, str) or not pricing_basis:
        raise ValueError("pricing_basis must be a non-empty string")
    previous = _runtime_observation(payload["previous"], "previous")
    current = _runtime_observation(payload["current"], "current")
    _validate_runtime_years(prepared_year, previous, current)
    numeric = {
        field_name: _finite_runtime_number(
            payload[field_name], field_name, nonnegative=True
        )
        for field_name in _RUNTIME_NUMERIC_FIELDS
    }
    if not isinstance(getattr(model, "previous", None), AnnualStorageObservation):
        raise TypeError("Storage-cost model must be rebuilt before runtime restore")
    if not isinstance(getattr(model, "current", None), AnnualStorageObservation):
        raise TypeError("Storage-cost model must be rebuilt before runtime restore")
    for field_name in _RUNTIME_NUMERIC_FIELDS:
        if not hasattr(model, field_name):
            raise TypeError(f"Storage-cost model lacks runtime field {field_name}")

    model.previous = previous
    model.current = current
    model.prepared_year = prepared_year
    model.pricing_basis = pricing_basis
    for field_name, value in numeric.items():
        setattr(model, field_name, value)


class DynamicStorageCostDefinition:
    id = "dynamic-annual-storage-cost"
    version = "1.0.0"
    scientific_version = "dynamic-storage-recovery-2026.08.04"

    def __init__(self, evidence=None, scientific_parameters: Mapping[str, object] | None = None):
        self.evidence = evidence
        self.parameters = dict(scientific_parameters or {})
        if evidence is not None:
            evidence.record(self.id, self.version, "storage_cost.selected", scientific_version=self.scientific_version)

    def create(self, *, battery_type: str, period_hours: float, **_legacy):
        return DynamicAnnualStorageCost(
            battery_type=battery_type,
            period_hours=period_hours,
            discount_rate=float(self.parameters.get("storage.cost.discount_rate", 0.05)),
            utilisation_floor=float(
                self.parameters.get("storage.cost.utilisation_floor_fraction", 0.0)
            ),
        )


class SchemeCLegacyStorageCostDefinition:
    id = "scheme-c-legacy-storage-tariff"
    version = "1.0.0"
    scientific_version = "scheme-c-storage-tariffs-2026.07.18"

    def __init__(self, evidence=None, scientific_parameters: Mapping[str, object] | None = None):
        del scientific_parameters
        self.evidence = evidence
        if evidence is not None:
            evidence.record(self.id, self.version, "storage_cost.selected", scientific_version=self.scientific_version)

    def create(
        self,
        *,
        battery_type: str,
        period_hours: float,
        legacy_storage_fee: float = 0.0,
        legacy_holding_fee: float = 0.0,
        **_kwargs,
    ):
        return SchemeCLegacyTariffStorageCost(
            battery_type=battery_type,
            period_hours=period_hours,
            storage_fee_gbp_per_mwh=legacy_storage_fee,
            holding_fee_gbp_per_mwh_period=legacy_holding_fee,
        )


class UserFormulaStorageCostDefinition(DynamicStorageCostDefinition):
    id = "user-formula-storage-cost"
    scientific_version = "user-formula-storage-cost/v1"

    def create(self, *, battery_type: str, period_hours: float, **_legacy):
        return UserFormulaAnnualStorageCost(
            formula=str(self.parameters.get(
                "storage.cost.custom_formula",
                "cycle_depreciation_gbp_per_mwh + dwell_periods * holding_recovery_gbp_per_mwh_period",
            )),
            battery_type=battery_type,
            period_hours=period_hours,
            discount_rate=float(self.parameters.get("storage.cost.discount_rate", 0.05)),
            utilisation_floor=float(
                self.parameters.get("storage.cost.utilisation_floor_fraction", 0.0)
            ),
        )
