"""One projection of authoritative module and parameter Study choices."""

from __future__ import annotations

import math
from typing import Mapping

from .zonal_demand_alignment import SUPPORTED_ZONAL_DEMAND_MODES
from .voll import LEGACY_DEFAULT_VOLL_GBP_PER_MWH, VOLL_GBP_PER_MWH


def _registry_voll(parameters: Mapping[str, object]) -> float:
    return float(parameters.get("market.voll_gbp_per_mwh", VOLL_GBP_PER_MWH))


def _reprojected_voll(declared: object, parameters: Mapping[str, object]) -> object:
    """The VoLL of a supplied market configuration, re-projected when stale.

    The market configuration is a projection of the Study's parameters.  A
    Study saved before decision A16-5 may carry the old registry default
    (10000 GBP/MWh) in it although it never overrode
    ``market.voll_gbp_per_mwh``; that projection follows the current default
    (17000) instead of failing the consistency check below.  An explicit
    parameter override is authoritative and is checked as before.
    """

    if "market.voll_gbp_per_mwh" in parameters:
        return declared
    try:
        value = float(declared)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return declared
    if value == LEGACY_DEFAULT_VOLL_GBP_PER_MWH:
        return VOLL_GBP_PER_MWH
    return declared


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
        "voll_gbp_per_mwh": _registry_voll(parameters),
    }
    if supplied:
        result.update({str(key): value for key, value in supplied.items()})
        result["voll_gbp_per_mwh"] = _reprojected_voll(result.get("voll_gbp_per_mwh"), parameters)
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
    declared_voll = float(result.get("voll_gbp_per_mwh", VOLL_GBP_PER_MWH))
    if not math.isfinite(declared_voll) or declared_voll <= 0:
        raise ValueError("Explicit market configuration VOLL must be finite and positive")
    if abs(declared_voll - _registry_voll(parameters)) > 1e-12:
        raise ValueError("Explicit market configuration VOLL does not match the parameter registry")
    # R3-N1 (DECISIONS A23): the VoLL is a float parameter; an editor that
    # sends 17000 for 17000.0 must not make an unchanged Study a new revision.
    result["voll_gbp_per_mwh"] = declared_voll
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
