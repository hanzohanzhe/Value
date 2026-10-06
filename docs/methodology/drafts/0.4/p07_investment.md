# Investment decisions, storage headroom and the cost ledger (P0-7 draft for methodology 0.4)

Status: draft written with the P0-7 construction (2026-10-06); to be merged into
`core.md` (en, zh) when the 0.4 edition is generated.

## Money basis: constant base-year money, undiscounted decisions (decision A6)

Every amount in VALUE is in constant base-year GBP: a pound of revenue in a
later model year is worth the same as a pound today. The CEM investment test is
therefore **undiscounted by design**. For an (owner, technology, region) group
with annual net revenue `S`, replacement capital `K` (sum of `total_capex_gbp`),
preferred rate `r_p` and target payback `T`:

* `S < 0` (and a positive unit cost): **Deplete**, retire
  `min(capacity, |S| x T / (K / capacity))` MW, split over the members by MW;
* `S / K > r_p`: **Invest_High**;
* otherwise `K / S <= T`: **Invest_Profit**;
* otherwise **Do_Nothing**.

A proposal adds `S / (K / capacity)` MW (headroom-limited technologies within
their headroom). The ROI and payback tests are the model's rule, not an
approximation of an NPV test: the review finding P4-02 ("accepts NPV < 0
projects") is out of scope, and no NPV, IRR or annuity hurdle is introduced.

This rule differs on purpose from the **cost accounting**, where the capital
of an operating asset enters the annual system cost as an annuity:
`annualised capital = total CAPEX x CRF(r_c, L)` with
`CRF(r, L) = r (1 + r)^L / ((1 + r)^L - 1)` (`asset_economics.py`). The CRF
spreads a capital stock over its life for a year's resource cost; it does not
discount future revenue in the investment test.

## Net revenue (decisions A4 and A7, both profiles)

* **Thermal** (CCGT, OCGT, gas, biomass; any asset with a fuel or carbon cost):
  `S = market income - generated MWh x (generation + fuel + carbon + unit-time
  cost)`, the original Scheme C rule (`runtime_compat/modular_investment_support.py`
  lines 2150-2152, 2246-2247), which the v2 port had dropped. It is a universal
  correction (`p07.thermal-net-revenue`): the doctoral reproduction profile
  applies it too, and its golden was re-baselined once (D4, report
  `tests/golden/reports/D4-r9.json`). A bid-at-cost unit paid its running cost
  has `S = 0` up to rounding (relative 1e-9 is snapped to 0), so it neither
  expands nor retires.
* **VRE and storage**: gross revenue is profit (thesis assumption: CAPEX and
  depreciation only). They have no variable OPEX, and their fixed OPEX is
  treated as already contained in their levelised CAPEX (A7), so no FOM is
  subtracted in the decision and none is added to the headline cost.
* The running cost comes from the PSM's `value.agent-cashflow/v1` extension
  (generated MWh and cost parts per asset); a decidable thermal group without
  it is an error, never a zero. Income stays the PSM's
  `market_income_gbp_by_agent`.

## Storage expansion headroom (corrected profile only)

The doctoral profile keeps the 0.6.0-alpha.2 behaviour (decision Q1): the
surplus is computed as accepted VRE minus demand, which is never positive, so
storage headroom is zero; the power cap is given to each battery type.
The corrected profile (`p07.storage-leftover-headroom`,
`r13.per-type-battery-caps`; `value-storage-expansion-policy` 5.1.0):

* uses the surplus left **after the existing fleet charged**, which the
  default PSM publishes per period from its declared column semantics
  (excess plus curtailed VRE under the corrected rule set);
* runs the retained aligned-utilisation spectrum on that surplus and the
  residual gap after observed discharge; the power-battery room is the daily
  plus intraday band, the hydrogen room the seasonal band, each times
  `expansion.storage_cap_fraction`;
* gives **each** of the 1C, 0.5C and 0.25C batteries its own cap
  `expansion.storage_cap_fraction x power_room` (0.2 by default), as in the
  thesis design (decision A20): the three types serve different durations
  and the fraction is already a reduced share, so together they may add up
  to three times `0.2 x power_room`. The hydrogen battery has its own cap on
  the seasonal band. Each type's additions are capped separately in the
  investment step;
* gives zero headroom with a recorded reason when the chronology is not one
  full year of 17520 half-hour periods (`partial_year_chronology`) or the PSM
  publishes no trace (`leftover_trace_unavailable`).

Between P0-7 and R1-3 the corrected profile instead made the three power
batteries share one pool of `0.2 x power_room` (`p07.power-battery-pool`,
review finding P5-02 read as a defect). Decision A20 withdrew that reading:
per-type caps are the thesis design, not a triple count. The pool entry stays
in the catalogue only so that Runs made in that interval keep a readable
identity; no profile pools any more, and no Run carries an advisory for
either rule. On VALUE 101 and the local GBP1 public2 first year the pool was
never binding (battery requests stayed below it), so the revert changes only
the recorded headroom and investment evidence, not proposals or capacities.

## Cost ledger v2

The headline CEM resource cost is annualised capital plus physical operating
cost. Cost ledger v2 lists two memo lines that are not part of the headline:

* VRE and storage fixed OPEX (A7, both profiles);
* the existing-stock compatibility capital of run-of-river hydro (P4-03), a
  preserved accounting basis (about GBP 10.96bn per year on the UK pack),
  excluded from the corrected headline; the doctoral headline keeps it and
  marks the memo as included.

Capital plus operating cost equals the headline on every result page.
