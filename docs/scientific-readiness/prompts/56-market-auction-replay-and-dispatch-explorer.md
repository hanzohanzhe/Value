# Prompt 56: Market auction replay and chronological dispatch explorer

Execute after accepted Prompt 55. Read the completed visibility Prompts 07-08,
scientific-readiness Prompts 08, 21, 23, 35-37, the current market-ledger
schema, the live FORCE clearing route and the current `Inspect` page before
editing. Act as a senior power-market frontend architect, simulation data
engineer and power-system modeller. Keep the product UI in English and update
the bilingual user documentation.

## Objective

Add a first-class `Market replay` workspace that lets a non-programmer see:

1. how bids compete and are accepted in one selected PSM period and market
   stage;
2. how the clearing outcome becomes physical generation, storage operation,
   imports, curtailment and unmet demand in that period; and
3. how the final physical outcomes of all half-hour periods join together into
   a chronological daily, weekly or annual dispatch profile.

This is an evidence and visualisation layer over the actual selected PSM. It
must not implement a second clearing algorithm, infer a result in the browser,
or change any retained Scheme C source or historical run artifact.

## Non-duplication and scientific boundaries

- Reuse `market/market.sqlite`, its index, the declared pre-clearing inputs,
  clearing outcomes and the existing bounded market query service. Do not
  create a parallel auction log or one giant JSON result.
- Keep the existing `Inspect` page for planning, raw tables, artifacts and
  provenance. The new navigation item is an explanatory exploration workspace,
  with links back to the exact Inspect evidence.
- Do not add accepted orders from ahead, curtailment and balancing stages as if
  they were independent physical generation. Define one canonical final
  physical dispatch view after all within-period adjustments. Incremental,
  decremental, charge, discharge and settlement quantities must retain their
  own signs and meanings.
- Do not assume that every stage is a uniform-price auction. Read the pricing
  and settlement rule from the executed module/model-card contract and label it
  accurately. If a marginal unit or clearing price is not scientifically
  defined for a stage, show `Not defined` with a reason rather than inventing it.
- Never relabel a Scheme C compatibility adjustment as generation, import,
  storage output, blackout or demand. Display it as an explicit unresolved
  accounting-boundary item and reduce the dispatch-coverage status accordingly.
- Offers, accepted bids, market payments, physical resource costs and final
  delivered energy are different quantities. Keep them visually and
  semantically separate.
- Existing `gridform.market-ledger/v2` run bundles are immutable. Add a new
  versioned read/model contract and backward-compatible capability detection;
  do not migrate old SQLite files in place.

## 1. Define the market-replay contracts

Create versioned, solver-neutral response contracts with definition IDs, units,
timezone, period duration, run ID, project revision, module ID/version, trace
level and source artifact hash.

At minimum define:

- `force.market-auction-view/v1`: one year/period/stage order book, including
  the stage requirement, offered and accepted MWh, rejected or partially
  accepted MWh, offer price, side, asset and technology identity, acceptance
  status/reason, pricing-rule identity, clearing price when defined, marginal
  order when defined, and links to the declared input and clearing outcome;
- `force.physical-dispatch-view/v1`: the final non-duplicated physical outcome
  for one period, by asset and by canonical technology, after all applicable
  stages;
- `force.dispatch-timeline/v1`: bounded chronological slices or server-side
  aggregates of final physical dispatch for charting;
- `force.market-replay-capabilities/v1`: availability of summary, detailed bids,
  physical dispatch, storage state, declared inputs and outcome evidence for a
  selected run.

Canonical technology groups must be driven by backend data mappings rather
than frontend string matching. They must distinguish at least VRE technologies,
nuclear, thermal technologies, natural-flow hydro, reservoir hydro when
present, pumped hydro, other storage technologies, boundary imports and flexible
demand. Unknown technologies remain visible as `Unmapped`, with their raw value
and a warning.

For storage orders, preserve technology, charge/discharge side and state of
charge. Where the executed storage-cost module exposes tranche-level evidence,
include the tranche or source-charge-period identifier, dwell periods and the
storage-cost policy ID. These fields are optional capability fields; absence
must not be filled with guessed values.

