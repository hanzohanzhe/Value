"""Observation-only record of the default PSM's storage offers (four-role M-D1).

The retained kernel (``runtime_compat/modular_simulation_model.py``) builds
one discharge offer per stored charge tranche (``storage_discharge_offers``)
in the ahead stage and, in balancing periods, again in the balancing stage.
The ``orders`` table of the market ledger only books generator offers; a
battery that discharged appears there as one ``final_dispatch`` row with
reason ``accepted_non_generator_offer``, offer price 0.0 and offered =
accepted, and a storage offer that was not accepted does not appear at all.
Those rows are frozen in the doctoral trajectory zone (decision Q12), so the
real offers are booked in a separate accounting table, ``storage_orders``.

:class:`StorageOfferTrace` only *reads*: the kernel declares each stage's
offer list just before it sorts it (the same list and enumeration index the
clearing declaration uses for ``offer_id``), and reports the power each offer
delivered right after ``Battery.discharge``.  The trace never changes an
offer, the merit order or a discharge, so dispatch, prices and state of
charge are bit-identical (doctoral trajectory frozen).

Units: the kernel works in MW held over a period; :meth:`rows` converts to
MWh with the physical period length.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

AHEAD = "ahead"
BALANCING = "balancing"
STAGE_LABELS = {AHEAD: "ahead_offer", BALANCING: "balancing_offer"}

# status / reason codes of storage_orders (documented in
# gridform_core/data/contracts/market-ledger-storage-orders-v1.schema.sql).
CLEARED = "cleared"
DEMAND_FILLED = "demand_filled"
NO_ENERGY_DELIVERED = "no_energy_delivered"
MERIT_ORDER_NOT_REACHED = "merit_order_not_reached"
_EPSILON_MW = 1e-12


def is_storage_offer(item: Any) -> bool:
    """A storage tranche offer of the retained kernel: ``[battery, price, charge_period, power]``.

    Generator offers are five-element lists and import offers are tuples.
    """

    return type(item) is list and len(item) == 4


@dataclass
class _Offer:
    stage: str
    offer_index: int
    item: list                  # kept alive for the period so id() stays unique
    asset_id: str
    asset_type: str
    charge_period: int
    dwell_periods: int
    price_gbp_per_mwh: float
    offered_power_mw: float
    bidding_factor: float
    delivered_power_mw: float = 0.0
    visited: bool = False


@dataclass
class StorageOfferTrace:
    """Storage offers of the current period and the power each one delivered."""

    period: int | None = None
    offers: list[_Offer] = field(default_factory=list)
    _by_item: dict[int, _Offer] = field(default_factory=dict)

    def reset(self, period: int | None = None) -> None:
        self.period = period
        self.offers = []
        self._by_item = {}

    def declare(
        self,
        stage: str,
        period: int,
        offer_list: Iterable[Any],
        *,
        bidding_factor: float,
        asset_name: Callable[[Any], str],
    ) -> None:
        """Record every storage offer of ``offer_list`` (before it is sorted).

        The ahead stage opens the period; a declaration for another period
        also starts afresh, so callers that never build ledger rows (the
        frozen HEAD loop of the reproduction harness) do not accumulate.
        """

        if stage == AHEAD or self.period != int(period):
            self.reset(int(period))
        for index, item in enumerate(offer_list):
            if not is_storage_offer(item):
                continue
            asset = item[0]
            offer = _Offer(
                stage=stage,
                offer_index=index,
                item=item,
                asset_id=str(asset_name(asset)),
                asset_type=asset.__class__.__name__,
                charge_period=int(item[2]),
                dwell_periods=int(period) - int(item[2]),
                price_gbp_per_mwh=float(item[1]),
                offered_power_mw=max(float(item[3]), 0.0),
                bidding_factor=float(bidding_factor),
            )
            self.offers.append(offer)
            self._by_item[id(item)] = offer

    def deliver(self, item: Any, delivered_power_mw: float) -> None:
        """The kernel called ``discharge`` for ``item``; book what it delivered."""

        offer = self._by_item.get(id(item))
        if offer is None or offer.item is not item:
            return
        offer.visited = True
        offer.delivered_power_mw += float(delivered_power_mw)

    def rows(self, year: int, period: int, period_hours: float, row_type: Callable[..., Any]) -> list:
        """Ledger rows (``row_type`` is ``StorageOrderLedgerRow``) of ``period``."""

        if self.period != int(period):
            return []
        rows = []
        for offer in self.offers:
            accepted_power = max(offer.delivered_power_mw, 0.0)
            if accepted_power <= _EPSILON_MW:
                status = "rejected"
                reason = NO_ENERGY_DELIVERED if offer.visited else MERIT_ORDER_NOT_REACHED
            elif accepted_power + _EPSILON_MW < offer.offered_power_mw:
                status, reason = "partially_accepted", DEMAND_FILLED
            else:
                status, reason = "accepted", CLEARED
            offer_id = f"{offer.stage}:s:{offer.offer_index}:{offer.asset_id}:{offer.charge_period}"
            accepted_mwh = accepted_power * period_hours
            rows.append(row_type(
                order_id=f"{int(year)}:{int(period)}:{offer_id}",
                year=int(year),
                period=int(period),
                stage=STAGE_LABELS[offer.stage],
                clearing_offer_id=offer_id,
                asset_id=offer.asset_id,
                asset_type=offer.asset_type,
                side="supply",
                charge_period=offer.charge_period,
                dwell_periods=offer.dwell_periods,
                bidding_factor=offer.bidding_factor,
                offer_price_gbp_per_mwh=offer.price_gbp_per_mwh,
                offered_mwh=offer.offered_power_mw * period_hours,
                accepted_mwh=accepted_mwh,
                status=status,
                reason_code=reason,
                accepted_offer_value_gbp=offer.price_gbp_per_mwh * accepted_mwh,
            ))
        return rows
