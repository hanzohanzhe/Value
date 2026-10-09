"""Executable fixed-price experiment; no scientific cost-recovery claim."""

from dataclasses import dataclass
from math import isfinite


@dataclass
class AnnualStorageObservation:
    """This example's own annual sales record.

    A module depends only on the public slot contract, never on VALUE's
    private ``scheme_c_1000twh/compat`` internals (MODULE_DEVELOPER_101,
    section 4), so the example keeps its own small record.
    """

    year: int | None = None
    sold_energy_mwh: float = 0.0
    dwell_weighted_sold_mwh_periods: float = 0.0

    @property
    def average_dwell_periods(self) -> float:
        if self.sold_energy_mwh <= 0:
            return 0.0
        return self.dwell_weighted_sold_mwh_periods / self.sold_energy_mwh


class FlatStorageOffer:
    def __init__(self, price_gbp_per_mwh: float = 42.0, **parameters) -> None:
        self.price_gbp_per_mwh = float(price_gbp_per_mwh)
        if not isfinite(self.price_gbp_per_mwh) or self.price_gbp_per_mwh < 0:
            raise ValueError("Fixed offer must be finite and non-negative")
        self.battery_type = parameters.get("battery_type")
        self.prepared_year = None
        # Consumer compatibility fields: this experiment models neither cost.
        self.cycle_depreciation_gbp_per_mwh = 0.0
        self.holding_recovery_gbp_per_mwh_period = 0.0
        self.previous = AnnualStorageObservation()
        self.current = AnnualStorageObservation()

    def prepare_year(self, year, **project):
        year = int(year)
        if self.prepared_year == year:
            return
        if self.prepared_year is not None:
            self.previous = self.current
        self.current = AnnualStorageObservation(year=year)
        self.prepared_year = year
        self.project = dict(project)

    def bid_price_gbp_per_mwh(self, dwell_periods):
        return self.price_gbp_per_mwh

    def record_sale(self, delivered_mwh, dwell_periods):
        delivered, dwell = float(delivered_mwh), float(dwell_periods)
        if not all(isfinite(value) and value >= 0 for value in (delivered, dwell)):
            raise ValueError("Sale and dwell must be finite and non-negative")
        self.current.sold_energy_mwh += delivered
        self.current.dwell_weighted_sold_mwh_periods += delivered * dwell

    def report(self):
        return {
            "method": "experimental_fixed_offer",
            "technology": self.battery_type,
            "prepared_year": self.prepared_year,
            "pricing_basis": "fixed_price_experiment_not_cost_recovery",
            "fixed_offer_gbp_per_mwh": self.price_gbp_per_mwh,
            "cycle_depreciation_gbp_per_mwh": self.cycle_depreciation_gbp_per_mwh,
            "holding_recovery_gbp_per_mwh_period": self.holding_recovery_gbp_per_mwh_period,
            "previous_year_sold_mwh": self.previous.sold_energy_mwh,
            "current_year_sold_mwh": self.current.sold_energy_mwh,
            "current_year_average_dwell_periods": self.current.average_dwell_periods,
        }


class FlatStorageCostDefinition:
    id = "example-flat-storage-offer"
    version = "1.0.0"
    scientific_version = "example-only-not-a-baseline"

    def create(self, **parameters):
        return FlatStorageOffer(**parameters)