## 2. Add a compact final physical-dispatch ledger

The present period summary is not sufficient to reconstruct thermal generation
by technology, while the full order table represents auction evidence rather
than necessarily final delivered energy. Add the smallest reliable backend
representation needed for `force.physical-dispatch-view/v1`.

- Prefer a compact batched SQLite table keyed by run year, period, asset and
  final physical category, or a deterministic post-run materialisation from an
  already complete clearing outcome. Choose the path that can be proved not to
  alter clearing and has the lower measured runtime overhead.
- Summary tracing should retain the compact technology-level final dispatch
  needed for a chronological system view. Full tracing additionally retains
  asset/order-level auction replay.
- Record generation, import, storage charge, storage discharge, flexible demand,
  exports, curtailment, blackout and excess with explicit units and sign
  convention. Do not net storage charge and discharge into one ambiguous value.
- Reconcile every final-period view to the existing physical balance and every
  annual sum to the versioned annual generation/import/storage results. Record
  coverage MWh and coverage percentage. A non-zero compatibility adjustment or
  unmapped quantity must be visible and must prevent a `complete` coverage
  label.
- Preserve batched writes. No dataframe construction, per-order file access,
  per-order JSON serialization or UI-specific formatting may enter the clearing
  hot loop.

## 3. Expose bounded query APIs

Add safe run-relative endpoints or equivalent service calls for:

- replay capabilities and available years/stages;
- chronological final dispatch by year and requested period range;
- server-side technology aggregation at exact half-hour, daily and weekly
  resolution;
- one selected period/stage auction curve and order table;
- one selected period's physical dispatch, storage state and reconciliation;
- search/filter by asset, technology, status, side and stage;
- existing streaming CSV/JSONL export, extended only where a new versioned table
  requires it.

The initial workspace and initial `Market replay` render must not load an annual
order book. Use range requests, pagination, virtualised tables and zoom-driven
detail loading. Exact half-hour values must remain available after zooming even
when the initial annual view uses server-side aggregation. Validate run-relative
paths and reject arbitrary filesystem access.

## 4. Add the `Market replay` navigation workspace

Add one top-level left-navigation item named `Market replay`, positioned after
`Runs` and before `Inspect`. It operates on a selected completed run and has
clear empty, running, summary-only, full-trace, legacy-partial and failed states.

### A. Chronological dispatch view

Provide a responsive stacked dispatch chart with:

- generation by canonical technology and boundary imports above zero;
- storage charging, exports and other controllable consumption below zero;
- demand as a line;
- optional price as a separately scaled panel, not a misleading third axis;
- distinct tracks or overlays for curtailment, excess and blackout;
- year/date-range controls, daily/weekly overview and exact half-hour zoom;
- brush selection that chooses the period shown in the auction replay;
- a legend that can isolate technologies without changing source values;
- exact tooltip values with timestamp, period number, MWh/period and provenance.

The chart represents final physical dispatch, not a sum of auction-stage orders.
Show a compact reconciliation/coverage badge beside it. When coverage is not
complete, identify the missing or compatibility quantity without drawing it as
physical supply.

### B. Selected-period auction replay

For the chosen period and stage, show:

- a merit-order/supply-curve view ordered exactly as the executed PSM ordered
  eligible offers, with accepted, partially accepted and rejected portions;
- the stage requirement or demand line;
- clearing price and marginal order only when defined by the executed rule;
- asset, technology, offered MWh, accepted MWh and GBP/MWh in the tooltip;
- period KPIs for forecast demand, real demand, accepted supply, imports,
  storage charge/discharge, VRE available/accepted, curtailment, blackout,
  excess and balance residual;
- a stage selector that explains ahead, curtailment and balancing roles from
  module metadata rather than hard-coded frontend prose;
- a paginated/virtualised order table linked to the plotted segments;
- a compact storage panel showing SOC and charge/discharge for the selected
  period, with cost-policy identity and optional tranche evidence.

Allow previous/next-period stepping and optional playback at accessible speeds.
Playback must stop on user interaction, respect reduced-motion preferences and
must not prefetch an entire annual order book.

### C. Explanation and evidence

