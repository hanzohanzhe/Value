"""Market rule sets of the default PSM kernel (plan P0-6 S2, decisions Q8, A2, A8).

The retained Scheme C kernel (``runtime_compat/modular_simulation_model.py``)
reads one immutable :class:`NativeMarketRules` per run.  Two rule sets exist:

* :data:`DOCTORAL` - the thesis behaviour as implemented at 35aadb3, frozen for
  the doctoral reproduction profile (Q1);
* :data:`CORRECTED` - the target of the corrected profile once every P0-6 step
  has landed.

Which value a field takes for a run is derived only from the methodology
catalogue (C15): each switchable field names the profile-gated correction id
that turns its corrected value on, and :func:`rules_for_methodology` asks
``ResolvedMethodology.enabled(<id>)``.  Profile ids are never compared.

A correction id enters ``gridform_core/data/methodology/corrections/p06.json``
in the same commit that implements its behaviour (with its trigger fixture).
Until then it is listed in :data:`PENDING_CORRECTION_IDS`; a pending switch
resolves to its doctoral value in every profile, so this skeleton (S2) cannot
change any dispatch, price, SoC or cost.  An id that is neither pending nor in
the catalogue raises (``UnknownCorrectionError``): typos fail closed.

Decision A2 cancelled the planned P3-01 dispatch change: ``realisation_basis``
is ``forecast_thesis`` in both rule sets and has no switch.  Decision A8 adds
``storage_settlement_basis`` (corrected storage is paid the period's uniform
clearing price instead of its own maximum bid).  Decision A16-2 (four-role
finding S-D3) adds ``interconnector_import_stage``: the thesis kernel offers
interconnector imports only in the balancing stage, for the residual
upward requirement after the day-ahead schedule; the corrected rule set also
offers them to the day-ahead clearing at the period's counterparty price and
available import capacity (``fx6.day-ahead-interconnector-imports``).  Decision
A18 adds ``nuclear_initial_state``: the thesis kernel starts every run with no
unit running, so a nuclear unit adds its start-up cost to its offer until it
is first accepted; the corrected rule set starts nuclear units in service in
the first period of the run, so the start-up cost is paid only when a unit
restarts after a period off (``fx8.nuclear-in-service-at-start``).  ``operating_cost_basis``
(``dispatch_unit_cost/v1``) is a universal accounting rule (P5-06, plan S4):
it is the same in both profiles and therefore has no profile switch either.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, replace
from typing import Any, Mapping

from ...energy_balance_contract import NATIVE_CORRECTED_RULE_SET
from ...voll import VOLL_GBP_PER_MWH

SCHEMA_VERSION = "value.native-market-rules/v1"
RECORD_SCHEMA_VERSION = "value.native-market-rule-set-record/v1"

DOCTORAL_RULE_SET_ID = "native-doctoral-thesis-v1"
# The energy-balance boundary registry keys the corrected boundary by this id (C19).
CORRECTED_RULE_SET_ID = NATIVE_CORRECTED_RULE_SET
PARTIAL_RULE_SET_PREFIX = "native-partial-"

# Field -> profile-gated correction id that selects the corrected value.
FIELD_CORRECTIONS: dict[str, str] = {
    "surplus_accounting": "p06.d1-surplus-accounting",
    "ahead_merit_key": "p06.storage-after-generation-merit-key",
    "downward_order": "p06.avoided-cost-downward-order",
    "storage_position": "p06.storage-net-per-period",
    "storage_fee_carry": "p06.storage-fee-per-period",
    "vre_direct_electrolysis": "p06.no-vre-pre-clearing-skim",
    "storage_bid_basis": "p06.storage-bid-cycle-only",
    "storage_settlement_basis": "p06.storage-uniform-price-settlement",
    "reliability_voll": "p06.voll-chronology-parameter",
    # FX6 (A16-2, four-role S-D3): method change of the corrected profile.
    "interconnector_import_stage": "fx6.day-ahead-interconnector-imports",
    # FX8 (A18): method change of the corrected profile.
    "nuclear_initial_state": "fx8.nuclear-in-service-at-start",
}

# Correction ids whose behaviour has not landed yet.  P0-6 S5-S10 registered
# every switch in corrections/p06.json together (the kernel runs only the
# complete doctoral or corrected rule set), so none is pending.
PENDING_CORRECTION_IDS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NativeMarketRules:
    """One market rule set of the default PSM (plan 4.6 point 1)."""

    rule_set_id: str
    realisation_basis: str
    surplus_accounting: str
    ahead_merit_key: str
    downward_order: str
    storage_position: str
    storage_fee_carry: str
    vre_direct_electrolysis: str
    storage_bid_basis: str
    storage_settlement_basis: str
    operating_cost_basis: str
    reliability_voll: str
    interconnector_import_stage: str
    nuclear_initial_state: str

    def definition(self) -> dict[str, str]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    @property
    def sha256(self) -> str:
        payload = {"schema_version": SCHEMA_VERSION, **self.definition()}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def switches(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in FIELD_CORRECTIONS}


DOCTORAL = NativeMarketRules(
    rule_set_id=DOCTORAL_RULE_SET_ID,
    realisation_basis="forecast_thesis",
    surplus_accounting="thesis_marginal_vre_only",
    ahead_merit_key="thesis_stable_price",
    downward_order="curtail_cost_thesis",
    storage_position="per_stage_thesis",
    storage_fee_carry="thesis_carry_last_balancing",
    vre_direct_electrolysis="thesis_pre_clearing_skim",
    storage_bid_basis="thesis_dwell_linear",
    storage_settlement_basis="thesis_max_bat_price",
    operating_cost_basis="dispatch_unit_cost/v1",
    # FX5 (A16-5, universal accounting correction fx5.voll-17000): the thesis
    # cost-ledger constant 8000 GBP/MWh is replaced by the author's 17000.
    reliability_voll="constant_17000",
    # The thesis kernel (35aadb3): a positive transfer constraint is an import
    # offer of the balancing stage only (residual upward requirement after
    # the day-ahead schedule); the day-ahead clearing receives no connection.
    interconnector_import_stage="balancing_residual_only",
    # The thesis kernel (35aadb3): accepted_bids starts empty, so in the first
    # period of a run every gas, biomass and nuclear unit adds its start-up
    # cost to its offer (nuclear 500 GBP/MWh on GBP1) until it is accepted.
    nuclear_initial_state="off_until_accepted",
)

CORRECTED = NativeMarketRules(
    rule_set_id=CORRECTED_RULE_SET_ID,
    # Decision A2: P3-01 is recorded as stress events, dispatch is unchanged.
    realisation_basis="forecast_thesis",
    surplus_accounting="rebuilt_available_minus_accepted",
    ahead_merit_key="rounded_price_generation_before_storage",
    downward_order="avoided_cost",
    storage_position="net_per_period",
    storage_fee_carry="per_period",
    vre_direct_electrolysis="disabled",
    storage_bid_basis="cycle_only",
    storage_settlement_basis="uniform_clearing_price",
    operating_cost_basis="dispatch_unit_cost/v1",
    reliability_voll="chronology_parameter",
    # A16-2: imports offer to the day-ahead clearing at the counterparty price
    # with the available import capacity; the balancing stage offers only the
    # capacity the day-ahead schedule left (no double counting).
    interconnector_import_stage="day_ahead_offer_then_balancing_residual",
    # A18: nuclear units are running before the first period of the run (no
    # start-up adder then); a unit that was not accepted in a period (outage,
    # refuelling, zero availability or not cleared) pays it on its restart.
    nuclear_initial_state="in_service_at_start",
)

RULE_SETS: dict[str, NativeMarketRules] = {
    DOCTORAL.rule_set_id: DOCTORAL,
    CORRECTED.rule_set_id: CORRECTED,
}


def _literal_consultations(methodology: Any) -> dict[str, Any]:
    """Each switch asked by its literal correction id.

    The methodology catalogue scan (scripts/check_methodology_catalog.py)
    requires every profile-gated correction to be consulted as
    ``enabled`` with the literal id somewhere in the code (C15).
    """

    return {
        "p06.d1-surplus-accounting": lambda: methodology.enabled("p06.d1-surplus-accounting"),
        "p06.storage-after-generation-merit-key": lambda: methodology.enabled("p06.storage-after-generation-merit-key"),
        "p06.avoided-cost-downward-order": lambda: methodology.enabled("p06.avoided-cost-downward-order"),
        "p06.storage-net-per-period": lambda: methodology.enabled("p06.storage-net-per-period"),
        "p06.storage-fee-per-period": lambda: methodology.enabled("p06.storage-fee-per-period"),
        "p06.no-vre-pre-clearing-skim": lambda: methodology.enabled("p06.no-vre-pre-clearing-skim"),
        "p06.storage-bid-cycle-only": lambda: methodology.enabled("p06.storage-bid-cycle-only"),
        "p06.storage-uniform-price-settlement": lambda: methodology.enabled("p06.storage-uniform-price-settlement"),
        "p06.voll-chronology-parameter": lambda: methodology.enabled("p06.voll-chronology-parameter"),
        "fx6.day-ahead-interconnector-imports": lambda: methodology.enabled("fx6.day-ahead-interconnector-imports"),
        "fx8.nuclear-in-service-at-start": lambda: methodology.enabled("fx8.nuclear-in-service-at-start"),
    }


def _switch_enabled(methodology: Any, correction_id: str) -> bool:
    from ...methodology import UnknownCorrectionError

    ask = _literal_consultations(methodology).get(correction_id, lambda: methodology.enabled(correction_id))
    try:
        return bool(ask())
    except UnknownCorrectionError:
        if correction_id in PENDING_CORRECTION_IDS:
            return False
        raise


def rules_for_methodology(methodology: Any) -> NativeMarketRules:
    """Rule set of a resolved methodology, field by field from its corrections."""

    values: dict[str, str] = {}
    for name, correction_id in FIELD_CORRECTIONS.items():
        source = CORRECTED if _switch_enabled(methodology, correction_id) else DOCTORAL
        values[name] = getattr(source, name)
    for rules in (DOCTORAL, CORRECTED):
        if rules.switches() == values:
            return rules
    partial = replace(DOCTORAL, rule_set_id="pending", **values)
    return replace(partial, rule_set_id=PARTIAL_RULE_SET_PREFIX + partial.sha256[:12])


def pending_switches(rules: NativeMarketRules) -> list[str]:
    """Correction ids of fields that still hold the doctoral value only because
    their corrected behaviour has not landed (diagnostic for the record)."""

    return sorted(
        correction_id for name, correction_id in FIELD_CORRECTIONS.items()
        if correction_id in PENDING_CORRECTION_IDS and getattr(rules, name) == getattr(DOCTORAL, name)
    )


def active_rules(explicit: NativeMarketRules | None, runtime: object | None) -> NativeMarketRules:
    """The kernel's rule set (plan 4.6 point 2, fail-closed).

    explicit argument > ``runtime.market_rules`` > the reference module runtime
    (``SchemeCModuleRuntime``: doctoral) > no runtime at all (unit-level kernel
    use: doctoral).  Any other configured runtime without rules is an adapter
    that forgot to choose: refuse instead of guessing.
    """

    if explicit is not None:
        if not isinstance(explicit, NativeMarketRules):
            raise TypeError(f"market_rules must be NativeMarketRules, not {type(explicit).__name__}")
        return explicit
    if runtime is None:
        return DOCTORAL
    configured = getattr(runtime, "market_rules", None)
    if configured is not None:
        if not isinstance(configured, NativeMarketRules):
            raise TypeError(
                f"runtime.market_rules must be NativeMarketRules, not {type(configured).__name__}"
            )
        return configured
    from .scheme_c_modules import SchemeCModuleRuntime

    if isinstance(runtime, SchemeCModuleRuntime):
        return DOCTORAL
    raise RuntimeError(
        f"Scheme C module runtime {type(runtime).__name__} is configured without market_rules; "
        "the default PSM refuses to choose a market rule set implicitly"
    )


# A16-5: VoLL is 17000 GBP/MWh in both profiles (gridform_core/voll.py).
DOCTORAL_VOLL_GBP_PER_MWH = VOLL_GBP_PER_MWH
DEFAULT_VOLL_GBP_PER_MWH = VOLL_GBP_PER_MWH


def voll_gbp_per_mwh(rules: NativeMarketRules, parameters: Mapping[str, Any] | None) -> float:
    """VoLL of the physical operating cost (plan appendix P0-6 Q7, decision A16-5).

    The doctoral rule set uses the constant 17000 GBP/MWh (the thesis code's
    8000 was replaced by the universal accounting correction
    ``fx5.voll-17000``); the corrected one reads ``market.voll_gbp_per_mwh``
    (default 17000 GBP/MWh).  VoLL enters only the cost accounts of the
    default PSM, never its dispatch.
    """

    if rules.reliability_voll == "constant_17000":
        return DOCTORAL_VOLL_GBP_PER_MWH
    value = (parameters or {}).get("market.voll_gbp_per_mwh", DEFAULT_VOLL_GBP_PER_MWH)
    return float(DEFAULT_VOLL_GBP_PER_MWH if value is None else value)


def column_semantics(rules: NativeMarketRules) -> dict[str, str]:
    """Ledger column semantics of a rule set (C20; read by P0-7 and P0-9).

    The doctoral values are the retained 35aadb3 declarations.  Under the
    corrected rule set ``vre_accepted`` is gross VRE output (including surplus
    consumed by storage, export or flexible demand), ``curtailed`` is VRE
    availability minus that gross output and ``excess`` is the non-VRE spill;
    the two unused quantities are disjoint, so leftover = excess + curtailed.
    """

    if rules.surplus_accounting == "rebuilt_available_minus_accepted":
        return {
            "excess_scope": "non_vre_spill",
            "excess_relationship": "separate_prebalancing",
            "curtailment_semantics": "vre_available_minus_gross_output",
            "vre_accepted_semantics": "gross_vre_output_including_consumed_surplus",
            "leftover_relationship": "excess_plus_curtailed_disjoint",
        }
    return {
        "excess_scope": "inflexible_mixed",
        "excess_relationship": "separate_prebalancing",
        "curtailment_semantics": "balancing_stage_down_regulation_after_storage_export_and_flexible_demand",
    }


def require_supported_rules(rules: NativeMarketRules) -> NativeMarketRules:
    """Only the two tested rule sets run in the kernel (plan 4.6 point 1).

    A partial rule set mixes column semantics (and declares no energy-balance
    boundary), so the kernel refuses it instead of clearing a combination no
    test covers.
    """

    for supported in (DOCTORAL, CORRECTED):
        if rules == supported:
            return rules
    raise RuntimeError(
        f"GF_MARKET_RULES_UNSUPPORTED: market rule set {rules.rule_set_id} is neither "
        f"{DOCTORAL.rule_set_id} nor {CORRECTED.rule_set_id}; the default PSM runs only these two"
    )


def storage_bid_basis_source(cost_object: object) -> str:
    """``rule_set`` when the kernel's rule set owns the object's bid basis.

    Only an object whose type is exactly ``DynamicAnnualStorageCost`` (the
    built-in dynamic-annual-storage-cost module) takes its bid basis from the
    rule set; subclasses (user formula), the legacy tariff and external
    modules define their own bid (``module_defined``).
    """

    from .runtime_compat.storage_cost import DynamicAnnualStorageCost

    return "rule_set" if type(cost_object) is DynamicAnnualStorageCost else "module_defined"


def market_rule_set_record(
    rules: NativeMarketRules,
    *,
    storage_cost_module_id: str | None = None,
    storage_bid_basis_sources: Mapping[str, str] | None = None,
    runtime_kernel_tree_sha256: str | None = None,
    voll_gbp_per_mwh: float | None = None,
) -> dict[str, object]:
    """The ``market_rule_set`` record (extensions / ledger metadata / identity)."""

    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "rule_set_id": rules.rule_set_id,
        "rule_set_sha256": rules.sha256,
        "rules": rules.definition(),
        "switch_corrections": dict(FIELD_CORRECTIONS),
        "pending_switches": pending_switches(rules),
        "storage_cost_module_id": storage_cost_module_id,
        "storage_bid_basis_sources": dict(storage_bid_basis_sources or {}),
        "runtime_kernel_tree_sha256": runtime_kernel_tree_sha256,
        "voll_gbp_per_mwh": voll_gbp_per_mwh,
    }
