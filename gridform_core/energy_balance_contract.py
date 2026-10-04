"""Per-period energy-balance identities for VALUE market ledgers (P0-4 S1).

This leaf module depends only on :mod:`math` and the standard library typing
helpers.  It is the single implementation of the period energy identities
(integration hotspot C19): kernels, ledgers, the read-only oracle
(:mod:`gridform_core.energy_balance_oracle`) and later run-level invariants
must call it instead of re-deriving a balance.

Symbols (all MWh in one period, as recorded in ``period_summary``)::

    S  accepted_supply_mwh     final dispatch incl. imports and storage discharge
    B  blackout_mwh            recorded unserved energy
    D  real_demand_mwh
    C  storage_charge_mwh      total storage input
    E  export_mwh
    X  flexible_demand_mwh     electrolyser / flexible load
    XS excess_mwh              pre-balancing excess still unused at the end
    K  curtailed_mwh           balancing-stage curtailment (down-regulation)
    F  forecast_demand_mwh
    U_out  out-of-dispatch surplus (VRE availability not accepted) that was
           routed to storage, export or flexible load
    W_in   in-dispatch surplus (must-run output already inside S, e.g.
           nuclear) that was finally spilled (``non_vre_spill``, decision Q7)

Boundaries (``BOUNDARIES``):

* ``full_node_v1``:  r = S + B - D - C - E - X   (staged and perfect-foresight)
* ``default_psm_surplus_node_v1``:  r = S + B + U_out - W_in - D - C - E - X,
  with per-source surplus conservation (doctoral default PSM, decision Q7).
  U_out and W_in come from the optional ``surplus_routing`` ledger table that
  P0-4 S5 adds; without it the boundary cannot be evaluated exactly.
* ``retained_demand_serving_v1``: r = S + B - D - min(C, max(F - D, 0)); the
  boundary the HEAD kernel uses for ``raw_energy_balance_residual_mwh``.  It is
  a diagnostic decomposition only and never a verdict basis.

Necessary envelope (any ledger of the surplus-node family): because
0 <= U_out <= C + E + X and 0 <= W_in <= XS + K (in-dispatch output can only
be spilled as unused excess or as balancing-stage curtailment; the default
PSM keeps curtailed must-run output inside S, so K belongs to the bound), a
physically closing period has

    -(C + E + X) - tol  <=  full_node_residual  <=  XS + K + tol .

Ledgers without the routing table can only be checked against this envelope;
they can fail it but can never pass on it.

Stress events (decision A2, both profiles): the period shortfall is the
demand plus the boundary's loads that accepted supply did not meet,
``shortfall = max(0, D + C + E + X - U_out + W_in - S)``; recorded blackout B
is part of it, the remainder is hidden shortfall.  Without routing data the
shortfall is bracketed by ``max(0, D - S)`` and
``max(0, D + C + E + X + min(XS + K, S) - S)`` (W_in is part of S, so it can
never exceed S).  Contiguous stress periods inside one year form one stress
event.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

CONTRACT_VERSION = "value.energy-balance-contract/v1"

FULL_NODE_V1 = "full_node_v1"
DEFAULT_PSM_SURPLUS_NODE_V1 = "default_psm_surplus_node_v1"
RETAINED_DEMAND_SERVING_V1 = "retained_demand_serving_v1"
UNKNOWN_BOUNDARY = "unknown"

EXACT_ARITHMETIC = "exact_arithmetic"
LP_SOLVER = "lp_solver"

# Plan 4.4 point 1 / appendix P0-4 Q1, Q9 (to be confirmed on validation_168h).
TOLERANCE_TIERS: dict[str, dict[str, float]] = {
    EXACT_ARITHMETIC: {"absolute_mwh": 1e-6, "relative": 1e-9},
    LP_SOLVER: {"absolute_mwh": 1e-5, "relative": 1e-7},
}
ANNUAL_ADJUSTMENT_SHARE_CAP = 1e-6

# Ledger metadata keys a kernel uses to declare its boundary (written from
# P0-4 S6 on).  Values are JSON strings like every other metadata value.
METADATA_BOUNDARY_KEY = "energy_balance_boundary"
METADATA_RULE_SET_KEY = "energy_balance_rule_set"

# Optional surplus routing table (P0-4 S5).  One row per (year, period,
# source_class); source_class is ``in_dispatch`` (surplus already inside S)
# or ``out_of_dispatch`` (available VRE not accepted into S).
SURPLUS_ROUTING_TABLE = "surplus_routing"
SURPLUS_SOURCE_CLASSES = ("in_dispatch", "out_of_dispatch")
SURPLUS_ROUTING_COLUMNS = (
    "year", "period", "source_class", "available_mwh", "to_storage_mwh",
    "to_export_mwh", "to_flexible_mwh", "spilled_mwh",
)

PERIOD_COLUMNS = (
    "year", "period", "stage", "forecast_demand_mwh", "real_demand_mwh",
    "accepted_supply_mwh", "storage_charge_mwh", "flexible_demand_mwh",
    "export_mwh", "blackout_mwh", "excess_mwh", "curtailed_mwh", "energy_balance_residual_mwh",
    "compatibility_adjustment_mwh", "raw_energy_balance_residual_mwh",
)


@dataclass(frozen=True)
class Boundary:
    boundary_id: str
    formula: str
    requires_surplus_routing: bool
    verdict_basis: bool
    description: str


BOUNDARIES: dict[str, Boundary] = {
    FULL_NODE_V1: Boundary(
        FULL_NODE_V1, "S + B - D - C - E - X", False, True,
        "every recorded load is served by recorded supply (staged, perfect foresight)",
    ),
    DEFAULT_PSM_SURPLUS_NODE_V1: Boundary(
        DEFAULT_PSM_SURPLUS_NODE_V1, "S + B + U_out - W_in - D - C - E - X", True, True,
        "source-classified node of the default PSM (decision Q7)",
    ),
    RETAINED_DEMAND_SERVING_V1: Boundary(
        RETAINED_DEMAND_SERVING_V1, "S + B - D - min(C, max(F - D, 0))", False, False,
        "HEAD kernel raw residual boundary; diagnostic decomposition only",
    ),
}


@dataclass(frozen=True)
class RegistryEntry:
    module_id: str
    minimum_version: str
    maximum_version_exclusive: str | None
    rule_sets: tuple[str | None, ...]
    boundary_id: str
    tolerance_tier: str
    note: str
    # Boundary of the writer's own ``raw_energy_balance_residual_mwh`` column
    # in ledgers that declare nothing (None: not known, not cross-checked).
    legacy_raw_basis: str | None = None


# Key (module_id, version interval, rule_set) -> boundary (C19).  ``None`` in
# rule_sets matches ledgers that record no rule set (everything before X0 S8).
# Later packages append entries (P0-6: native_corrected_full_node_v1).
BOUNDARY_REGISTRY: tuple[RegistryEntry, ...] = (
    RegistryEntry(
        "value-bid-at-cost-psm", "0", "6.0.0", (None, "doctoral-lineage-0.6.0a2"),
        DEFAULT_PSM_SURPLUS_NODE_V1, EXACT_ARITHMETIC,
        "retained Scheme C kernel; pre-balancing surplus is routed outside S",
        RETAINED_DEMAND_SERVING_V1,
    ),
    RegistryEntry(
        "value-perfect-foresight-lp", "0", None, (None,),
        FULL_NODE_V1, LP_SOLVER, "LP co-optimisation; excess is unused VRE",
    ),
    RegistryEntry(
        "value-staged-bid-at-cost-psm", "0", None, (None,),
        FULL_NODE_V1, LP_SOLVER, "staged ahead/balancing LP",
    ),
    RegistryEntry(
        "value-reference-dc-network", "0", None, (None,),
        FULL_NODE_V1, LP_SOLVER, "DC network LP",
    ),
)


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in str(version).split("."):
        digits = ""
        for character in token:
            if not character.isdigit():
                break
            digits += character
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def registry_lookup(module_id: str | None, version: str | None, rule_set: str | None) -> RegistryEntry | None:
    if not module_id:
        return None
    for entry in BOUNDARY_REGISTRY:
        if entry.module_id != module_id or rule_set not in entry.rule_sets:
            continue
        if version is None:
            continue
        key = _version_key(version)
        if key < _version_key(entry.minimum_version):
            continue
        if entry.maximum_version_exclusive is not None and key >= _version_key(entry.maximum_version_exclusive):
            continue
        return entry
    return None


def tolerance(tier: str, *magnitudes: float) -> float:
    """Absolute tolerance for one period: max(abs, rel * max(|m|..., 1))."""

    values = TOLERANCE_TIERS[tier]
    scale = max([abs(float(value)) for value in magnitudes] + [1.0])
    return max(values["absolute_mwh"], values["relative"] * scale)


@dataclass(frozen=True)
class PeriodFlows:
    year: int
    period: int
    supply_mwh: float
    blackout_mwh: float
    demand_mwh: float
    storage_charge_mwh: float
    export_mwh: float
    flexible_demand_mwh: float
    excess_mwh: float = 0.0
    curtailed_mwh: float = 0.0
    forecast_demand_mwh: float | None = None
    u_out_mwh: float | None = None
    w_in_mwh: float | None = None
    reported_raw_residual_mwh: float | None = None
    reported_adjustment_mwh: float | None = None
    reported_residual_mwh: float | None = None
    stage: str = ""

    @property
    def loads_mwh(self) -> float:
        return self.storage_charge_mwh + self.export_mwh + self.flexible_demand_mwh

    @property
    def spill_capacity_mwh(self) -> float:
        """Envelope bound on W_in: unused excess plus balancing-stage curtailment."""

        return max(self.excess_mwh, 0.0) + max(self.curtailed_mwh, 0.0)

    @property
    def in_dispatch_spill_bound_mwh(self) -> float:
        """Tightest bound on W_in from the ledger alone: W_in is inside S."""

        return min(self.spill_capacity_mwh, max(self.supply_mwh, 0.0))

    def values(self) -> tuple[float, ...]:
        return tuple(
            value for value in (
                self.supply_mwh, self.blackout_mwh, self.demand_mwh, self.storage_charge_mwh,
                self.export_mwh, self.flexible_demand_mwh, self.excess_mwh, self.curtailed_mwh,
                self.forecast_demand_mwh,
                self.u_out_mwh, self.w_in_mwh, self.reported_raw_residual_mwh,
                self.reported_adjustment_mwh, self.reported_residual_mwh,
            ) if value is not None
        )

    def is_finite(self) -> bool:
        return all(math.isfinite(float(value)) for value in self.values())


def full_node_residual(flows: PeriodFlows) -> float:
    return (
        flows.supply_mwh + flows.blackout_mwh - flows.demand_mwh
        - flows.storage_charge_mwh - flows.export_mwh - flows.flexible_demand_mwh
    )


def surplus_node_residual(flows: PeriodFlows) -> float:
    if flows.u_out_mwh is None or flows.w_in_mwh is None:
        raise ValueError("default_psm_surplus_node_v1 needs U_out and W_in (surplus_routing)")
    return full_node_residual(flows) + flows.u_out_mwh - flows.w_in_mwh


def retained_residual(flows: PeriodFlows) -> float:
    if flows.forecast_demand_mwh is None:
        raise ValueError("retained_demand_serving_v1 needs the forecast demand")
    accounted_charge = min(
        flows.storage_charge_mwh,
        max(flows.forecast_demand_mwh - flows.demand_mwh, 0.0),
    )
    return flows.supply_mwh + flows.blackout_mwh - flows.demand_mwh - accounted_charge


def boundary_residual(boundary_id: str, flows: PeriodFlows) -> float:
    if boundary_id == FULL_NODE_V1:
        return full_node_residual(flows)
    if boundary_id == DEFAULT_PSM_SURPLUS_NODE_V1:
        return surplus_node_residual(flows)
    if boundary_id == RETAINED_DEMAND_SERVING_V1:
        return retained_residual(flows)
    raise KeyError(f"unknown energy-balance boundary {boundary_id!r}")


def envelope_bounds(boundary_id: str, flows: PeriodFlows) -> tuple[float, float]:
    """Bounds on the full-node residual that any closing period must respect.

    For the surplus-node family (and for an unknown boundary, which gets the
    widest envelope) the bounds are [-(C+E+X), XS+K]; for full_node_v1 the
    full-node residual itself must vanish.
    """

    if boundary_id == FULL_NODE_V1:
        return (0.0, 0.0)
    return (-flows.loads_mwh, flows.spill_capacity_mwh)


@dataclass(frozen=True)
class EnvelopeResult:
    full_node_residual_mwh: float
    lower_mwh: float
    upper_mwh: float
    tolerance_mwh: float
    lower_violation_mwh: float
    upper_violation_mwh: float

    @property
    def violated(self) -> bool:
        return self.lower_violation_mwh > 0.0 or self.upper_violation_mwh > 0.0


def check_envelope(boundary_id: str, flows: PeriodFlows, tier: str) -> EnvelopeResult:
    residual = full_node_residual(flows)
    lower, upper = envelope_bounds(boundary_id, flows)
    tol = tolerance(tier, flows.demand_mwh, flows.supply_mwh)
    lower_violation = (lower - tol) - residual
    upper_violation = residual - (upper + tol)
    return EnvelopeResult(
        residual, lower, upper, tol,
        # The violation is measured against the bound itself (not bound - tol)
        # so a hand calculation reads directly: -18.829 vs -5.0 -> 13.829.
        (lower - residual) if lower_violation > 0.0 else 0.0,
        (residual - upper) if upper_violation > 0.0 else 0.0,
    )


@dataclass(frozen=True)
class SurplusRoutingRow:
    year: int
    period: int
    source_class: str
    available_mwh: float
    to_storage_mwh: float
    to_export_mwh: float
    to_flexible_mwh: float
    spilled_mwh: float

    @property
    def routed_mwh(self) -> float:
        return self.to_storage_mwh + self.to_export_mwh + self.to_flexible_mwh

    def conservation_gap_mwh(self) -> float:
        return self.available_mwh - self.routed_mwh - self.spilled_mwh


def surplus_terms(rows: Iterable[SurplusRoutingRow]) -> tuple[float, float]:
    """(U_out, W_in) for one period from its routing rows."""

    u_out = 0.0
    w_in = 0.0
    for row in rows:
        if row.source_class == "out_of_dispatch":
            u_out += row.routed_mwh
        elif row.source_class == "in_dispatch":
            w_in += row.spilled_mwh
        else:
            raise ValueError(f"unknown surplus source class {row.source_class!r}")
    return u_out, w_in


# ---------------------------------------------------------------------------
# Stress events (decision A2)


@dataclass(frozen=True)
class ShortfallEstimate:
    """Period shortfall; exact when lower == upper (routing data present)."""

    year: int
    period: int
    lower_mwh: float
    upper_mwh: float
    recorded_unserved_mwh: float
    exact: bool

    @property
    def shortfall_mwh(self) -> float | None:
        return self.lower_mwh if self.exact else None

    @property
    def hidden_lower_mwh(self) -> float:
        return max(self.lower_mwh - self.recorded_unserved_mwh, 0.0)


def period_shortfall(flows: PeriodFlows) -> ShortfallEstimate:
    if flows.u_out_mwh is not None and flows.w_in_mwh is not None:
        value = max(
            flows.demand_mwh + flows.loads_mwh - flows.u_out_mwh + flows.w_in_mwh - flows.supply_mwh,
            0.0,
        )
        return ShortfallEstimate(flows.year, flows.period, value, value, flows.blackout_mwh, True)
    lower = max(flows.demand_mwh - flows.supply_mwh, 0.0)
    upper = max(flows.demand_mwh + flows.loads_mwh + flows.in_dispatch_spill_bound_mwh - flows.supply_mwh, 0.0)
    return ShortfallEstimate(flows.year, flows.period, lower, upper, flows.blackout_mwh, False)


def full_node_shortfall(flows: PeriodFlows) -> float:
    """Shortfall when every recorded load must be met by S (full_node_v1)."""

    return max(flows.demand_mwh + flows.loads_mwh - flows.supply_mwh, 0.0)


@dataclass
class StressEvent:
    year: int
    first_period: int
    last_period: int
    periods: int = 0
    shortfall_lower_mwh: float = 0.0
    shortfall_upper_mwh: float = 0.0
    recorded_unserved_mwh: float = 0.0


@dataclass
class StressSummary:
    basis: str
    periods_evaluated: int = 0
    stress_periods: int = 0
    possible_stress_periods: int = 0
    events: list[StressEvent] = field(default_factory=list)
    by_year: dict[int, dict[str, float]] = field(default_factory=dict)


def stress_events(
    estimates: Sequence[ShortfallEstimate],
    *,
    tier: str = EXACT_ARITHMETIC,
    scale: Mapping[tuple[int, int], float] | None = None,
) -> StressSummary:
    """Group stress periods into contiguous events per year.

    A period is a (certain) stress period when its lower shortfall bound
    exceeds the tolerance, and a possible stress period when only the upper
    bound does.  Events are built from certain stress periods; for exact
    estimates the two coincide.
    """

    exact = bool(estimates) and all(item.exact for item in estimates)
    summary = StressSummary("exact" if exact else "bounds")
    current: StressEvent | None = None
    previous: tuple[int, int] | None = None
    for item in sorted(estimates, key=lambda value: (value.year, value.period)):
        summary.periods_evaluated += 1
        tol = tolerance(tier, (scale or {}).get((item.year, item.period), 0.0))
        year = summary.by_year.setdefault(item.year, {
            "stress_periods": 0, "possible_stress_periods": 0, "event_count": 0,
            "shortfall_lower_mwh": 0.0, "shortfall_upper_mwh": 0.0,
            "recorded_unserved_mwh": 0.0, "hidden_shortfall_lower_mwh": 0.0,
        })
        year["recorded_unserved_mwh"] += item.recorded_unserved_mwh
        certain = item.lower_mwh > tol
        possible = item.upper_mwh > tol
        if possible:
            summary.possible_stress_periods += 1
            year["possible_stress_periods"] += 1
            year["shortfall_upper_mwh"] += item.upper_mwh
        if certain:
            summary.stress_periods += 1
            year["stress_periods"] += 1
            year["shortfall_lower_mwh"] += item.lower_mwh
            year["hidden_shortfall_lower_mwh"] += item.hidden_lower_mwh
            contiguous = (
                current is not None and previous is not None
                and previous == (item.year, item.period - 1)
            )
            if not contiguous:
                current = StressEvent(item.year, item.period, item.period)
                summary.events.append(current)
                year["event_count"] += 1
            assert current is not None
            current.last_period = item.period
            current.periods += 1
            current.shortfall_lower_mwh += item.lower_mwh
            current.shortfall_upper_mwh += item.upper_mwh
            current.recorded_unserved_mwh += item.recorded_unserved_mwh
            previous = (item.year, item.period)
        else:
            current = None
            previous = None
    return summary
