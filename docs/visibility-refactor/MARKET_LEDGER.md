# Market-clearing ledger

`runtime.market_trace_level` selects one run-level writer:

- `off`: null writer, no market database;
- `summary` (default): period summaries and storage state;
- `full`: summary data plus individual offers/acceptance rows.

SQLite uses WAL and batched prepared inserts at
`model-output/market/market.sqlite`. CSV/JSON exports are created only when a
user explicitly requests them.

## Schema and accounting boundary

`gridform.market-ledger/v4` separates demand, traced asset supply, storage
charge/discharge, flexible load, external trades, VRE, curtailment, price,
physical resource cost, market payment, policy transfer, blackout and excess.

Every period stores:

- `raw_energy_balance_residual_mwh`: traced supply minus the traced load boundary;
- `compatibility_adjustment_mwh`: the named amount needed to reconcile that
  copied-session boundary;
- `energy_balance_residual_mwh`: the result after the explicit adjustment.

**Correction (P0-4, 2026-10).** Up to 0.6.0-alpha.2 the adjustment was set to
minus the raw residual whenever the raw residual was not zero, with no cap.
The adjusted residual was therefore zero by construction, and the "0.1%
relative limit" checked nothing: the adjusted residual is **not** evidence of
an energy balance. The raw residual was computed on the retained
demand-serving boundary, which leaves out surplus routed to storage, export
and electrolysis outside the accepted supply; it mixes that surplus with
hidden shortfall (P3-01) and the doctoral double count of must-run surplus
(DEV-BAL-04). It was not only a "visible legacy-accounting limitation".

From P0-4 S6 the default PSM declares its balance boundary in the ledger
metadata (`energy_balance_boundary`: `default_psm_surplus_node_v1` for the
doctoral rule set, `native_corrected_full_node_v1` for the corrected one),
records the surplus routing per source (`surplus_routing`), the per-asset
storage audit (`storage_energy_audit`, `storage_year_boundary`) and the A2
energy-balance account (`balance_boundary_period`, `stress_event`). The
compatibility adjustment absorbs numerical noise only. The independent,
read-only oracle (`python -B -m gridform_core.energy_balance_oracle <run>`)
recomputes the balance from these rows; its verdict, the storage invariants
and the run invariants are the validation gates of the scientific-validation
report (P0-4 S7). Ledgers written before P0-4 S6 can only be checked against
a necessary envelope: `failed` or `not_evaluated`, never `passed`.

`orders` stores offered/accepted MWh, offer price, status, reason, physical cost
and payment. `storage_state` stores SOC, charge/discharge, MW and MWh by asset and
period. `physical_dispatch` is the single final, non-duplicated physical layer
after all within-period stages. Its `flow_type` distinguishes generation, imports,
storage charge/discharge, flexible demand, exports, excess, curtailment and
blackout; `balance_component_mwh` records the signed public-balance contribution.
A compatibility adjustment is never written as generation.

**Storage offers (four-role finding M-D1, 2026-10).** In the default PSM a
battery that discharged appears in `orders` as one `final_dispatch` row with
reason `accepted_non_generator_offer`, offer price 0.0 and offered equal to
accepted; that row is the frozen net-dispatch record (doctoral trajectory
zone), not an offer, and storage offers that were not accepted never appear
there. From `value-bid-at-cost-psm` 6.1.0 the full trace also writes
`storage_orders`: one row per storage tranche offer of the ahead and the
balancing stage, accepted or not, with the storage cost module's bid price
times the bid multiplier (`offer_price_gbp_per_mwh`, `bidding_factor`,
`charge_period`, `dwell_periods`), offered and accepted MWh, status and
reason (`cleared`, `demand_filled`, `no_energy_delivered`,
`merit_order_not_reached`), `accepted_offer_value_gbp` (price x accepted
MWh, the storage fee the kernel books) and `clearing_offer_id`, the
`offer_id` of the same offer in `clearing_inputs`. Under the doctoral rule
set the accepted MWh of a battery and period sum to its `final_dispatch` row
and to `storage_energy_audit.discharge_output_mwh`; under the corrected rule
set the row is net of the same-period buy-back. Accounting zone; dispatch is
unchanged. Schema: `gridform_core/data/contracts/market-ledger-storage-orders-v1.schema.sql`.

`clearing_inputs` and `clearing_outcomes` retain hashes and JSON envelopes for
the exact pre-clearing declaration and its result. They are written only where
the selected PSM and trace policy expose that capability. Perfect-foresight LP
runs therefore have final physical dispatch and dual prices but no fabricated
sequential merit order.

## Query and export

`query_market_table(database, "period_summary" | "orders" | "storage_state" |
"physical_dispatch" | "clearing_inputs" | "clearing_outcomes", ...)`
supports pagination and year/period/stage/asset filters.
`export_market_table(..., output_format="jsonl" | "csv")` streams a requested
export without loading it into memory.

The versioned read models in `gridform_core.market_replay` expose bounded
capability, auction, dispatch-timeline, VRE-summary and VRE-timeline responses.
Daily and weekly energy values are sums of exact half-hour rows. Display prices
use a declared demand-weighted mean. Browser code formats these values but does
not perform scientific attribution or clearing.

Each period price carries its declared basis (`price_basis`): the default PSM's
value is an average period cost per MWh of demand, not a clearing price.
Dispatch-timeline buckets report A2 stress (`shortfall_mwh`, `stress_periods`,
`shortfall_basis`) from the same contract as the energy-balance oracle, and
`query_stress_events` pages the full year's `stress_event` rows (contiguous
periods in which accepted supply fell short of demand; dispatch is unchanged and
the shortfall is booked as unserved energy). The VRE summary reads the column
semantics the rule set declares: under the corrected rule set `excess_mwh` is
non-VRE spill and `curtailed_mwh` is VRE availability minus gross output, so its
unused-VRE events carry the basis `corrected_unused_vre`.

## Relative writer benchmark

Python 3.10 on Windows, 2,000 synthetic periods, one storage row per period and
50 offers per period:

| Level | Wall time | Overhead vs off | Rows | SQLite bytes |
| --- | ---: | ---: | ---: | ---: |
| off | 0.0119 s | 0 s | 0 | 0 |
| summary | 0.1283 s | 0.1164 s | 4,000 | 364,544 |
| full | 5.0857 s | 5.0737 s | 104,000 | 15,388,672 |

These are relative writer measurements, not complete Scheme C runtime. Raw JSON
is stored in `market-ledger-benchmark.json`.
