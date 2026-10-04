"""Scheme C demand-profile expansion caps for solar, onshore and offshore."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ...contracts import CapacityDecision, ModelState, PSMResult, YearContext
from ...data import required_uri


def calculate_expansion_limit(demand_path: str, profile_path: str, negative_threshold: int = 200) -> float:
    demand = pd.to_numeric(pd.read_csv(demand_path).iloc[:, 0], errors="coerce").fillna(0).to_numpy()
    profile = pd.to_numeric(pd.read_csv(profile_path, header=None).iloc[:, 0], errors="coerce").fillna(0).to_numpy()
    length = min(len(demand), len(profile))
    demand, profile = demand[:length], profile[:length]
    if not np.any(profile > 0):
        return 0.0
    low, high = 0.0, max(float(np.max(demand)) / max(float(np.mean(profile)), 1e-9) * 4, 1.0)
    for _ in range(60):
        midpoint = (low + high) / 2
        negative_count = int(np.count_nonzero(demand - midpoint * profile < 0))
        if negative_count > negative_threshold:
            high = midpoint
        else:
            low = midpoint
    return low


class SchemeCVREExpansion:
    id = "vre-expansion-cap"
    version = "1000twh-2026.07.19"
    order = 30

    def decide(self, context: YearContext, state: ModelState, psm_result: PSMResult, previous_decisions):
        del state, psm_result, previous_decisions
        fraction = float(context.parameters.get("vre_expansion_cap_fraction", 0.20))
        demand = required_uri(context.data_pack, "demand.real")
        additions = {}
        for tech, role in {
            "solar": "profiles.vre_solar",
            "onshore": "profiles.vre_onshore",
            "offshore": "profiles.vre_offshore",
        }.items():
            additions[tech] = fraction * calculate_expansion_limit(demand, required_uri(context.data_pack, role))
        return CapacityDecision(module_id=self.id, additions_mw=additions, evidence={"cap_fraction": fraction})