Add short plain-English help explaining bid-at-cost, offered versus accepted
energy, physical dispatch, storage charge/discharge, curtailment, balancing and
why stage transactions cannot simply be summed. Every visual must link to the
corresponding raw Inspect table, declared input, clearing outcome and artifact
provenance when available.

Use the existing FORCE visual language. Do not add a decorative hero, redundant
page title, 3-D chart, animation for its own sake or a Sankey diagram that hides
exact time order. Charts need keyboard-accessible summaries and downloadable
tabular alternatives.

## 5. Trace-level behaviour

- `off`: state that no market replay evidence was retained and offer a safe way
  to clone the study with an appropriate trace setting.
- `summary`: show the chronological technology-level physical dispatch and
  period summary, but clearly disable individual bid replay.
- `full`: show both chronological physical dispatch and complete period/stage
  auction evidence.
- Historical v2 or retained-reference runs: show only capabilities proved by
  their artifacts. Never synthesize missing bids or final asset dispatch.

Preflight must estimate the additional rows, bytes and runtime for the selected
trace level. The study form should explain that full bid replay has a storage
and runtime cost, while summary retains the compact generation chronology.

## 6. Tests and acceptance gates

Create deterministic fixtures covering thermal, VRE, boundary imports, battery,
pumped hydro, storage charging, storage discharge, curtailment, excess and
blackout. Include more than one market stage and at least one partially accepted
order.

Acceptance requires all of the following:

1. The plotted offer order, accepted segments, marginal result and table rows
   match the executed full-trace ledger exactly for every fixture.
2. Final physical dispatch does not double count quantities carried from ahead
   into balancing or curtailment stages.
3. For every period, the displayed final dispatch reconciles to the same balance
   identity and tolerance as the market ledger. Annual technology sums reconcile
   to the authoritative annual result contract.
4. Storage charging and discharging use the declared efficiency/SOC convention;
   neither is silently converted to the other side of the store.
5. A deliberately swapped sign, duplicated stage quantity, missing asset,
   fabricated clearing price or relabelled compatibility adjustment makes the
   scientific UI/API test fail.
6. `off`, `summary`, `full`, v2 historical, incomplete and failed-run states are
   covered by backend and rendered-browser tests.
7. The initial page payload remains bounded as the number of periods and orders
   grows. The annual chart does not create one DOM node per order, and the order
   table is paginated or virtualised.
8. Measure clearing/runtime overhead, SQLite growth, API latency and frontend
   rendering for a 24-hour fixture, a 168-hour fixture and one 17,520-period
   annual artifact. Report results rather than hiding a regression behind a
   larger timeout.
9. Keyboard navigation, focus state, colour contrast, screen-reader chart
   summary, reduced-motion behaviour and responsive layout pass their tests.
10. Tracing off, summary and full produce identical dispatch and annual scientific
    results for the same deterministic input.
11. Retained Scheme C hashes and all completed run-bundle hashes remain unchanged.
12. Frontend lint/build, Python tests, source-release scan and generated-document
    consistency tests pass.

## Stop conditions

Stop and report the gap instead of presenting a misleading chart if any of these
conditions occurs:

- final physical asset/technology dispatch cannot be distinguished from staged
  accepted orders;
- the selected PSM does not declare its stage pricing/settlement semantics;
- displayed generation cannot reconcile with the period and annual ledgers;
- a compatibility adjustment would have to be relabelled as physical supply;
- an annual order book would have to be loaded into browser memory to render the
  default page.

Do not repair a stop condition by modifying retained Scheme C, clipping a
quantity, adding an undocumented residual category or weakening a scientific
gate.

## Deliverables

Provide:

- the new versioned replay/dispatch contracts and schema documentation;
- the compact physical-dispatch artifact and bounded query services;
- the English `Market replay` workspace and updated bilingual README;
- a metric/visual-to-source mapping that identifies the SQLite table/field,
  definition ID, unit and reconciliation rule behind every displayed value;
- screenshots for full, summary-only and incomplete-coverage states;
- performance measurements and mutation-test evidence;
- a machine-readable Prompt 56 report and a concise human-readable report stating
  exactly which PSM modules and historical runs support full auction replay.

