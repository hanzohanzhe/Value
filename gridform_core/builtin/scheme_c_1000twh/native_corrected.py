"""Corrected clearing helpers of the default PSM kernel (plan P0-6 S5-S10).

The retained Scheme C kernel (``runtime_compat/modular_simulation_model.py``)
calls these helpers only when its market rule set is
:data:`~.native_market_rules.CORRECTED`; the doctoral rule set never reaches
them, so the thesis behaviour stays bit-identical (Q1).  The helpers are kept
outside ``runtime_compat`` (C18) and work on the kernel's own objects:

* :class:`SurplusBook` - D1-surplus (``surplus_accounting =
  rebuilt_available_minus_accepted``): the ahead market's surplus rebuilt per
  source from availability minus acceptance.  Must-run (non-VRE) surplus is
  already inside S; VRE surplus is outside S and becomes gross VRE output when
  storage, export, flexible demand or the balancing requirement consumes it.
* :func:`downward_stack` - P3-03 (``downward_order = avoided_cost``): down
  regulation in descending avoided cost, ties by technology class then name,
  read by object identity, bounded by the ramp floor.
* :func:`merit_key` - Q8 (``ahead_merit_key``): ``(round(price, 2),
  is_storage, price)`` with a stable sort, i.e. storage after generation in
  the same 0.01 band.
* storage netting - P5-03 (``storage_position = net_per_period``): one book
  per battery and period; discharges share the rated power across stages, a
  battery that discharged buys back before it can charge, and a battery that
  charged offers no discharge in the same period.

* day-ahead imports - A16-2 (``interconnector_import_stage =
  day_ahead_offer_then_balancing_residual``, ``fx6.day-ahead-interconnector-imports``):
  :func:`import_offers` builds the day-ahead import offers of the period and
  :class:`ImportSchedule` remembers what each connection was scheduled, so
  the balancing stage offers only the remaining capacity.  An accepted import
  enters the downward stack at its avoided import price.

Decision A2: the realisation branch (forecast rule) and therefore every
hidden shortfall stay as they are; shortfalls are booked as stress events by
the ledger (P0-4 S6).  Decision Q5 (P0-6): the absorption order of the
curtailment branch (storage, export, flexible demand, down regulation) is the
thesis order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .native_realisation import BALANCING_BRANCH  # noqa: F401  (kernel reads it from here)

# Nuclear down-regulation premium of the avoided-cost stack (plan appendix
# P0-6 Q2): reducing must-run nuclear avoids its running cost but carries an
# explicit premium, so at equal rounded price it is the last resort.  The
# value is part of the corrected rule set's identity (DOWNWARD_TABLE).
NUCLEAR_DEC_PREMIUM_GBP_PER_MWH = 100.0

# Shared down-regulation technology table (C15, also read by P0-8): class rank
# at an equal rounded avoided cost.  Lower ranks are reduced first.
DOWNWARD_CLASS_RANK = {
    "thermal": 0,
    "hydro_biomass": 1,
    "vre": 2,
    "nuclear": 3,
}
DOWNWARD_TABLE = {
    "schema_version": "value.downward-technology-table/v1",
    "price_rounding_gbp_per_mwh": 0.01,
    "class_rank": dict(DOWNWARD_CLASS_RANK),
    "nuclear_dec_premium_gbp_per_mwh": NUCLEAR_DEC_PREMIUM_GBP_PER_MWH,
    "order": "descending rounded avoided cost, then class rank, then asset name",
}

TOLERANCE_MW = 1e-9

# A16-2: rank of an accepted day-ahead import at an equal rounded avoided cost.
# Kept outside DOWNWARD_TABLE (whose content is part of the P0-8 method
# identity); it follows network_method_rules.DEC_CLASSES, where an import is
# dec'd after fuel and before storage, run-of-river, VRE and nuclear.
IMPORT_DOWNWARD_CLASS_RANK = 0.5


def _kind(asset: Any) -> str:
    name = type(asset).__name__
    if name == "Connection":
        return "import"
    if name == "ExpensiverenewableGenerator":
        return "vre"
    if name == "NuclearGenerator":
        return "nuclear"
    if name in ("WaterGenerator", "BiomassGenerator"):
        return "hydro_biomass"
    return "thermal"


def is_vre(asset: Any) -> bool:
    return type(asset).__name__ == "ExpensiverenewableGenerator"


def is_storage_offer(offer: Any) -> bool:
    return isinstance(offer, list) and len(offer) == 4 and type(offer[0]).__name__ == "Battery"


def merit_key(offer: Any) -> tuple[float, int, float]:
    """Q8 ahead/balancing merit key; use with a stable sort (input order last)."""

    price = float(offer[1])
    return (round(price, 2), 1 if is_storage_offer(offer) else 0, price)


# ---------------------------------------------------------------------------
# gen_list helpers (the kernel's final composition: [asset, power_mw] rows)
# ---------------------------------------------------------------------------


def add_output(gen_list: list, asset: Any, power_mw: float) -> None:
    if power_mw <= 0:
        return
    for row in gen_list:
        if row[0] is asset:
            row[1] += power_mw
            return
    gen_list.append([asset, power_mw])


def reduce_output(gen_list: list, asset: Any, power_mw: float) -> float:
    """Take up to ``power_mw`` off the asset's rows (last row first)."""

    remaining = max(float(power_mw), 0.0)
    for row in reversed(gen_list):
        if remaining <= 0:
            break
        if row[0] is asset and row[1] > 0:
            take = min(row[1], remaining)
            row[1] -= take
            remaining -= take
    return float(power_mw) - remaining


