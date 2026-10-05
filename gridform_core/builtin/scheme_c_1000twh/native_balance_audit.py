"""Observation-only energy audit of the default PSM kernel (plan P0-4 S4-S5).

The retained kernel (``runtime_compat/modular_simulation_model.py``) keeps its
dispatch, prices and state trajectory exactly; these helpers only *read*
quantities around the points where the kernel already moves energy, so that
the market ledger can book them.  Nothing here feeds back into clearing.

* :class:`StorageEnergyAudit` - per battery and period: state of charge at the
  start, grid-side charge input and its stored share, grid-side discharge
  output and the stored energy it withdrew, self-discharge (``decay_func``),
  tail write-off (``clr_stored_energy_var`` / ``cleanup_negligible_energy``
  delete tranches below 0.001 MWh) and any other change (capacity rescaling).
  The identity ``soc_end = soc_start + stored - withdrawn - self_discharge -
  tail_writeoff - other`` closes by construction up to rounding; the residual
  is recorded (P3-14, P5-11).
* :class:`SurplusTrace` - per period, the pre-balancing surplus by source
  class (decision Q7): ``in_dispatch`` surplus is output already inside the
  accepted supply S (must-run nuclear excess, and the forecast-minus-real
  surplus of the scheduled output in the curtailment branch);
  ``out_of_dispatch`` surplus is VRE availability that the ahead market did
  not accept.  Each take point (storage, export, flexible demand, re-dispatch
  to demand in the balancing branch, down-regulation) adds the difference of
  the kernel's own ``excess_energy`` / ``need_curtailed_energy`` before and
  after the take.  The surplus-node boundary uses ``U_out`` (out-of-dispatch
  surplus routed to storage, export or flexible demand) and ``W_in`` (the
  in-dispatch surplus that was spilled, reported as ``non_vre_spill``).

Units: the kernel works in MW held over a period; the audit converts to MWh
with the physical period length when it builds ledger rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

IN_DISPATCH = "in_dispatch"
OUT_OF_DISPATCH = "out_of_dispatch"
ROUTING_KEYS = (
    "available", "to_storage", "to_export", "to_flexible", "to_dispatch",
    "curtailed", "claimed_spill",
)


# ---------------------------------------------------------------------------
# Storage energy audit (S4)


@dataclass
class StorageEnergyAudit:
    """Per-battery accumulators of one period (stored-side MWh unless noted)."""

    period: int | None = None
    soc_start_mwh: float = 0.0
    charge_input_mwh: float = 0.0       # grid side
    charge_stored_mwh: float = 0.0
    discharge_output_mwh: float = 0.0   # grid side
    discharge_withdrawn_mwh: float = 0.0
    self_discharge_mwh: float = 0.0
    tail_writeoff_mwh: float = 0.0
    opened: bool = False

    def open(self, period: int, soc_start_mwh: float) -> None:
        self.period = int(period)
        self.soc_start_mwh = float(soc_start_mwh)
        self.charge_input_mwh = 0.0
        self.charge_stored_mwh = 0.0
        self.discharge_output_mwh = 0.0
        self.discharge_withdrawn_mwh = 0.0
        self.self_discharge_mwh = 0.0
        self.tail_writeoff_mwh = 0.0
        self.opened = True

    def row_values(self, soc_end_mwh: float) -> dict[str, float]:
        soc_end = float(soc_end_mwh)
        explained = (
            self.soc_start_mwh + self.charge_stored_mwh - self.discharge_withdrawn_mwh
            - self.self_discharge_mwh - self.tail_writeoff_mwh
        )
        return {
            "soc_start_mwh": self.soc_start_mwh,
            "charge_input_mwh": self.charge_input_mwh,
            "charge_stored_mwh": self.charge_stored_mwh,
            "discharge_output_mwh": self.discharge_output_mwh,
            "discharge_withdrawn_mwh": self.discharge_withdrawn_mwh,
            "self_discharge_mwh": self.self_discharge_mwh,
            "tail_writeoff_mwh": self.tail_writeoff_mwh,
            "soc_end_mwh": soc_end,
            "identity_residual_mwh": explained - soc_end,
        }


AUDIT_ATTRIBUTE = "_value_energy_audit"


def battery_audit(battery: object) -> StorageEnergyAudit:
    """The battery's audit, created lazily.

    Works for objects built with ``Battery.__new__`` (module conformance
    builds them without ``__init__``) because nothing is required at
    construction time.
    """

    state = getattr(battery, "__dict__", None)
    if state is None:  # pragma: no cover - kernel batteries are plain objects
        return StorageEnergyAudit()
    audit = state.get(AUDIT_ATTRIBUTE)
    if audit is None:
        audit = StorageEnergyAudit()
        state[AUDIT_ATTRIBUTE] = audit
    return audit


def stored_total(battery: object) -> float:
    return float(sum(getattr(battery, "stored_energy", {}).values()))


# ---------------------------------------------------------------------------
# Surplus routing trace (S5)


def _routing() -> dict[str, float]:
    return {key: 0.0 for key in ROUTING_KEYS}


@dataclass
class SurplusTrace:
    """Surplus routing of the current period, in kernel MW."""

    period: int | None = None
    excess_class: str | None = None
    excess_sources: tuple[str, ...] = ()
    routing: dict[str, dict[str, float]] = field(default_factory=lambda: {
        IN_DISPATCH: _routing(), OUT_OF_DISPATCH: _routing(),
    })
    double_counted_mw: float = 0.0

    def begin(self, period: int, excess_mw: float, excess_class: str | None, sources: tuple[str, ...] = ()) -> None:
        self.period = int(period)
        self.excess_class = excess_class
        self.excess_sources = tuple(sources)
        self.routing = {IN_DISPATCH: _routing(), OUT_OF_DISPATCH: _routing()}
        self.double_counted_mw = 0.0
        if excess_class is not None and excess_mw:
            self.routing[excess_class]["available"] += float(excess_mw)

    def add(self, source_class: str | None, key: str, mw: float) -> None:
        if source_class is None or not mw:
            return
        self.routing[source_class][key] += float(mw)

    def excess(self, key: str, before_mw: float, after_mw: float) -> None:
        """A take from the kernel's ``excess_energy`` (difference before/after)."""

        self.add(self.excess_class, key, float(before_mw) - float(after_mw))

    def need(self, key: str, before_mw: float, after_mw: float) -> None:
        """A take from the curtailment branch's ``need_curtailed_energy`` (in dispatch)."""

        self.add(IN_DISPATCH, key, float(before_mw) - float(after_mw))


