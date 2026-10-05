"""Period realisation records of the default PSM kernel (plan P0-6 S3).

``realise_period`` in ``runtime_compat/modular_simulation_model.py`` runs the
real-time stage of one period (curtailment or balancing market, chosen by the
thesis forecast rule; decision A2 keeps that rule in both profiles) and
returns a :class:`PeriodRealisation`.  ``run_simulation`` appends exactly the
values the HEAD loop appended, so the refactor is bit-identical.

The kernel also writes the period's flows into a :class:`RealisationLog`:
plain numpy arrays (no references to generator, battery or connection
objects) in kernel power units, i.e. MW held over the period; multiply by the
period length in hours for MWh.  The energy identities over these flows live
only in :mod:`gridform_core.energy_balance_contract` (C19).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

CURTAILMENT_BRANCH = 0
BALANCING_BRANCH = 1
BRANCH_NAMES = {CURTAILMENT_BRANCH: "curtailment", BALANCING_BRANCH: "balancing"}

LOG_COLUMNS = (
    "forecast_demand_mw", "real_demand_mw", "storage_charge_mw", "excess_mw",
    "curtailed_mw", "blackout_mw", "flexible_demand_mw", "export_mw",
)

# P0-6 S4 physical-cost and settlement terms per period (GBP) and the doctoral
# market-rule diagnostics (kernel units: MW, or GBP per hour for the storage
# fee carry); kept outside LOG_COLUMNS like the surplus terms.
COST_COLUMNS = (
    "generation_variable_gbp", "import_variable_gbp", "startup_adder_gbp",
    "storage_offer_payment_gbp", "retained_period_cost_gbp", "generation_offer_payment_gbp",
    "storage_fee_retained_gbp", "curtailment_payment_gbp", "balancing_payment_gbp",
    "export_revenue_gbp", "import_payment_gbp",
)
DIAGNOSTIC_COLUMNS = (
    "unrecorded_vre_mw", "storage_fee_carry_gbp_per_h", "vre_skim_leak_mw",
    "vre_skim_to_electrolysis_mw", "phantom_surplus_mw",
)

# P0-4 S5 surplus-node terms per period (MWh; not part of the P0-6 log view).
SURPLUS_COLUMNS = (
    "u_out_mwh", "non_vre_spill_mwh", "non_vre_double_counted_mwh",
    "u_out_to_storage_mwh", "u_out_to_export_mwh", "u_out_to_flexible_mwh",
)


@dataclass
class PeriodRealisation:
    """Outcome of one period's real-time stage, as the HEAD loop consumed it.

    The appended values keep the HEAD types exactly (for instance the integer
    ``0`` a branch appended for a fee it does not have), because the trace
    writers serialise them.
    """

    branch: int
    real_list: Any
    store_energy: Any
    storage_pool_composition_after: Any
    gen_list: Any
    excess_energy: Any
    energy_cell_period: Any
    income_dict_balance: dict
    energy_deficit: Any
    total_storage_fee_balance: Any
    balance_renewables: Any
    balance_other: Any
    balance_traditional: Any
    balance_nuclear: Any
    curtailment_fee: Any
    balancing_fee: Any
    curtailed_energy: Any
    curtailed_energy_record: Any
    sold_fee: Any
    purchase_fee: Any
    green_hy: Any

    @property
    def branch_name(self) -> str:
        return BRANCH_NAMES[self.branch]


class RealisationLog:
    """Per-period realised flows of one kernel run (numpy, object-free)."""

    def __init__(self, periods: int = 0) -> None:
        self.start(periods)

    def start(self, periods: int) -> None:
        self.periods = int(periods)
        self.recorded = np.zeros(self.periods, dtype=bool)
        self.branch = np.full(self.periods, -1, dtype=np.int8)
        for column in LOG_COLUMNS:
            setattr(self, column, np.zeros(self.periods, dtype=np.float64))
        self._start_surplus()
        self._start_costs()

    def record(self, period: int, realisation: PeriodRealisation, *, forecast_demand: float,
               real_demand: float, flexible_demand: float, export: float) -> None:
        self.recorded[period] = True
        self.branch[period] = realisation.branch
        self.forecast_demand_mw[period] = float(forecast_demand)
        self.real_demand_mw[period] = float(real_demand)
        self.storage_charge_mw[period] = float(realisation.store_energy or 0.0)
        self.excess_mw[period] = float(realisation.excess_energy or 0.0)
        self.curtailed_mw[period] = float(realisation.curtailed_energy or 0.0)
        self.blackout_mw[period] = float(realisation.energy_deficit or 0.0)
        self.flexible_demand_mw[period] = float(flexible_demand or 0.0)
        self.export_mw[period] = float(export or 0.0)

    def record_surplus(self, period: int, trace: Any, terms: Any) -> None:
        """P0-4 S5: node terms of the period (MWh), kept outside LOG_COLUMNS.

        ``trace`` is the kernel's SurplusTrace and ``terms`` its
        PeriodSurplusTerms; only numbers are kept.
        """

        if not hasattr(self, "u_out_mwh") or len(self.u_out_mwh) != self.periods:
            self._start_surplus()
        self.u_out_mwh[period] = float(terms.u_out_mwh)
        self.non_vre_spill_mwh[period] = float(terms.w_in_mwh)
        self.non_vre_double_counted_mwh[period] = float(terms.non_vre_double_counted_mwh)
        out = trace.routing["out_of_dispatch"]
        hours = float(terms.period_hours)
        self.u_out_to_storage_mwh[period] = out["to_storage"] * hours
        self.u_out_to_export_mwh[period] = out["to_export"] * hours
        self.u_out_to_flexible_mwh[period] = out["to_flexible"] * hours

    def record_costs(self, period: int, terms: Any, diagnostics: Any) -> None:
        """P0-6 S4: physical cost and settlement terms (GBP) and rule diagnostics."""

        if not hasattr(self, "generation_variable_gbp") or len(self.generation_variable_gbp) != self.periods:
            self._start_costs()
        for column in COST_COLUMNS:
            getattr(self, column)[period] = float(terms.get(column, 0.0))
        for column in DIAGNOSTIC_COLUMNS:
            getattr(self, column)[period] = float(diagnostics.get(column, 0.0))

    def _start_costs(self) -> None:
        for column in COST_COLUMNS + DIAGNOSTIC_COLUMNS:
            setattr(self, column, np.zeros(self.periods, dtype=np.float64))

    def _start_surplus(self) -> None:
        for column in SURPLUS_COLUMNS:
            setattr(self, column, np.zeros(self.periods, dtype=np.float64))

    def as_dict(self) -> dict[str, list]:
        payload: dict[str, list] = {"branch": self.branch.tolist()}
        for column in LOG_COLUMNS:
            payload[column] = getattr(self, column).tolist()
        return payload


def active_realisation_log(runtime: object | None, periods: int) -> RealisationLog:
    """The runtime's log (restarted for this run) or a private one."""

    log = getattr(runtime, "realisation_log", None) if runtime is not None else None
    if log is None:
        return RealisationLog(periods)
    if not isinstance(log, RealisationLog):
        raise TypeError(f"runtime.realisation_log must be RealisationLog, not {type(log).__name__}")
    log.start(periods)
    return log
