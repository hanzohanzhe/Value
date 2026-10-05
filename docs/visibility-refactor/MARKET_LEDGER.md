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
