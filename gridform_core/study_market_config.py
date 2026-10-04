"""One projection of authoritative module and parameter Study choices."""

from __future__ import annotations

import math
from typing import Mapping

from .zonal_demand_alignment import SUPPORTED_ZONAL_DEMAND_MODES


def resolve_market_configuration(
    modules: Mapping[str, object],
    parameters: Mapping[str, object],
    runtime_controls: Mapping[str, object],
    supplied: Mapping[str, object] | None = None,
) -> dict[str, object]:
    result = {
        "ahead_market_module_id": str(modules.get("psm") or ""),
        "balancing_module_id": str(modules.get("balancing") or ""),
        "network_pack_id": "",
        "zonal_demand_mode": "",
        "weather_spatialisation_module_id": str(modules.get("weather_spatializer") or ""),
        "ledger_detail": str(
            runtime_controls.get("runtime.market_trace_level")
            or runtime_controls.get("market_trace_level")
            or "summary"
        ),
        "voll_gbp_per_mwh": float(parameters.get("market.voll_gbp_per_mwh", 10_000.0)),
    }
    if supplied:
        result.update({str(key): value for key, value in supplied.items()})
    expected = {
        "ahead_market_module_id": str(modules.get("psm") or ""),
        "balancing_module_id": str(modules.get("balancing") or ""),
        "weather_spatialisation_module_id": str(modules.get("weather_spatializer") or ""),
    }
    for field_name, value in expected.items():
        if str(result.get(field_name) or "") != value:
            label = field_name.replace("_module_id", "").replace("_", " ")
            raise ValueError(
                f"Explicit market configuration {label} does not match the authoritative module selection"
            )
    declared_voll = float(result.get("voll_gbp_per_mwh", 10_000.0))
    if not math.isfinite(declared_voll) or declared_voll <= 0:
        raise ValueError("Explicit market configuration VOLL must be finite and positive")
    if abs(declared_voll - float(parameters.get("market.voll_gbp_per_mwh", 10_000.0))) > 1e-12:
        raise ValueError("Explicit market configuration VOLL does not match the parameter registry")
    expected_ledger = str(
        runtime_controls.get("runtime.market_trace_level")
        or runtime_controls.get("market_trace_level")
        or "summary"
    )
    if str(result.get("ledger_detail") or "") != expected_ledger:
        raise ValueError(
            "Explicit market configuration ledger detail does not match runtime controls"
        )
    if expected_ledger not in {"off", "summary", "full"}:
        raise ValueError("Explicit market configuration ledger detail is unsupported")
    demand_mode = str(result.get("zonal_demand_mode") or "")
    zonal = expected["balancing_module_id"] == "value-zonal-redispatch-balancing"
    if zonal and demand_mode not in SUPPORTED_ZONAL_DEMAND_MODES:
        supported = ", ".join(sorted(SUPPORTED_ZONAL_DEMAND_MODES))
        raise ValueError(
            "Explicit market configuration zonal_demand_mode is required for zonal "
            f"balancing and must be one of: {supported}"
        )
    if not zonal and demand_mode:
        raise ValueError(
            "Explicit market configuration zonal_demand_mode is only valid for zonal balancing"
        )
    result["zonal_demand_mode"] = demand_mode
    return result
