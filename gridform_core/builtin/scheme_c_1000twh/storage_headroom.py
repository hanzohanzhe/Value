"""Corrected storage expansion headroom (P0-7 S6/S7, findings P5-01 and P5-02).

Only the value-corrected profile uses this module; the doctoral profile keeps
the 35aadb3 typed path (zero headroom from accepted VRE minus demand, and the
same power cap copied to each of the three power batteries), decision Q1.

* P5-01: new storage may charge only from the surplus left after the existing
  fleet charged. The PSM publishes that per-period trace
  (``storage_headroom_inputs``, from its declared column semantics); the
  retained Scheme C kernel turns it into the aligned-utilisation spectrum.
  A chronology that is not one full year of 17520 half-hour periods gives no
  headroom (reason ``partial_year_chronology``), and a PSM without the trace
  gives none either (reason ``leftover_trace_unavailable``); neither is a
  silent zero.
* P5-02: the three power batteries share one pool of
  ``cap_fraction x power_room`` instead of receiving it three times.
* No kernel global is written (the HEAD path rebinds ``CAP_FRACTION``).
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

HEADROOM_INPUTS_KEY = "storage_headroom_inputs"
HEADROOM_INPUTS_SCHEMA = "value.storage-headroom-inputs/v1"
HEADROOM_SEMANTICS = "corrected_leftover_power_pool_v1"
POWER_BATTERY_POOL = "power_battery_pool"
POWER_BATTERIES = ("0.25c_battery", "0.5c_battery", "1c_battery")
HYDROGEN_BATTERY = "hydrogen_battery"
STORAGE_POLICY_IDS = frozenset({"storage-expansion-scheme-c", "value-storage-expansion-policy"})
FULL_YEAR_PERIODS = 17520
FULL_YEAR_PERIOD_HOURS = 0.5


def headroom_inputs(leftover_mwh: Sequence[float], *, basis: str, psm_module_id: str) -> dict[str, object]:
    """The PSM side: the per-period post-charge surplus (MWh) and how it was read."""
    values = [float(value) for value in leftover_mwh]
    return {"schema_version": HEADROOM_INPUTS_SCHEMA, "psm_module_id": psm_module_id,
            "leftover_excess_basis": basis, "leftover_excess_mwh": values}


def _trace(values: object, label: str, periods: int) -> list[float]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ValueError(f"{label} must be a sequence of MWh")
    parsed = [float(value) for value in values]
    if len(parsed) != periods:
        raise ValueError(f"{label} has {len(parsed)} periods; the market has {periods}")
    if any(not math.isfinite(value) or value < 0 for value in parsed):
        raise ValueError(f"{label} must be finite and nonnegative")
    return parsed


def corrected_storage_headroom(
    period_summaries: Sequence[object],
    market_extensions: Mapping[str, object],
    *,
    cap_fraction: float,
    period_hours: float,
    pooled: bool,
    existing_mw_by_technology: Mapping[str, float],
) -> tuple[dict[str, float], dict[str, float], dict[str, object]]:
    """Return (allowed MW by technology, numeric evidence, extensions)."""
    from .storage import storage_expansion_cap as kernel

    fraction = float(cap_fraction)
    if not math.isfinite(fraction) or fraction < 0:
        raise ValueError("expansion.storage_cap_fraction must be finite and nonnegative")
    periods = len(period_summaries)
    zero = {tech: 0.0 for tech in (*POWER_BATTERIES, HYDROGEN_BATTERY)}
    extensions: dict[str, object] = {
        "headroom_semantics": HEADROOM_SEMANTICS,
        "pooled_power_batteries": bool(pooled),
        "existing_storage_mw_by_technology": dict(sorted(existing_mw_by_technology.items())),
        "kernel_globals_written": False,
    }
    evidence: dict[str, float] = {"cap_fraction": fraction, "native_typed_execution": 1.0,
                                  "periods": float(periods), "period_hours": float(period_hours)}
    reason = None
    if periods != FULL_YEAR_PERIODS or float(period_hours) != FULL_YEAR_PERIOD_HOURS:
        reason = "partial_year_chronology"
    inputs = market_extensions.get(HEADROOM_INPUTS_KEY)
    if reason is None and not isinstance(inputs, Mapping):
        reason = "leftover_trace_unavailable"
    if reason is not None:
        extensions["reason"] = reason
        if pooled:
            extensions["pools"] = {POWER_BATTERY_POOL: {"cap_mw": 0.0, "technologies": list(POWER_BATTERIES)}}
        return zero, evidence, extensions
    assert isinstance(inputs, Mapping)
    if inputs.get("schema_version") != HEADROOM_INPUTS_SCHEMA:
        raise ValueError(f"{HEADROOM_INPUTS_KEY} is not {HEADROOM_INPUTS_SCHEMA}")
    leftover = _trace(inputs.get("leftover_excess_mwh"), "post-charge leftover excess", periods)
    vre = [float(row.vre_accepted_mwh) for row in period_summaries]
    demand = [float(row.real_demand_mwh) for row in period_summaries]
    discharge = [float(row.storage_discharge_mwh) for row in period_summaries]
    charge = [float(row.storage_charge_mwh) for row in period_summaries]
    excess, deficit, mode = kernel.build_deficit_for_cap(
        vre, demand, excess_generation=leftover, storage_discharge=discharge,
        store_charge=charge, cap_row={}, credit_mode="scheme_c")
    spectrum = kernel.aligned_utilisation_spectrum(excess, deficit)
    daily = float(spectrum["daily_loop"])
    intraday = float(spectrum["intraday"])
    seasonal = float(spectrum["seasonal"])
    power_room = max(0.0, daily + intraday)
    power_cap = fraction * power_room
    hydrogen_cap = fraction * max(0.0, seasonal)
    allowed = {tech: power_cap for tech in POWER_BATTERIES}
    allowed[HYDROGEN_BATTERY] = hydrogen_cap
    evidence.update({"daily_loop_mw": daily, "intraday_mw": intraday, "seasonal_mw": seasonal,
                     "power_room_mw": power_room, "power_pool_cap_mw": power_cap,
                     "leftover_excess_mwh": math.fsum(leftover)})
    extensions.update({"reason": None, "credit_mode": mode,
                       "leftover_excess_basis": inputs.get("leftover_excess_basis"),
                       "leftover_source_psm": inputs.get("psm_module_id")})
    if pooled:
        extensions["pools"] = {POWER_BATTERY_POOL: {"cap_mw": power_cap, "technologies": list(POWER_BATTERIES)}}
    return allowed, evidence, extensions


def headroom_pools(headroom: Sequence[object], *, pooled: bool) -> dict[str, dict[str, object]]:
    """Shared pools declared by the headroom rows; refused across profiles.

    A doctoral run (per-technology caps, Q1) receiving a pooled corrected row
    is an error rather than a silent reinterpretation.
    """
    pools: dict[str, dict[str, object]] = {}
    for row in headroom:
        extensions = dict(getattr(row, "extensions", {}) or {})
        declared = extensions.get("pools")
        if not declared:
            continue
        if not pooled:
            raise ValueError(
                f"headroom {getattr(row, 'module_id', '?')} declares shared pools "
                f"({extensions.get('headroom_semantics')}); this run's methodology keeps per-technology caps")
        for key, spec in dict(declared).items():
            cap = float(spec["cap_mw"])
            technologies = tuple(str(tech) for tech in spec["technologies"])
            if key in pools:
                if tuple(pools[key]["technologies"]) != technologies:
                    raise ValueError(f"pool {key} is declared with different technologies")
                cap = min(cap, float(pools[key]["cap_mw"]))
            pools[str(key)] = {"cap_mw": max(0.0, cap), "technologies": technologies}
    return pools
