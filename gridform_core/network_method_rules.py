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
then VRE, then nuclear).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields
from typing import Mapping

from .builtin.scheme_c_1000twh.native_corrected import (
    DOWNWARD_TABLE,
    NUCLEAR_DEC_PREMIUM_GBP_PER_MWH,
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
# an equal rounded price).
DEC_CLASSES = ("fuel", "import", "storage", "run_of_river", "vre", "nuclear")


class NetworkMethodRulesError(ValueError):
    """Network method parameters are malformed or inconsistent."""


@dataclass(frozen=True)
class NetworkMethodRules:
    rule_set_id: str
    dec_pricing: str
    tie_rule: str

    def definition(self) -> dict[str, object]:
        payload: dict[str, object] = {item.name: getattr(self, item.name) for item in fields(self)}
        payload["downward_table"] = dict(DOWNWARD_TABLE)
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
