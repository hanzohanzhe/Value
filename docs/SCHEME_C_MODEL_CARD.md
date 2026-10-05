# FORCE model card

**FORCE** is the **F**lexibility **O**ptimization, **R**esource
**C**ompetition, & **E**xpansion framework. Its current UK configuration retains
the internal `scheme-c-*` implementation and data-pack identifiers so that
historical runs and the read-only numerical reference remain reproducible.

The selectable capacity-expansion path is **FORCE-CEM v1**. It is derived from
the Scheme C research structure but is not an exact numerical reproduction.
Immutable project/asset lineage and typed technology aggregation replace retained
in-place Python-object mutation. REPD filtering, policy-support income and
exogenous pumped-hydro differences are listed in each run's
`cem-model-identity.json`.

Physical operating assets and investment owners have separate identities. The
current FORCE-CEM policy evaluates one owner/technology/region group once per
year, spends VRE/storage headroom as one technology-wide MW budget and explicitly
lists which thermal technologies are uncapped. Commissioned assets inherit an
existing owner or remain non-investing external assets; they cannot multiply the
number of investment tests.

Existing pumped hydro and natural-flow hydro remain valid operating stock. New
hydro is site constrained and is deferred unless the project carries the required
hydrology/site identifiers, storage energy where applicable, and a separately
sourced `capital_cost_scope=new_build` record. The Scheme C hydro stock value is
an accounting compatibility basis, not a new-build CAPEX assumption.

This module represents Great Britain as one node without internal transmission
limits. Interconnectors are exogenous boundary import offers, not transmission
lines inside the GB network. Dispatch is continuous bid-at-cost competition among
VRE, storage, thermal generation and imports; it has no unit start/stop, ramping,
minimum-output or minimum up/down constraints.

A normal model year contains 17,520 half-hour periods. Short diagnostic runs only
verify wiring and never publish annual economic indicators. The retained
implementation requires Python 3.10 for numerical parity.

The 1e9 MW / 1e9 MWh virtual storage pool is a non-binding diagnostic sentinel,
not physical installed storage. FORCE-CEM system cost definition
`force.cem-system-resource-cost/v1` uses reconciled active-fleet
annualised CAPEX, explicit fixed O&M, realised operating costs and implemented
policy-mechanism costs. A retained Scheme C comparison is reported under its own
cost-definition identifier. Fixed assumptions require a new module version; they
are not advanced-setting sliders.

Every run writes `cem-model-identity.json`, `scheme-c-model-card.json` where the
compatibility route requires it, and `resolved-run.json`. A bid
multiplier other than 1.0 is marked experimental and the run must not be described
as strict bid-at-cost.

Default PSM market rule sets (P0-6). The doctoral reproduction profile clears
with the 0.6.0-alpha.2 rules (`native-doctoral-thesis-v1`) and declares their
known deviations: VRE crowded out by zero-priced storage or must-run nuclear is
not recorded, must-run nuclear surplus used for balancing is counted twice
(DEV-BAL-04), the last balancing storage fee is carried into later curtailment
periods, VRE is skimmed to electrolysis before clearing, storage bids carry a
linear dwell term and storage is paid its own maximum bid. The corrected profile
(`native-corrected-v1`) removes these; its zero-priced pumped hydro and hydrogen
storage dispatch myopically (no water value), a buy-back does not refund the
ahead storage payment, and the realisation branch still follows the forecast
(decision A2), so ahead shortfalls are reported as stress events.