def excess_source_class(excess_energy_list, nuclear_type, vre_type) -> tuple[str | None, tuple[str, ...]]:
    """Source class of the ahead market's excess.

    The retained ahead market stops at its marginal offer, so the excess has
    one source: a must-run nuclear unit (inside S) or VRE availability that
    was not accepted (outside S).  Returns (class, distinct source kinds).
    """

    kinds = []
    for item in excess_energy_list or ():
        asset = item[0]
        if type(asset) is nuclear_type:
            kind = IN_DISPATCH
        elif type(asset) is vre_type:
            kind = OUT_OF_DISPATCH
        else:
            kind = "unclassified"
        if kind not in kinds:
            kinds.append(kind)
    if not kinds:
        return None, ()
    first = kinds[0]
    return (first if first in (IN_DISPATCH, OUT_OF_DISPATCH) else None), tuple(kinds)


@dataclass(frozen=True)
class PeriodSurplusTerms:
    """Node terms of one period, MWh."""

    u_out_mwh: float
    w_in_mwh: float
    in_dispatch_claimed_spill_mwh: float
    in_dispatch_unrealised_mwh: float
    non_vre_double_counted_mwh: float


def node_terms(
    trace: SurplusTrace,
    period_hours: float,
    *,
    supply_mwh: float,
    blackout_mwh: float,
    demand_mwh: float,
    loads_mwh: float,
) -> tuple[PeriodSurplusTerms, list[dict[str, float | str]]]:
    """U_out, W_in and the routing rows of one period (MWh).

    The in-dispatch spill the kernel *claims* is the excess it left unused
    plus the down-regulation it booked but did not take out of S.  Only
    energy that is physically in S and not used by the node can be spilled,
    so W_in is that claim capped at ``max(0, S + B + U_out - D - loads)``;
    the rest of the claim is recorded as ``unrealised`` surplus (the kernel
    routed a surplus that the accepted supply never contained, P3-01).  The
    cap can only lower W_in, so a shortfall or a double count (a positive
    residual) always stays visible in the boundary residual.
    """

    hours = float(period_hours)
    routing = trace.routing
    out_row = routing[OUT_OF_DISPATCH]
    in_row = routing[IN_DISPATCH]
    u_out = (out_row["to_storage"] + out_row["to_export"] + out_row["to_flexible"]) * hours
    claimed = max(in_row["claimed_spill"], 0.0) * hours
    unused = max(supply_mwh + blackout_mwh + u_out - demand_mwh - loads_mwh, 0.0)
    w_in = min(claimed, unused)
    rows: list[dict[str, float | str]] = []
    for source_class, values in ((IN_DISPATCH, in_row), (OUT_OF_DISPATCH, out_row)):
        if not any(values[key] for key in ROUTING_KEYS):
            continue
        if source_class == IN_DISPATCH:
            spilled, unrealised = w_in, claimed - w_in
        else:
            spilled, unrealised = max(values["claimed_spill"], 0.0) * hours, 0.0
        rows.append({
            "source_class": source_class,
            "available_mwh": values["available"] * hours,
            "to_storage_mwh": values["to_storage"] * hours,
            "to_export_mwh": values["to_export"] * hours,
            "to_flexible_mwh": values["to_flexible"] * hours,
            "spilled_mwh": spilled,
            "to_dispatch_mwh": values["to_dispatch"] * hours,
            "curtailed_mwh": values["curtailed"] * hours,
            "unrealised_mwh": unrealised,
        })
    terms = PeriodSurplusTerms(
        u_out_mwh=u_out,
        w_in_mwh=w_in,
        in_dispatch_claimed_spill_mwh=claimed,
        in_dispatch_unrealised_mwh=claimed - w_in,
        non_vre_double_counted_mwh=in_row["to_dispatch"] * hours,
    )
    return terms, rows


def open_storage_period(batteries, period: int) -> None:
    """Start the audit period of every battery at its current state of charge."""

    for battery in batteries:
        battery_audit(battery).open(period, stored_total(battery))


def storage_audit_rows(year: int, period: int, batteries) -> list:
    """StorageEnergyAuditRow per battery for the period just cleared."""

    from ...market_ledger import StorageEnergyAuditRow

    rows = []
    for battery in batteries:
        audit = battery_audit(battery)
        if not audit.opened or audit.period != int(period):
            # A battery the loop did not open (custom caller): its start state
            # is unknown, so its whole state counts as the opening state.
            audit.open(period, stored_total(battery))
        rows.append(StorageEnergyAuditRow(
            int(year), int(period), str(getattr(battery, "name", battery.__class__.__name__)),
            **audit.row_values(stored_total(battery)),
        ))
    return rows
