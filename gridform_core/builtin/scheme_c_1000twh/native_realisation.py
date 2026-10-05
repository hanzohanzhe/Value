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
