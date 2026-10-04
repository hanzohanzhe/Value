"""Actual Scheme C 1000 TWh virtual-pool storage cap adapter."""

from __future__ import annotations

import numpy as np

from ...contracts import CapacityDecision, ModelState, PSMResult, YearContext
from .storage import storage_expansion_cap as kernel


class SchemeCStorageExpansion:
    id = "storage-expansion-scheme-c"
    version = "1000twh-2026.07.22"
    order = 40

    def decide(self, context: YearContext, state: ModelState, psm_result: PSMResult, previous_decisions):
        del previous_decisions
        kernel.CAP_FRACTION = float(context.parameters.get("storage_cap_fraction", 0.20))
        kernel.VIRTUAL_POOL_ENERGY_MWH = float(context.parameters.get("storage_virtual_pool_energy_mwh", 1_000_000_000.0))
        cap_row = {
            kernel.BATTERY_CAP_COLUMNS[asset.technology]: asset.capacity_mw
            for asset in state.assets
            if asset.technology in kernel.BATTERY_CAP_COLUMNS
        }
        limits = kernel.calculate_storage_expansion_limits_from_profiles(
            np.asarray(psm_result.vre_generation_mwh, dtype=float),
            np.asarray(psm_result.demand_mwh, dtype=float),
            prices=np.asarray(psm_result.prices_gbp_per_mwh, dtype=float),
            cap_row=cap_row,
            storage_discharge=np.asarray(psm_result.storage_discharge_mwh, dtype=float),
            credit_mode="scheme_c",
        )
        return CapacityDecision(
            module_id=self.id,
            additions_mw=limits,
            evidence={
                "cap_fraction": kernel.CAP_FRACTION,
                "virtual_pool_energy_mwh": kernel.VIRTUAL_POOL_ENERGY_MWH,
            },
        )
