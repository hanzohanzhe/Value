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

Version and methodology profiles (VALUE 0.7.0-alpha.1). Every Run records
one of two methodology profiles (`docs/generated/METHODOLOGY_PROFILES.md`):

- the corrected default (`value-corrected`), which applies every correction
  of the 2026-10 review;
- the frozen doctoral reproduction (`doctoral-lineage-0.6.0a2`, "as
  implemented in VALUE 0.6.0-alpha.2"). It is not an exact reproduction of the
  2026-07-18 retained trajectory. It changes only under the universal
  corrections: interconnector clock P6-24, GBP1 reading P6-02, P6-03 and
  P6-04, thermal net revenue A4, stress events A2, and accounting-only
  corrections.

In the doctoral profile, an accepted nuclear unit runs at full power until the
end of the year (path dependency of the frozen kernel). Its GBP1 run fails the
surplus-conservation invariant in 471 periods (up to 991 MWh), as the 35aadb3
code did. This is a known issue under investigation (A15), and the run's annual
results stay withheld.

The paragraphs below say which profile each statement applies to. The bounded
claims are in `docs/VALIDATION_AND_CLAIMS.md`, section "Scope of the
0.7.0-alpha.1 claims".

Known simplifications of both profiles:

- the market is energy only, without reserves, unit commitment or ramping;
- investment is myopic and undiscounted (A6);
- weather is climatological;
- the realisation branch follows the forecast, and ahead shortfalls are
  reported as stress events (A2);
- there is no support revenue for biomass (no CfD top-up, no ROCs; review
  finding P4-07, next round). Biomass offers at its full fuel and carbon cost
  (85 GBP/MWh in the shipped GB parameters, above CCGT 55.07 and OCGT 74.92),
  so it is rarely dispatched: about 0.01 TWh from 4,762 MW in the 2025 GBP1
  and R029 corrected runs. Runs with biomass carry the advisory
  `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED` (A24-2; disclosure only, no
  behaviour change).

The corrected profile also has these simplifications:

- zero-priced pumped hydro and hydrogen storage dispatch myopically, without
  a water value;
- a buy-back does not refund the ahead storage payment.

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

Investment rule (P0-7). Investment decisions are undiscounted ROI / payback
tests in constant base-year money (decision A6). Thermal plants net their
running cost (fuel, carbon, unit-time cost) in both profiles (decision A4);
VRE and storage keep gross revenue as profit and carry no separate fixed OPEX
(A7). Only the corrected profile opens storage expansion (post-charge surplus,
one cap of 0.2 x power room for each power battery type, decision A20); the
doctoral profile keeps zero storage headroom.

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

Corrected-profile inputs (P0-5b). The corrected profile reads ERA5 weather
with its time conventions (weather v2), multiplies wind and solar by cited
literature loss factors (no calibration to statistical load factors), and
derates nuclear (station load factors, month-exact generation end) and
natural-flow hydro (annual load factor x monthly shape); the reference values
were PENDING AUTHOR REVIEW at this step (reviewed by the author in A14, see
below). The kernel receives the same arrays as the
canonical adapter. The doctoral reproduction profile keeps the 0.6.0-alpha.2
inputs.

Corrected-profile update (F2, decisions A9, A10, A13, A14). Solar output is the
plane-of-array irradiance (Erbs decomposition, Hay-Davies transposition,
latitude-optimal south-facing tilt, per-period sun position) times the
performance ratio, for ERA5 accumulations; every nuclear station retires by
month; natural-flow hydro uses the DUKES 2019-2024 load factor 0.3487 with a
seasonal shape. The nuclear and hydro values were reviewed by the author (A14).
The model's wind capacity factors stay above DUKES load factors (GBP1 onshore
about 1.6x, offshore 1.2x) and are disclosed next to them, not calibrated (A9).

