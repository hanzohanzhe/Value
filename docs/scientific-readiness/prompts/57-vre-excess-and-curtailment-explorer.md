# Prompt 57: VRE excess-generation and curtailment explorer

Execute after Prompt 56. Read Chapter 2 and the Figure 26 discussion in
`PhD thesis7.20_stuart.docx`, the current period ledger, annual PSM result,
curtailment/excess variables and the Prompt 56 market-replay contracts before
editing. Act as a power-system modeller, scientific frontend engineer and data
visualisation engineer. Keep the product UI in English and update the bilingual
guide.

## Objective

Add a dedicated `VRE & curtailment` results page that makes the paper's PSM
claim inspectable rather than reducing all unused renewable electricity to one
number. For every eligible run, show how much VRE was available, delivered,
stored/exported where the model can identify it, classified as pre-balancing
excess generation, or curtailed in balancing. Join the annual totals to the
underlying half-hour chronology without changing the PSM or reconstructing
missing physical quantities in JavaScript.

## Scientific definitions and non-duplication boundary

- Reuse Prompt 56's final physical-dispatch view and the canonical market
  ledger. Do not add another clearing trace, dispatch table or full-run JSON.
- Preserve the thesis distinction:
  - `excess_generation_mwh` is energy already known to be surplus before the
    balancing stage in the executed FORCE information structure;
  - `balancing_curtailment_mwh` is scheduled generation reduced after forecast
    and real demand diverge, after the model's storage/export opportunities;
  - `unused_vre_mwh` is a neutral accounting total when the selected PSM exposes
    only `available VRE - accepted VRE` and cannot scientifically split the two.
- Do not label `excess_mwh` as VRE-only when the selected PSM can include
  nuclear or natural-flow hydro in that variable. Return a composition scope and
  use `inflexible excess generation` unless VRE attribution is proved.
- Do not calculate `available - accepted` and then add reported excess or
  curtailment again. Every energy-flow identity must be explicit and mutually
  exclusive.
- Do not relabel export, storage charging, flexible demand, blackout or a Scheme
  C compatibility adjustment as curtailed energy.
- `Average curtailment rate` uses total unused VRE divided by total available
  VRE. `Marginal curtailment` is a different experiment concerning an additional
  capacity increment; do not display it unless a versioned marginal experiment
  artifact exists. The ordinary annual run must label it `Not evaluated`.
- Historical artifacts remain immutable. Detect their capabilities and show
  partial evidence rather than migrating or filling missing fields.

## Backend contracts

Create `force.vre-curtailment-summary/v1` and
`force.vre-curtailment-timeline/v1`. Include run and project revision, year,
period duration, timezone, selected PSM and module version, definition IDs,
units, source artifact hash and evidence coverage.

The annual contract must include, where scientifically available:

- available VRE MWh;
- accepted/delivered VRE MWh;
- pre-balancing excess generation MWh and its composition scope;
- balancing curtailment MWh;
- neutral unused VRE MWh;
- VRE utilisation and average unused/curtailment rate;
- periods with unused VRE, longest continuous event, peak-period unused VRE and
  the relevant period/timestamp;
- energy directed to storage charging, export and flexible demand, each kept as
  a separate system flow and not automatically claimed as VRE-sourced;
- annual reconciliation residual and coverage status;
- marginal-curtailment status and reason.

The timeline contract must provide bounded exact half-hour slices and
server-side daily/weekly aggregates. It must include available VRE, accepted
VRE, pre-balancing excess, balancing curtailment, neutral unused VRE, demand,
storage charge, export and price where available. Aggregate energy by summation;
never average MWh/period and call it an energy total. For price, declare the
aggregation method.

## Frontend page

Add a top-level navigation item named `VRE & curtailment`, adjacent to
`Market replay`. It uses the selected completed run and provides:

1. An annual bar view inspired by the thesis Figure 26: available VRE split into
   delivered and unused portions for every model year. Keep pre-balancing excess
   and balancing curtailment separately identifiable when the contract supports
   that split. Show exact TWh labels and the average unused share.
2. A selected-year chronological chart inspired by the thesis PSM figures:
   available VRE, delivered VRE and unused/excess/curtailed energy across time,
   with a daily/weekly overview and exact half-hour zoom. Do not add a decorative
   title inside the plot.
3. KPI cards for total available, delivered, excess, balancing curtailment,
   unused share, number of affected periods, longest event and peak event.
4. A destination strip for storage charging, exports and flexible demand. State
   clearly when the ledger proves only simultaneous system flows rather than the
   source of each MWh.
5. A period drawer linked to Prompt 56, so selecting a peak-curtailment period
   opens its physical dispatch and auction evidence.
6. A definitions panel explaining the FORCE/thesis distinction among available
   VRE, delivered VRE, excess generation, balancing curtailment and marginal
   curtailment.
7. CSV/JSONL export through the existing bounded export path and an accessible
   tabular alternative for every chart.

Do not show unavailable quantities as zero. Use `Not available` or
`Not separately attributable`, with a reason. Smoke runs may demonstrate wiring
but must not be presented as annual curtailment evidence.

## Tests and acceptance

Use deterministic fixtures covering no curtailment, pre-balancing excess only,
balancing curtailment only, both classifications, storage charging, exports,
blackout, a non-VRE inflexible excess component and an incomplete historical
ledger.

Acceptance requires:

1. `available VRE = accepted VRE + neutral unused VRE` within tolerance whenever
   the selected PSM defines all three on the same boundary.
2. Split quantities never exceed neutral unused VRE and are never added to it a
   second time.
3. Annual totals exactly equal sums of the exact half-hour rows; daily and weekly
   responses sum to the same annual energy.
4. A deliberately duplicated excess row, VRE/non-VRE scope swap, false zero,
   storage charge relabelled as curtailment or MWh averaging error fails tests.
5. Peak, duration and affected-period statistics are correct across year and
   day boundaries.
6. Figure values rendered by frontend fixtures match the backend contracts
   exactly; the browser performs no scientific recomputation beyond display
   formatting.
7. A summary-trace run supports the annual and chronological VRE page without
   requiring individual order rows. Full trace adds links to bid evidence but
   does not change totals.
8. Measure API latency, payload size and chart rendering on 24-hour, 168-hour
   and 17,520-period fixtures. The initial page remains bounded and does not
   render one DOM element per half-hour for an annual overview.
9. Keyboard, screen-reader summary, colour contrast, responsive layout and empty,
   partial, running, failed and full-evidence states pass frontend tests.
10. Tracing off/summary/full does not change physical dispatch, curtailment or
    annual scientific results. Retained Scheme C and historical run hashes stay
    unchanged.
11. Python tests, frontend lint/build, source-release scan and generated-document
    checks pass.

## Stop conditions

Stop and report rather than mislabel the page if the executed PSM cannot provide
a common boundary for available and accepted VRE, if excess composition cannot
be stated truthfully, or if the annual totals do not reconcile to exact period
rows. Never repair this by clipping, silently netting, assigning every surplus
MWh to VRE, or changing retained Scheme C.

## Deliverables

- versioned annual and timeline contracts with definition documentation;
- bounded query endpoints and capability handling;
- the English `VRE & curtailment` page and bilingual guide update;
- mapping from every KPI/chart series to ledger fields and equations;
- screenshots for complete, separately-unattributable and summary-only states;
- deterministic, mutation, performance and frontend evidence;
- human- and machine-readable Prompt 57 reports, including the precise extent
  to which the page reproduces the logic of the thesis PSM figures.

