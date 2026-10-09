"""Economic rules of the staged / zonal network path (plan P0-8 S7-S10).

One immutable :class:`NetworkMethodRules` describes how the staged PSM prices
its balancing (dec) bids, how its copperplate balancer breaks equal-price ties,
which engine prices the network-free counterfactual and how boundary marginal
values are obtained.  Two rule sets exist:

* :data:`ECONOMIC` - the maintained rules (P0-8b).  Dec bids carry the cost the
  system avoids (fuel units, imports) or the support the asset loses (VRE,
  run-of-river hydro), nuclear carries an extra inflexibility premium, storage
  bids at most what its stored energy is worth and never above the period's
  lowest inc price; equal prices share pro rata.
* :data:`LEGACY` - the 35aadb3 behaviour (every dec bid at GBP 0, ties broken by
  bid id).  Decision Q3 rejects the staged, zonal, DC and AC modules in the
  doctoral profile, so no profile can reach it: it is kept only as an internal
  golden rule for tests that show the defect (plan 5.3 point 7).

The down-regulation technology table is shared with the default PSM's
corrected avoided-cost stack (C15): same nuclear premium, same 0.01 GBP/MWh
rounding band and the same class order (fuel units, then storage charging,
then VRE, then nuclear).  In the down direction the order is applied at an
equal 0.01-rounded price (:func:`dec_rank`), so storage charging absorbs a
surplus before run-of-river, VRE or nuclear output is reduced even when the
storage dec price is capped at a GBP 0 inc (M6 review).  In the up direction
storage keeps coming after generation at an equal price (Q8).

R3-2 (DECISIONS A19, A22, A22a, A24-3; ``r32.network-economic-downward-order``):
the maintained rule set ``network-economic-v2`` no longer reduces a gas or
biomass unit in one block before VRE.  Its dec bid is split at minimum stable
generation (the restart table of the default PSM, R1-2): the running range
above it keeps the avoided-cost price c and so is reduced before VRE; the
shutdown segment below it is priced at the net saving a(H) = c - S(H)/(m H)
and competes with VRE on price (VRE at minus its lost support, GBP 0 without
support), after VRE at an equal 0.01 band; when the expected downtime H is
below the unit's minimum down time it is a last resort, priced below every
other dec of the period.  ``network-economic-v1`` (P0-8b) is kept unchanged,
like LEGACY, only for tests that show the previous order.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields
from typing import Mapping, Sequence

from .builtin.scheme_c_1000twh.native_corrected import (
    DOWNWARD_TABLE,
    NUCLEAR_DEC_PREMIUM_GBP_PER_MWH,
    RestartParameters,
    restart_parameters,
    restart_table,
    restart_table_sha256,
    surplus_run_after,
)

SCHEMA_VERSION = "value.network-method-rules/v1"

DEC_MULTIPLIER_PARAMETER = "market.dec_multiplier"
BID_MULTIPLIER_PARAMETER = "market.bid_multiplier"
POLICY_SUPPORT_PARAMETER = "market.policy_support_gbp_per_mwh_by_technology"
INFLEXIBLE_PREMIUM_PARAMETER = "network.inflexible_dec_premium_gbp_per_mwh_by_technology"
DEFAULT_INFLEXIBLE_PREMIUM_JSON = json.dumps(
    {"nuclear": NUCLEAR_DEC_PREMIUM_GBP_PER_MWH}, sort_keys=True, separators=(",", ":")
)

# Dec pricing classes, in the shared table's order (lower is reduced first at
# an equal rounded price).  R3-2: a gas or biomass unit's shutdown segment
# (``fuel_shutdown``) comes after VRE and before nuclear at an equal band, so a
# shutdown is preferred to curtailment only when its net saving is strictly
# above the VRE dec price after rounding (A22: "a > 0"); a shutdown below the
# minimum down time (``fuel_shutdown_last_resort``) comes last.  The P0-8b
# rule set (network-economic-v1) never emits either class and records the
# six-class order it was published with.
DEC_CLASSES = (
    "fuel",
    "import",
    "storage",
    "run_of_river",
    "vre",
    "fuel_shutdown",
    "nuclear",
    "fuel_shutdown_last_resort",
)
DEC_CLASSES_P08 = ("fuel", "import", "storage", "run_of_river", "vre", "nuclear")
DEC_PRICE_BAND_GBP_PER_MWH = 0.01

THERMAL_SHUTDOWN_NOT_MODELLED = "not_modelled"
THERMAL_SHUTDOWN_RESTART_ECONOMICS = "restart_cost_vs_avoided_cost_v1"
SHUTDOWN_HORIZON_BASIS = "declared_period_availability_vre_plus_nuclear"
DOWNWARD_RESTART_SCHEMA = "value.network-downward-restart-economics/v1"


class NetworkMethodRulesError(ValueError):
    """Network method parameters are malformed or inconsistent."""


@dataclass(frozen=True)
class NetworkMethodRules:
    rule_set_id: str
    dec_pricing: str
    tie_rule: str
    thermal_shutdown: str = THERMAL_SHUTDOWN_NOT_MODELLED

    @property
    def restart_economics(self) -> bool:
        return self.thermal_shutdown == THERMAL_SHUTDOWN_RESTART_ECONOMICS

    def definition(self) -> dict[str, object]:
        payload: dict[str, object] = {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if item.name != "thermal_shutdown"
        }
        payload["downward_table"] = dict(DOWNWARD_TABLE)
        payload["dec_tie_order"] = (
            "descending 0.01-rounded dec price, then dec class order, then exact price"
        )
        if not self.restart_economics:
            # The P0-8b definition, byte for byte (its sha is unchanged).
            payload["dec_class_order"] = list(DEC_CLASSES_P08)
            return payload
        payload["dec_class_order"] = list(DEC_CLASSES)
        payload["thermal_shutdown"] = self.thermal_shutdown
        payload["restart_table"] = {
            "table_id": str(restart_table()["table_id"]),
            "sha256": restart_table_sha256(),
        }
        payload["thermal_shutdown_rule"] = (
            "gas (CCGT, OCGT) and biomass dec bids split at min_stable_fraction x the "
            "ahead schedule: running range at the dec price c; shutdown segment at "
            "a(H) = c - S(H)/(m H) (class fuel_shutdown) when H >= min_down_time_h, "
            "otherwise class fuel_shutdown_last_resort priced 0.01 below the lowest "
            "other dec band of the period"
        )
        payload["shutdown_horizon"] = (
            "H = (1 + consecutive later periods with forecast demand <= declared VRE "
            "plus nuclear availability) x period hours"
        )
        return payload

    @property
    def sha256(self) -> str:
        payload = {"schema_version": SCHEMA_VERSION, **self.definition()}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def record(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "rule_set_id": self.rule_set_id,
            "rule_set_sha256": self.sha256,
            "rules": self.definition(),
        }


ECONOMIC = NetworkMethodRules(
    rule_set_id="network-economic-v2",
    dec_pricing="avoided_cost_or_lost_support_v1",
    tie_rule="pro_rata_v1",
    thermal_shutdown=THERMAL_SHUTDOWN_RESTART_ECONOMICS,
)

# The P0-8b rules (fuel units reduced in one block before VRE).  No module
# default reaches them since R3-2; kept for tests that show the previous order.
ECONOMIC_P08 = NetworkMethodRules(
    rule_set_id="network-economic-v1",
    dec_pricing="avoided_cost_or_lost_support_v1",
    tie_rule="pro_rata_v1",
)

LEGACY = NetworkMethodRules(
    rule_set_id="network-legacy-35aadb3",
    dec_pricing="legacy_zero_v1",
    tie_rule="bid_id_v1",
)


@dataclass(frozen=True)
class DecPricingInputs:
    dec_multiplier: float
    policy_support_gbp_per_mwh_by_technology: Mapping[str, float]
    inflexible_premium_gbp_per_mwh_by_technology: Mapping[str, float]


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise NetworkMethodRulesError(f"{label} must be a finite number")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise NetworkMethodRulesError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise NetworkMethodRulesError(f"{label} must be a finite number")
    return number


def _technology_map(raw: object, label: str) -> dict[str, float]:
    """A JSON object {technology: GBP/MWh} (string parameter or mapping)."""

    if raw is None or raw == "":
        return {}
    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NetworkMethodRulesError(f"{label} must be a JSON object") from exc
    if not isinstance(value, Mapping):
        raise NetworkMethodRulesError(f"{label} must be a JSON object")
    result: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise NetworkMethodRulesError(f"{label} keys must be technology names")
        number = _finite(item, f"{label}.{key}")
        if number < 0:
            raise NetworkMethodRulesError(f"{label}.{key} cannot be negative")
        result[key.strip().lower()] = number
    return result


def validate_technology_map_parameter(raw: object, label: str) -> dict[str, float]:
    """Public validator used by the parameter registry."""

    return _technology_map(raw, label)


def dec_pricing_inputs(parameters: Mapping[str, object]) -> DecPricingInputs:
    """Dec pricing parameters of one run (fail closed)."""

    bid_multiplier = _finite(parameters.get(BID_MULTIPLIER_PARAMETER, 1.0), BID_MULTIPLIER_PARAMETER)
    dec_multiplier = _finite(parameters.get(DEC_MULTIPLIER_PARAMETER, 1.0), DEC_MULTIPLIER_PARAMETER)
    if dec_multiplier < 0:
        raise NetworkMethodRulesError(f"{DEC_MULTIPLIER_PARAMETER} cannot be negative")
    if dec_multiplier > bid_multiplier + 1e-12:
        # A dec above the same asset's inc would let the balancer buy and sell
        # the same MWh at a profit (review P2-05).
        raise NetworkMethodRulesError(
            f"{DEC_MULTIPLIER_PARAMETER} ({dec_multiplier}) must not exceed "
            f"{BID_MULTIPLIER_PARAMETER} ({bid_multiplier})"
        )
    premium = _technology_map(
        parameters.get(INFLEXIBLE_PREMIUM_PARAMETER, DEFAULT_INFLEXIBLE_PREMIUM_JSON),
        INFLEXIBLE_PREMIUM_PARAMETER,
    )
    return DecPricingInputs(
        dec_multiplier=dec_multiplier,
        policy_support_gbp_per_mwh_by_technology=_technology_map(
            parameters.get(POLICY_SUPPORT_PARAMETER, "{}"), POLICY_SUPPORT_PARAMETER
        ),
        inflexible_premium_gbp_per_mwh_by_technology=premium,
    )


def dec_class(resource_class: str, technology: str) -> str:
    """Pricing class of a generator/import dec bid."""

    if resource_class == "import":
        return "import"
    if resource_class == "vre":
        return "vre"
    if resource_class == "hydro":
        return "run_of_river"
    if "nuclear" in str(technology).lower():
        return "nuclear"
    return "fuel"


def dec_rank(
    *,
    resource_class: str,
    technology: str = "",
    declared_dec_class: object = None,
) -> int:
    """Position of a down bid in :data:`DEC_CLASSES` (lower is reduced first).

    Storage bids rank as storage whatever else they declare; a bid's declared
    ``dec_class`` provenance wins over the derivation from its resource class;
    interconnector bids in either direction of trade (``import``, ``export``,
    ``interconnector``) rank as imports.
    """

    resource = str(resource_class or "")
    if resource == "storage":
        return DEC_CLASSES.index("storage")
    declared = str(declared_dec_class or "")
    if declared in DEC_CLASSES:
        return DEC_CLASSES.index(declared)
    if resource in {"import", "export", "interconnector"}:
        return DEC_CLASSES.index("import")
    return DEC_CLASSES.index(dec_class(resource, technology))


def bid_dec_rank(bid: object, resource_class: str | None = None) -> int:
    """:func:`dec_rank` of a :class:`FlexibilityBid`-like object."""

    provenance = getattr(bid, "provenance", None) or {}
    resource = resource_class
    if resource is None:
        resource = str(provenance.get("resource_class") or "")
    return dec_rank(
        resource_class=resource,
        technology=str(getattr(bid, "technology", "") or ""),
        declared_dec_class=provenance.get("dec_class"),
    )


def dec_price_band(price_gbp_per_mwh: float) -> float:
    """The 0.01 GBP/MWh rounding band of the shared down-regulation table."""

    return round(float(price_gbp_per_mwh), 2)


# Zonal LP (physical tie phase): weight per MWh of an accepted non-storage
# down bid, so that within one zone the LP reproduces DEC_CLASSES at an equal
# primary price.  Storage enters the same phase through its charge/discharge
# throughput at weight 1, between imports (0.5) and run-of-river (2).
PHYSICAL_DEC_WEIGHT_BY_CLASS = {
    "fuel": 0.0,
    "import": 0.5,
    "storage": 0.0,
    "run_of_river": 2.0,
    "vre": 3.0,
    "fuel_shutdown": 3.5,
    "nuclear": 4.0,
    "fuel_shutdown_last_resort": 5.0,
}


def physical_dec_weight(rank: int) -> float:
    return PHYSICAL_DEC_WEIGHT_BY_CLASS[DEC_CLASSES[rank]]


def _lookup(table: Mapping[str, float], technology: str, fallback_key: str | None = None) -> float:
    key = str(technology).strip().lower()
    if key in table:
        return float(table[key])
    if fallback_key is not None and fallback_key in table:
        return float(table[fallback_key])
    return 0.0


def resource_dec_price(
    rules: NetworkMethodRules,
    *,
    resource_class: str,
    technology: str,
    marginal_cost_gbp_per_mwh: float,
    inputs: DecPricingInputs,
    legacy_curtailment_cost_gbp_per_mwh: float = 0.0,
) -> float:
    """BM-convention dec price (higher is accepted first; cashflow -MWh x price).

    * fuel units: SRMC x m_dec - support (the avoided running cost is returned);
    * imports: period price x m_dec;
    * VRE and run-of-river hydro: -support (the support the asset loses);
    * nuclear: SRMC x m_dec - support - inflexibility premium.
    """

    if rules.dec_pricing == "legacy_zero_v1":
        return 0.0 - float(legacy_curtailment_cost_gbp_per_mwh)
    if rules.dec_pricing != "avoided_cost_or_lost_support_v1":
        raise NetworkMethodRulesError(f"Unknown dec pricing rule {rules.dec_pricing}")
    kind = dec_class(resource_class, technology)
    support = _lookup(inputs.policy_support_gbp_per_mwh_by_technology, technology)
    marginal = float(marginal_cost_gbp_per_mwh)
    if kind == "import":
        return marginal * inputs.dec_multiplier
    if kind in {"vre", "run_of_river"}:
        return 0.0 - support
    if kind == "nuclear":
        premium = _lookup(
            inputs.inflexible_premium_gbp_per_mwh_by_technology, technology, "nuclear"
        )
        return marginal * inputs.dec_multiplier - support - premium
    return marginal * inputs.dec_multiplier - support


def storage_dec_price(
    rules: NetworkMethodRules,
    *,
    up_price_gbp_per_mwh: float,
    charge_efficiency: float,
    discharge_efficiency: float,
    lowest_inc_price_gbp_per_mwh: float | None,
) -> float:
    """Storage down (charge more / discharge less) price.

    The stored MWh is worth at most its own up price after the round-trip
    losses, and never more than the cheapest inc of the period, so a storage
    dec can never be paired with an inc at a profit (down <= every up).
    """

    if rules.dec_pricing == "legacy_zero_v1":
        return 0.0
    value = float(up_price_gbp_per_mwh) * float(charge_efficiency) * float(discharge_efficiency)
    if lowest_inc_price_gbp_per_mwh is not None:
        value = min(value, float(lowest_inc_price_gbp_per_mwh))
    return min(value, float(up_price_gbp_per_mwh))


# ---------------------------------------------------------------------------
# R3-2 (A19/A22/A22a/A24-3): restart economics of gas and biomass dec bids
# ---------------------------------------------------------------------------

# Labels of the annual summary (the default PSM's R1-2 tally keys, plus the
# network-only classes).
SEGMENT_THERMAL_RUNNING = "thermal_running_range"
SEGMENT_THERMAL_SHUTDOWN_SAVING = "thermal_shutdown_net_saving"
SEGMENT_THERMAL_SHUTDOWN_AFTER_VRE = "thermal_shutdown_after_vre"
SEGMENT_THERMAL_SHUTDOWN_LAST_RESORT = "thermal_shutdown_below_min_down_time"
DOWNWARD_SEGMENTS = (
    SEGMENT_THERMAL_RUNNING,
    SEGMENT_THERMAL_SHUTDOWN_SAVING,
    SEGMENT_THERMAL_SHUTDOWN_AFTER_VRE,
    SEGMENT_THERMAL_SHUTDOWN_LAST_RESORT,
    "vre",
    "interconnector",
    "storage",
    "hydro",
    "nuclear",
    "other",
)
_CLASS_SEGMENT = {
    "import": "interconnector",
    "storage": "storage",
    "run_of_river": "hydro",
    "vre": "vre",
    "nuclear": "nuclear",
}


def restart_technology(technology: str, asset_id: str = "") -> str | None:
    """Restart-table technology of a staged fuel resource (None: no restart economics).

    Mirrors ``native_corrected.restart_technology``: a gas unit is OCGT when
    its technology or asset id names OCGT and CCGT otherwise; biomass covers
    ``bio_and_waste`` and other ``bio*`` technologies.
    """

    key = str(technology or "").strip().lower()
    name = str(asset_id or "").lower()
    if "ocgt" in key or ("ocgt" in name and ("gas" in key or "ccgt" in key)):
        return "OCGT"
    if "ccgt" in key or "gas" in key:
        return "CCGT"
    if key.startswith("bio") or "biomass" in key:
        return "biomass"
    return None


@dataclass(frozen=True)
class ThermalDecSegments:
    """The two dec segments of one gas or biomass unit in one period."""

    technology: str
    running_mwh: float
    shutdown_mwh: float
    running_price_gbp_per_mwh: float
    net_saving_gbp_per_mwh: float
    expected_downtime_h: float
    start_class: str
    restart_cost_gbp_per_mw: float
    min_stable_fraction: float
    min_down_time_h: float

    @property
    def shutdown_allowed(self) -> bool:
        return self.expected_downtime_h >= self.min_down_time_h - 1e-9

    @property
    def shutdown_class(self) -> str:
        return "fuel_shutdown" if self.shutdown_allowed else "fuel_shutdown_last_resort"

    @property
    def shutdown_segment(self) -> str:
        if not self.shutdown_allowed:
            return SEGMENT_THERMAL_SHUTDOWN_LAST_RESORT
        if self.net_saving_gbp_per_mwh > 0.0:
            return SEGMENT_THERMAL_SHUTDOWN_SAVING
        return SEGMENT_THERMAL_SHUTDOWN_AFTER_VRE


def thermal_dec_segments(
    rules: NetworkMethodRules,
    *,
    resource_class: str,
    technology: str,
    asset_id: str,
    scheduled_mwh: float,
    dec_price_gbp_per_mwh: float,
    expected_downtime_h: float,
    parameters: Mapping[str, RestartParameters] | None = None,
) -> ThermalDecSegments | None:
    """Split a fuel unit's dec at minimum stable generation (None: one block).

    Online capacity is the ahead schedule (an aggregate unit scheduled ahead is
    online and fully loaded, as in R1-2).  The running range
    ``(1 - m) x schedule`` keeps the dec price c.  The shutdown segment
    ``m x schedule`` saves a(H) = c - S(H)/(m H) per MWh (A22a): removing 1 MW
    of output at minimum stable generation shuts 1/m MW of capacity, which
    costs S/m at restart and saves c over the downtime H.
    """

    if not rules.restart_economics:
        return None
    if dec_class(resource_class, technology) != "fuel":
        return None
    restart = restart_technology(technology, asset_id)
    if restart is None:
        return None
    table = restart_parameters() if parameters is None else parameters
    params = table.get(restart)
    if params is None or not params.min_stable_fraction > 0.0:
        return None
    scheduled = max(float(scheduled_mwh), 0.0)
    horizon = float(expected_downtime_h)
    if not horizon > 0.0 or not math.isfinite(horizon):
        raise NetworkMethodRulesError("The expected downtime H must be a positive number of hours")
    shutdown = params.min_stable_fraction * scheduled
    return ThermalDecSegments(
        technology=restart,
        running_mwh=scheduled - shutdown,
        shutdown_mwh=shutdown,
        running_price_gbp_per_mwh=float(dec_price_gbp_per_mwh),
        net_saving_gbp_per_mwh=params.net_saving(float(dec_price_gbp_per_mwh), horizon),
        expected_downtime_h=horizon,
        start_class=params.start_class(horizon),
        restart_cost_gbp_per_mw=params.restart_cost(horizon),
        min_stable_fraction=params.min_stable_fraction,
        min_down_time_h=params.min_down_time_h,
    )


def last_resort_price(net_saving_gbp_per_mwh: float, other_down_prices: Sequence[float]) -> float:
    """Price of a shutdown below the minimum down time: its net saving, but at
    least one 0.01 band below every other dec of the period, so the balancer
    (copperplate order or zonal LP primary objective) takes it only when no
    other down regulation is left (A22; R1-2 deviation 6)."""

    price = float(net_saving_gbp_per_mwh)
    if other_down_prices:
        floor = min(dec_price_band(value) for value in other_down_prices)
        price = min(price, round(floor - DEC_PRICE_BAND_GBP_PER_MWH, 2))
    return price


def shutdown_horizon_hours(
    forecast_demand_mwh: Sequence[float],
    must_take_mwh: Sequence[float],
    period_hours: float,
) -> tuple[float, ...]:
    """Expected downtime H of a shutdown decided in each period (A22).

    The current period counts as one (it is being balanced down), followed by
    the consecutive later periods whose forecast demand is covered by the
    declared VRE and nuclear availability (no thermal output needed); the same
    outlook as the default PSM (R1-2), on the staged chronology.
    """

    forecast = [float(value) for value in forecast_demand_mwh]
    must_take = [float(value) for value in must_take_mwh]
    if len(forecast) != len(must_take):
        raise NetworkMethodRulesError("Forecast demand and must-take availability differ in length")
    run_after = surplus_run_after(
        demand <= available + 1e-9 for demand, available in zip(forecast, must_take)
    )
    return tuple((1 + int(value)) * float(period_hours) for value in run_after)


def dec_segment_label(bid: object) -> str:
    """Summary label of an accepted down bid."""

    provenance = getattr(bid, "provenance", None) or {}
    declared = str(provenance.get("dec_segment") or "")
    if declared:
        return declared
    resource = str(provenance.get("resource_class") or "")
    if resource == "storage":
        return "storage"
    if resource in {"export", "interconnector"}:
        return "interconnector"
    return _CLASS_SEGMENT.get(DEC_CLASSES[bid_dec_rank(bid)], "other")