# ---------------------------------------------------------------------------
# D1-surplus
# ---------------------------------------------------------------------------


@dataclass
class SurplusBook:
    """Per-source surplus of one period (MW), consumed non-VRE first."""

    rows: list = field(default_factory=list)  # the kernel's excess_energy_list rows
    vre_consumed_mw: dict = field(default_factory=dict)  # id(asset) -> MW
    need_spill_mw: float = 0.0

    @property
    def total_mw(self) -> float:
        return float(sum(max(float(row[1]), 0.0) for row in self.rows))

    @property
    def non_vre_remaining_mw(self) -> float:
        return float(sum(max(float(row[1]), 0.0) for row in self.rows if not is_vre(row[0])))

    def consume(self, power_mw: float, gen_list: list) -> float:
        """Route ``power_mw`` of surplus to a load; VRE taken becomes gross output."""

        remaining = max(float(power_mw), 0.0)
        for vre_pass in (False, True):
            for row in self.rows:
                if remaining <= 0:
                    break
                if is_vre(row[0]) != vre_pass or row[1] <= 0:
                    continue
                take = min(float(row[1]), remaining)
                row[1] -= take
                remaining -= take
                if vre_pass:
                    add_output(gen_list, row[0], take)
                    self.vre_consumed_mw[id(row[0])] = self.vre_consumed_mw.get(id(row[0]), 0.0) + take
        return float(power_mw) - remaining


def rebuild_surplus(excess_energy: float, excess_energy_list: list, generators: Iterable[Any],
                    accepted_bids: Iterable[Any]) -> tuple[float, list, float]:
    """D1-surplus of doctoral_market_kernel.py:898-910 for the retained kernel.

    Returns (excess, rows, unrecorded_vre_mw) where rows keep the non-VRE
    (must-run) surplus first and add every VRE's availability minus its
    acceptance; ``unrecorded_vre_mw`` is the VRE surplus the thesis rows did
    not record (the doctoral diagnostic).
    """

    non_vre_rows = [row for row in excess_energy_list if not is_vre(row[0])]
    recorded_vre = sum(float(row[1]) for row in excess_energy_list if is_vre(row[0]))
    accepted: dict[int, float] = {}
    for row in accepted_bids:
        if is_vre(row[0]):
            accepted[id(row[0])] = accepted.get(id(row[0]), 0.0) + float(row[2])
    vre_rows = []
    for source in generators:
        if is_vre(source):
            surplus = max(float(source.capacity_limit) - accepted.get(id(source), 0.0), 0.0)
            if surplus > 0:
                vre_rows.append([source, surplus])
    rows = non_vre_rows + vre_rows
    total = sum(float(row[1]) for row in rows)
    return total, rows, max(sum(float(row[1]) for row in vre_rows) - recorded_vre, 0.0)


