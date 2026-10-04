"""Canonical VALUE-UK Study templates installed by a research suite."""

from __future__ import annotations

import copy
import re

from .frontend_contract import EXPERIMENTAL_ACK, builtin_maturity_acknowledgement_key
from .zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS


VALUE_UK_COPPERPLATE_STUDY_ID = "value-uk-copperplate-2025-2034"
VALUE_UK_ZONAL_STUDY_ID = "value-uk-zonal-2025-2034"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def value_uk_study_templates(
    base_pack_id: str,
    network_pack_id: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Return the controlled copperplate and zonal ten-year Study pair."""

    if not _SAFE_ID.fullmatch(base_pack_id) or not _SAFE_ID.fullmatch(network_pack_id):
        raise ValueError("VALUE-UK pack IDs must be safe immutable identifiers")
    modules = {
        "psm": "value-staged-bid-at-cost-psm",
        "storage_cost": "dynamic-annual-storage-cost",
        "investment": "agent-investment",
        "pipeline": "planning-pipeline",
        "vre_cap": "vre-expansion-cap",
        "storage_cap": "value-storage-expansion-policy",
        "transition": "value-annual-state-transition",
    }
    common: dict[str, object] = {
        "schema_version": "value.project/v1",
        "data_pack_id": base_pack_id,
        "start_year": 2025,
        "end_year": 2034,
        "purpose": "Compare the 2025-2034 VALUE-UK pathway under a declared physical system domain.",
        "parameters": {"market.voll_gbp_per_mwh": 17_000.0},
        "runtime_options": {
            "runtime.market_trace_level": "summary",
            "runtime.checkpoint_enabled": True,
        },
        "extension_parameters": {},
    }
    copperplate = {
        **copy.deepcopy(common),
        "id": VALUE_UK_COPPERPLATE_STUDY_ID,
        "name": "VALUE-UK copperplate 2025-2034",
        "modules": {**modules, "balancing": "value-copperplate-balancing"},
        "selected_extensions": [],
        "market_configuration": {},
        "maturity_acknowledgements": {},
    }
    zonal = {
        **copy.deepcopy(common),
        "id": VALUE_UK_ZONAL_STUDY_ID,
        "name": "VALUE-UK fixed-zonal network 2025-2034",
        "purpose": (
            "Compare the 2025-2034 VALUE-UK pathway with fixed GB zonal boundaries "
            "and post-market redispatch."
        ),
        "modules": {
            **modules,
            "balancing": "value-zonal-redispatch-balancing",
            "weather_spatializer": "value-representative-point-weather",
        },
        "selected_extensions": ["value-zonal-redispatch-extension"],
        "market_configuration": {
            "network_pack_id": network_pack_id,
            "zonal_demand_mode": "scenario_scaled_zonal_shares",
            "ledger_detail": "summary",
        },
        "solver_contract": DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
        "maturity_acknowledgements": {
            # Keys follow the registered module versions (X0 S7).
            builtin_maturity_acknowledgement_key("module", "value-zonal-redispatch-balancing"): EXPERIMENTAL_ACK,
            builtin_maturity_acknowledgement_key("module", "value-representative-point-weather"): EXPERIMENTAL_ACK,
            builtin_maturity_acknowledgement_key("extension", "value-zonal-redispatch-extension"): EXPERIMENTAL_ACK,
        },
    }
    return copperplate, zonal