# ---------------------------------------------------------------------------
# P3-03 avoided-cost downward stack
# ---------------------------------------------------------------------------


def avoided_cost(asset: Any) -> float:
    if _kind(asset) == "import":
        # A16-2: reducing an accepted import avoids paying its period price.
        return float(getattr(asset, "external_price", 0.0) or 0.0)
    cost = float(getattr(asset, "gen_cost", 0.0) or 0.0)
    if _kind(asset) == "nuclear":
        cost -= NUCLEAR_DEC_PREMIUM_GBP_PER_MWH
    return cost


def downward_key(asset: Any) -> tuple[float, float, str]:
    kind = _kind(asset)
    rank = IMPORT_DOWNWARD_CLASS_RANK if kind == "import" else DOWNWARD_CLASS_RANK[kind]
    return (-round(avoided_cost(asset), 2), rank, str(getattr(asset, "name", "")))


def ramp_floor_mw(asset: Any, previous_mw: float | None) -> float:
    """Lowest output the asset can reach this period (VRE: none)."""

    if _kind(asset) in ("vre", "import") or previous_mw is None:
        return 0.0
    alter = float(getattr(asset, "alter_limit", 0.0) or 0.0)
    return max(float(previous_mw) - alter, 0.0)


def downward_stack(accepted_bids: list, last_gen_energy: Iterable[Any], need_mw: float,
                   gen_list: list) -> tuple[float, list, list]:
    """Reduce accepted ahead output by ``need_mw`` in avoided-cost order.

    ``last_gen_energy`` rows are ``(asset, curtail_cost, previous_output)``
    and are matched by object identity.  Returns (remaining need, curtailment
    fees, [[asset, MW]] reductions); hydro and biomass get their reduced
    energy back into their annual budget.
    """

    previous = {id(row[0]): float(row[2]) for row in last_gen_energy}
    remaining = max(float(need_mw), 0.0)
    fees: list = []
    reductions: list = []
    for item in sorted(accepted_bids, key=lambda row: downward_key(row[0])):
        if remaining <= TOLERANCE_MW:
            break
        asset = item[0]
        floor = ramp_floor_mw(asset, previous.get(id(asset)))
        available = max(float(item[2]) - floor, 0.0)
        take = min(available, remaining)
        if take <= 0:
            continue
        item[2] = float(item[2]) - take
        if _kind(asset) != "import":
            asset.set_real_gen_energy(item[2])
        reduce_output(gen_list, asset, take)
        if _kind(asset) == "hydro_biomass":
            asset.dec_have_gen_energy(take)
        fees.append(take * float(item[3]))
        reductions.append([asset, take])
        remaining -= take
    return (remaining if remaining > TOLERANCE_MW else 0.0), fees, reductions


# ---------------------------------------------------------------------------
# A16-2 day-ahead interconnector imports
# ---------------------------------------------------------------------------


def is_import_offer(offer: Any) -> bool:
    """An import offer of the kernel: ``(connection, price, capacity_mw, 0)`` (a tuple)."""

    return isinstance(offer, tuple) and len(offer) == 4 and _kind(offer[0]) == "import"


def import_offers(connections: Iterable[Any], bidding_factor: float) -> list:
    """Day-ahead import offers of the period, in connection order.

    A connection whose transfer constraint is positive offers that many MW
    (its available import capacity in the period) at the period's
    counterparty price times the bid multiplier, the same price the
    balancing stage has always used.  A negative constraint is export
    capability and offers nothing here; a zero constraint offers nothing.
    """

    offers = []
    for connection in connections:
        capacity = float(connection.transfer_constraint)
        if capacity > 0:
            offers.append((connection, float(connection.external_price) * float(bidding_factor), capacity, 0))
    return offers


@dataclass
class ImportSchedule:
    """Day-ahead import of each connection in the current period (MW, by identity)."""

    period: int | None = None
    offers: list = field(default_factory=list)
    scheduled_mw: dict = field(default_factory=dict)

    def reset(self, period: int | None = None) -> None:
        self.period = period
        self.offers = []
        self.scheduled_mw = {}

    def schedule(self, connection: Any, power_mw: float) -> None:
        self.scheduled_mw[id(connection)] = self.scheduled_mw.get(id(connection), 0.0) + float(power_mw)

    def remaining_mw(self, connection: Any) -> float:
        """Import capacity left for the balancing stage (never below zero)."""

        return max(float(connection.transfer_constraint) - self.scheduled_mw.get(id(connection), 0.0), 0.0)


# ---------------------------------------------------------------------------
# P5-03 storage netting
# ---------------------------------------------------------------------------


@dataclass
class StoragePeriodBook:
    period: int
    draws: list = field(default_factory=list)  # [charge_period, output MW]
    charged_mw: float = 0.0
    bought_back_mw: float = 0.0

    @property
    def discharged_mw(self) -> float:
        return float(sum(max(float(draw[1]), 0.0) for draw in self.draws))


BOOK_ATTRIBUTE = "_p06_period_book"


def period_book(battery: Any, period: int) -> StoragePeriodBook:
    book = battery.__dict__.get(BOOK_ATTRIBUTE)
    if book is None or book.period != int(period):
        book = StoragePeriodBook(int(period))
        battery.__dict__[BOOK_ATTRIBUTE] = book
    return book


def remaining_discharge_power_mw(battery: Any, period: int) -> float:
    book = period_book(battery, period)
    if book.charged_mw > TOLERANCE_MW:
        return 0.0
    return max(float(battery.power_capacity_mw) - book.discharged_mw, 0.0)


def absorb(battery: Any, period: int, power_mw: float, gen_list: list) -> tuple[float, float]:
    """Netting absorption: buy back this period's discharge first, then charge.

    Returns (bought back MW, charged MW).  A battery that still discharges
    after the buy-back does not charge (no same-period charge and discharge).
    """

    power = max(float(power_mw), 0.0)
    bought = battery.buy_back(period, power)
    reduce_output(gen_list, battery, bought)
    charged = 0.0
    if power - bought > TOLERANCE_MW and period_book(battery, period).discharged_mw <= TOLERANCE_MW:
        charged = battery.charge(period, power - bought)
    return bought, charged


class StorageNettingError(RuntimeError):
    """A battery closed a period outside the three storage invariants."""


def close_battery_period(battery: Any, period: int, *, tolerance_mw: float = 1e-6) -> dict[str, float]:
    """Settle the period's net discharge and check the three invariants (S8)."""

    book = period_book(battery, period)
    discharged = book.discharged_mw
    name = getattr(battery, "name", type(battery).__name__)
    if discharged > float(battery.power_capacity_mw) + tolerance_mw:
        raise StorageNettingError(
            f"GF_STORAGE_NETTING_INVARIANT: {name} discharged {discharged:.6f} MW in period {period} "
            f"above its rated {float(battery.power_capacity_mw):.6f} MW"
        )
    if discharged > tolerance_mw and book.charged_mw > tolerance_mw:
        raise StorageNettingError(
            f"GF_STORAGE_NETTING_INVARIANT: {name} charged and discharged in period {period}"
        )
    stored = float(sum(battery.stored_energy.values()))
    if stored < -tolerance_mw or stored > float(battery.energy_capacity_mwh) + tolerance_mw:
        raise StorageNettingError(
            f"GF_STORAGE_NETTING_INVARIANT: {name} state of charge {stored:.6f} MWh outside "
            f"[0, {float(battery.energy_capacity_mwh):.6f}] in period {period}"
        )
    return {"discharged_mw": discharged, "charged_mw": book.charged_mw, "bought_back_mw": book.bought_back_mw}


# ---------------------------------------------------------------------------
# A8 uniform settlement
# ---------------------------------------------------------------------------


def uniform_income(pairs: Iterable[Any], price_gbp_per_mwh: float, period_hours: float) -> dict[str, float]:
    """Every accepted supplier (generation, storage, import) is paid one price.

    ``pairs`` are ``(asset, power_mw)``; the price is the stage's uniform
    marginal price (A8, P5-05).
    """

    income: dict[str, float] = {}
    for asset, power_mw in pairs:
        key = asset.name
        income[key] = income.get(key, 0.0) + float(power_mw) * period_hours * float(price_gbp_per_mwh)
    return income


# ---------------------------------------------------------------------------
# Corrected node terms and P5-06 physical operating cost
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrectedNodeTerms:
    """Balance terms of native_corrected_full_node_v1 (MWh): only the spill."""

    non_vre_spill_mwh: float
    phantom_surplus_mwh: float = 0.0
    u_out_mwh: float = 0.0
    non_vre_double_counted_mwh: float = 0.0

    @property
    def w_in_mwh(self) -> float:
        return self.non_vre_spill_mwh

    @property
    def in_dispatch_unrealised_mwh(self) -> float:
        return self.phantom_surplus_mwh


STARTUP_TYPES = ("GasGenerator", "BiomassGenerator", "NuclearGenerator")


def physical_cost_terms(
    dispatch_by_asset: Mapping[Any, float],
    previous_accepted: Iterable[Any],
    period_hours: float,
    *,
    storage_fee_this_period: float,
    retained_cost_gbp: float,
    generation_offer_gbp: float,
    storage_fee_retained_gbp: float,
    curtailment_fee_gbp: float,
    balancing_fee_gbp: float,
    export_revenue_gbp: float,
    import_payment_gbp: float,
) -> dict[str, float]:
    """One period's P5-06 terms (GBP; universal, plan 4.6 point 6).

    Physical: generation at the unit's own running cost (fuel, carbon and
    unit-time cost, never the bid multiplier), imports at the external price,
    and the start-up adder of thesis bids (``startup_cost`` per MWh of a gas,
    biomass or nuclear unit that was not running in the previous period).
    Settlement: the transfers of the period at their actual value; the
    storage offer payment is this period's (the thesis cost column may carry
    the last balancing period's fee).
    """

    previous = {id(asset) for asset in previous_accepted}
    hours = float(period_hours)
    generation = imports = startup = 0.0
    for asset, power_mw in dispatch_by_asset.items():
        kind = type(asset).__name__
        energy = float(power_mw) * hours
        if kind == "Battery":
            continue
        if kind == "Connection":
            imports += energy * float(getattr(asset, "external_price", 0.0) or 0.0)
            continue
        generation += energy * float(getattr(asset, "gen_cost", 0.0) or 0.0)
        if kind in STARTUP_TYPES and id(asset) not in previous:
            startup += energy * float(getattr(asset, "startup_cost", 0.0) or 0.0)
    return {
        "generation_variable_gbp": generation,
        "import_variable_gbp": imports,
        "startup_adder_gbp": startup,
        "storage_offer_payment_gbp": float(storage_fee_this_period) * hours,
        "retained_period_cost_gbp": float(retained_cost_gbp),
        "generation_offer_payment_gbp": float(generation_offer_gbp),
        "storage_fee_retained_gbp": float(storage_fee_retained_gbp),
        "curtailment_payment_gbp": float(curtailment_fee_gbp),
        "balancing_payment_gbp": float(balancing_fee_gbp),
        "export_revenue_gbp": float(export_revenue_gbp),
        "import_payment_gbp": float(import_payment_gbp),
    }
