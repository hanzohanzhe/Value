# Changelog

## 0.7.0-alpha.1 — P0 review fixes (source only, not yet released, 2026-10-06)

Python version `0.7.0a1`. This is the source state of branch
`fix/review-2026-10-04`. No installer of 0.7.0-alpha.1 has been built or
installed. The Full batch `2026-10-03-rc1` is still 0.6.0-alpha.2. An
existing installation is upgraded side by side, as described in
`docs/release/P0_ACCEPTANCE.md`, section 6.

### Two methodology profiles

- **Corrected methodology (default)** (`value-corrected`): every correction
  in the catalogue applies. New Studies and Runs use it unless they choose
  otherwise.
- **Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)**
  (`doctoral-lineage-0.6.0a2`, frozen): this profile is *not an exact
  reproduction of the 2026-07-18 retained trajectory*. It keeps the
  0.6.0-alpha.2 behaviour, including gross-revenue investment for VRE and
  storage and zero storage headroom (decision Q1); its per-type battery caps
  are the thesis design, which the corrected profile also uses since A20. It
  writes its reference configuration into the Study: the legacy storage
  tariff and the doctoral carbon-factor scenario (Q3). It runs only the
  thesis-lineage modules and data packs and refuses enabled external code.
  Its annual results are published on result pages only when every raw
  invariant passed; otherwise they can be read only through Inspect and
  export (Q14).
- **Universal corrections apply to both profiles**, so they are the only
  changes to the frozen behaviour. They are:
  - interconnector series aligned period by period to the 17,520-period clock
    (P6-24);
  - three GBP1 reading errors fixed: the Belgium price is hourly EUR, not
    half-hourly GBP (P6-02); the BE/NL flow files were swapped (P6-03); demand
    was shifted after the DST change on 2022-10-30 (P6-04);
  - thermal investment net of running cost (A4);
  - stress events (A2);
  - value of lost load 17,000 GBP/MWh (A16-5; the thesis code's 8,000 entered
    only the cost accounts);
  - three implementation errors of the thesis kernel (A26, R4-1): down
    regulation in the curtailment branch is taken once, must-run nuclear
    surplus is not counted twice in balancing, and a store keeps one net
    position per period (see "Three thesis-kernel errors corrected in both
    profiles" below);
  - corrections in the accounting zone only (residuals, audits, cost ledger,
    validation; Q12).
- The investment rule stays undiscounted, in constant base-year money (A6).
- The generated table `docs/generated/METHODOLOGY_PROFILES.md` lists every
  correction with its track and the profiles it applies to.

### Correction ids

| Package | Both profiles | Corrected profile only |
|---|---|---|
| X0 | `x0.methodology-identity`, `x0.study-revision-migration` | — |
| P0-4 | `p04.validation-v2`, `p04.storage-energy-audit`, `p04.surplus-routing`, `p04.surplus-node-boundary`, `p04.validation-gate` (accounting zone) | — |
| P0-5 | `p05.declared-column`, `p05.belgium-price-currency`, `p05.boundary-identity`, `p05.demand-utc-clock`, `p05.interconnector-clock`, `p05.validation-layers`, `p05.weather-cache-key` | `p05.declared-reader`, `p05.series-clock`, `p05.data-gate`, `p05.weather-time-convention`, `p05.vre-loss-factors`, `p05.solar-plane-of-array`, `p05.firm-availability`, `p05.nuclear-generation-end-month`, `p05.hydro-dukes-load-factor`, `p05.raw-boundary-price` |
| P0-6 | `p06.physical-operating-cost` | `p06.d1-surplus-accounting`, `p06.storage-after-generation-merit-key`, `p06.avoided-cost-downward-order`, `p06.storage-net-per-period`, `p06.storage-fee-per-period`, `p06.no-vre-pre-clearing-skim`, `p06.storage-bid-cycle-only`, `p06.storage-uniform-price-settlement`, `p06.voll-chronology-parameter`, `p06.staged-dwell-disclosure` (staged path) |
| P0-7 | `p07.thermal-net-revenue`, `p07.cost-ledger-v2` | `p07.storage-leftover-headroom`, `p07.power-battery-pool`, `p07.compatibility-capital-out-of-headline` |
| P0-8 | `p08.zonal-solver-v4`, `p08.runtime-fallback-audit`, `p08.dec-economic-pricing`, `p08.pro-rata-ties`, `p08.dec-class-order`, `p08.network-free-counterfactual`, `p08.boundary-primary-dual`, `p08.network-share-expansion` (software fixes; network modules run only under the corrected profile, Q3) | — |
| FX4 (post-UAT M-D1) | `fx4.storage-offer-ledger` (accounting zone) | — |
| FX5 (A16-5 VoLL) | `fx5.voll-17000` (doctoral: accounting zone; parameter default for every module that reads `market.voll_gbp_per_mwh`) | — |
| FX6 (A16-2, four-role S-D3) | — | `fx6.day-ahead-interconnector-imports` (method change, explicit Study confirmation) |
| FX7 (A16-7, GBP1 public2 local acceptance) | — | `p05.nuclear-stations-public2` (GBP1 public2 only) |
| FX8 (A18, nuclear in service at start) | — | `fx8.nuclear-in-service-at-start` (method change, explicit Study confirmation) |
| R1-2 (A19/A22, economic down-regulation order) | — | `r12.economic-downward-order` (method change, explicit Study confirmation) |
| R3-2 (A24-3, economic down-regulation order of the network models) | — | `r32.network-economic-downward-order` (staged / zonal path, which runs only under the corrected profile, Q3; method change, explicit Study confirmation) |
| R1-3 (A20, per-type battery caps) | — | `r13.per-type-battery-caps` (method change, explicit Study confirmation; supersedes `p07.power-battery-pool`) |
| R3-3 (A24-4, restart costs in 2025 GBP) | — | `r33.restart-cost-price-base-2025` (parameter restatement used by `r12.*` and `r32.*`; recorded on the default PSM 6.6.0 and staged PSM 1.6.0 ledger bumps, explicit Study confirmation) |
| R4-1 (A26, thesis-kernel errors) | `r41.down-regulation-taken-once`, `r41.must-run-surplus-counted-once`, `p06.storage-net-per-period` (made universal; default PSM 6.7.0, explicit Study confirmation) | — |
| R4-3 (A27, four-role S-中1, model clock label) | `r43.model-clock-utc-label` (ledger metadata label only, accounting zone; no model value changes) | — |

P0-1 (local API security boundary), P0-2 (module quarantine), P0-3 (run
lifecycle) and P0-9 (result views) are software fixes. They have no
correction id and do not change model numbers.

### Golden delta summary

`docs/release/P0_GOLDEN_DELTA.md` is generated by
`scripts/golden/delta_report.py`. It shows, for each golden case, the columns
that changed since revision 0 (35aadb3) and the columns where the two
profiles differ. Every column is attributed to a correction id; none is
unattributed.

- **Doctoral family.** The trajectory columns of D1–D3 (VALUE 101 smoke,
  two_year_smoke and value_101_day) are bit-identical to 35aadb3. D4 (VALUE
  101 two_year) was re-baselined once for the thermal net revenue (A4): only
  an unprofitable CCGT is no longer built, two-year proposals fall from
  21.32 MW to 8.26 MW and system cost falls by 1.7 % (approved in A12). D5
  (GBP1 public1, first model year) was re-baselined once for A3, A5 and A4,
  and the author accepted it as the new reference (A15): imports fall by
  78 %, price spikes disappear, system cost falls by 3.2 %, the CCGT proposal
  is dropped and emissions rise by 3.4 %.
  Numeric reports: `tests/golden/reports/D4-r9.json` and `D5-r1.json`.
  R4-1 (A26) re-baselined D3 (r14), D4 (r12) and D5 (r3) once for the three
  thesis-kernel corrections (findings A15, DEV-BAL-04, DEV-STO-01; numeric
  reports `D3-r14.json`, `D4-r12.json`, `D5-r3.json`, summary in
  `docs/dev/p0-reports/r41-golden/`); D1 and D2 (r11) change only the list
  of declared deviations in the validation report. All other doctoral
  changes are in the accounting and identity zones.
- **Corrected family.** C1–C8 were revised under the correction ids above.
  Trajectory columns that changed since revision 0, by case: C1 34, C2 35,
  C3 50, C4 32, C5 503, C6 490, C7 34, C8 111.
  C9 (GBP1 public2, corrected, FX8) starts at revision 0 = the code before
  A18 and has one revision for A18 (trajectory 394 columns).
  R1-2 (A19/A22, `r12.economic-downward-order`) revised C1-C6 and C9 once
  (C1-C4, C9: the ten new `downward_restart_economics` columns; C5/C6: one
  2025 period, 28 trajectory and 41/43 accounting columns).
  R1-3 (A20, `r13.per-type-battery-caps`) revised C1, C2, C4-C7 and C9 once,
  for the storage headroom and investment evidence columns only (no pool
  declared, per-type cap evidence); proposals and capacities are unchanged.
  R2-1 (A22a closure, DECISIONS A23) revised C1-C6 and C9 once for the
  restart table's corrected formula text (`restart_table_sha256`, one
  trajectory column each; numbers unchanged) and synchronised the identity
  zones of C3 (R3-N6) and D3 (R-D10, identity only).
  R3-1 (A24-1) re-pinned C9 to GBP1 public2 `@v3` (the solar profile
  without its extra hour; trajectory and accounting unchanged) and added
  C10: R029 public2 under the corrected profile with the default modules of
  a new Study, first model year (revision 0).
  R3-2 (A24-3, `r32.network-economic-downward-order`) revised C7 (r13: rule
  record and the new `downward_restart_economics` extension) and C8 (r15:
  each CCGT dec becomes two bids, 40 more bid-ledger rows; dispatch, curtailment
  and costs move only by solver tolerance, at most 1.4e-7 MWh); numeric
  reports `docs/dev/p0-reports/r32-golden/`.
  R3-3 (A24-4, `r33.restart-cost-price-base-2025`) revised C1-C10 once for
  the restart costs in 2025 GBP: C1-C6, C9 and C10 change only the
  `restart_table_sha256` column (no priced shutdown segment is reached, so
  dispatch, curtailment and costs are bit-identical, GBP1 and R029 2025
  included); C7 the rule record and extension sha; C8 the CCGT last-resort
  shutdown dec prices (-373.5 -> -388.3 GBP/MWh) and solver-tolerance
  movements of the zonal LP; numeric report
  `docs/dev/p0-reports/r33-golden/C8-r16.json`.
  R4-3 (A27, `r43.model-clock-utc-label`) revised all fifteen cases (D1-D5,
  C1-C10) once for two accounting columns, `semantic_metadata.timezone` and
  `semantic_metadata.calendar` of `market/metadata.json` (now `UTC` and
  `fixed_365_day_utc_periods`; the staged ledgers of C7 and C8 record them
  for the first time). Trajectory and every other accounting column are
  unchanged.

### Known issues

- ~~**GBP1 doctoral run fails surplus conservation (decision A15).**~~
  Resolved by decision A26 (R4-1, `r41.down-regulation-taken-once`): the
  failure (563 routing rows, not 471 periods; 471 was the envelope count)
  was a real double down regulation in the thesis kernel
  (`docs/dev/GBP1_SURPLUS_CONSERVATION_INVESTIGATION.md`). After R4-1 the
  GBP1 doctoral run passes every raw invariant and its annual results are
  published (Q14).
- **Nuclear path dependency in the doctoral profile.** In the frozen kernel,
  a nuclear unit that has been accepted runs at full power until the end of
  the year. In the GBP1 before/after comparison this is one mechanism behind
  the differences (A15).
- ~~Nuclear path dependency also in the corrected profile (FX7).~~ Resolved
  for the corrected profile by decision A18 (FX8, `fx8.nuclear-in-service-at-start`,
  see "Nuclear in service at the start of the year" below): GBP1 public2
  2025 nuclear 2.02 -> 38.26 TWh (+2.5 % against Energy Trends 5.1). The
  doctoral profile keeps the thesis rule (previous item).
- **R029 public1 and GBP1 public1 solar profile under the strict corrected
  reader.** Both bind the same hourly `sa.csv` with 8761 values and no
  interval declaration; the declared clock recognises an undeclared hourly
  series only at 8760/8784 values, so the strict reader refuses it
  (`GF_DATA_SHORT_SERIES`) when the default PSM builds its chronology, while
  the data-pack validation layers report the pack eligible. The released
  packs are unchanged. Resolved in the local revisions R029 public2 and GBP1
  public2 `@v3` (A24-1, see "The extra hour of the hourly solar profile"
  below); the validation layers still do not check a VRE profile's clock.

- **Zonal LP numerical fragility (found in R3-3).** For some coefficient
  combinations the zonal redispatch LP (HiGHS dual simplex through SciPy
  1.8.1, tolerances 1e-9) stops in the `physical_throughput` phase with
  "optimal for the scaled model, NOTSET in the unscaled model"
  (`GF_ZONAL_SOLVER_FAILURE`). In the two-zone live toy of
  `tests/test_r32_network_economic_dec.py` it happens with an OCGT restart
  cost of 173-178 GBP/MW and a GBP 90 southern unit, and with other price
  pairs (OCGT 80 / CCGT 95). The rule is not involved; the zonal module
  (4.0.0) and solver contract v4 are unchanged in R3-3. A retry policy or a
  scaling fix belongs to the network owner; the live toy now uses a GBP 100
  southern unit (documented in the test).
- **Biomass is rarely dispatched (A24-2, disclosure).** VALUE has no CfD or
  ROC support revenue for biomass (P4-07, next round). Biomass offers at its
  full fuel and carbon cost (85 GBP/MWh in the shipped GB parameters, above
  CCGT 55.07 and OCGT 74.92) and generates about 0.01 TWh from 4,762 MW in
  the 2025 GBP1 and R029 corrected runs. Both profiles behave this way and
  are unchanged; Runs with biomass carry the advisory
  `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED` (see "Restart costs in the model's
  price base; biomass disclosure" below).

### Migration notes

- **Saved Studies.** When a saved Study's revision no longer matches the
  installed code, VALUE classifies the mismatch (Q13):
  - a code-identity or environment change appends a revision automatically
    when the Study next starts a Run;
  - a method upgrade needs explicit confirmation in the UI: a module bump
    with `requires_user_opt_in`, a changed solver contract, or the first
    recording of the methodology profile;
  - changed content and unverifiable revisions stay errors.

  Every Study saved before this version therefore asks for one
  confirmation before its first Run. `GET /api/projects/<id>/revision-migration`
  previews the classification and writes nothing.
- **Runs made before the fixes.** These Runs are read, never rewritten. They
  carry the read-time advisory `VALUE-ADV-2026-10-04-REVIEW`, plus one
  advisory for each correction that applies to them. A recorded positive
  status (`passed`) is shown as `superseded_pre_fix`, and the original value
  is kept in `recorded_*`. Comparisons that involve such a Run are marked
  `needs_review`.
- **Unfinished Runs.** A Run left unfinished by 0.6.0-alpha.2 cannot be
  resumed. The backend source hash is part of the execution identity, so
  finish or cancel these Runs before upgrading.
- **Zonal Studies.** A zonal Study that saves solver contract v2 or v3 gets
  `GF_SOLVER_CONTRACT_UPGRADE_REQUIRED` (409) together with an upgrade
  preview. A historical zonal Run whose method has been superseded gets
  `GF_RUN_METHOD_SUPERSEDED` when it is resumed or re-run.
- **Direct API clients and scripts.** Every request except `GET /api/health`
  and `OPTIONS` needs the per-process session header `X-VALUE-Session`; use
  `backend.api_session.authorized_headers`. Browsers reach the API only
  through the UI gateway.
- **Installed modules and extensions.** A broken external module or
  extension, or one whose name collides with another, is quarantined; it no
  longer stops VALUE. To recover offline, run
  `python -m gridform_core.module_recovery`.
- **Installation.** The installer installs only into an empty directory.
  `docs/release/P0_ACCEPTANCE.md` shows how to carry the state across
  without the session and lock files.

### API contract changes

| Area | Change | Package | Kind |
|---|---|---|---|
| Every `/api` request | `X-VALUE-Session` is required, except for `GET /api/health` without a session and for `OPTIONS`. CORS is removed. Any `Origin` returns 403; a foreign `Host` 421; a form or missing POST Content-Type 415; chunked POST 411. | P0-1 | breaking |
| Error answers | The body carries `error_code` and the response carries the header `X-VALUE-Error-Code`. One exception boundary maps errors to 400/404/409/415/503/504. | P0-1, P0-2, P0-3 | changed |
| `GET /api/health` | Adds `status: degraded` and `degraded_reasons [{code, count}]`. Without a session it returns a reduced payload. | P0-1, P0-2 | changed |
| Module and extension lifecycle | New `POST /api/modules/rescan`. Conflicts return 409 (was 400). A probe timeout returns 504. A stale catalogue returns 503 at run start. Pending runs return `GF_MODULE_LIFECYCLE_RUNS_PENDING` until the change is confirmed. Responses carry `module_quarantine`. | P0-2 | changed |
| Run lifecycle | New `POST /api/runs/<id>/mark-lost`. New fields `worker_liveness`, `worker`, `cancel_requested_at`, `persisted_status` and `lifecycle_history`; `worker.json` v2. | P0-3 | additive |
| Run and summary payloads | New `methodology`, `advisories`, `advisory_summary`, `recorded_*` statuses and `result_publication` (Q14). The status vocabulary is passed / failed / not_evaluated / superseded_pre_fix / reproduction_with_declared_deviations / reproduction_conformant. | X0 | additive |
| Study revisions | New `GET`/`POST /api/projects/<id>/revision-migration`. Run start returns 409 with `revision_migration` when confirmation is needed. Draft resolution returns a `methodology` block, and preflight has `checks.methodology`. | X0 | additive |
| Validation and stress | New fields `storage_invariant_status`, `storage_invariants`, `validation_gate`, `declared_deviations`, `energy_balance.raw_boundary_status` and `publication_blocked`. Status, summaries and replay windows carry `stress_periods`, `shortfall_mwh` and `shortfall_basis`. New `GET /api/runs/<id>/market/stress-events`. | P0-4, P0-9 | additive |
| PSM extensions | New `physical_operating_cost_detail_gbp`, `market_settlement_components_gbp`, `market_rule_diagnostics` and `market_rule_set`, and the cash-flow schema `value.agent-cashflow/v1`. | P0-6, P0-7 | additive |
| Results summary | New `vre_capacity_factor_disclosure` (wind and solar capacity factors shown next to DUKES). | F2 | additive |
| Zonal network | Solver contract v4. New `GF_SOLVER_CONTRACT_UPGRADE_REQUIRED` (409) and `GF_RUN_METHOD_SUPERSEDED`. Boundary marginal values use v2 semantics, and older ledgers read as `not_computed`. New run-time fallback audit read model. | P0-8 | changed |
| Data mapping | Declared CSV columns are read (`GF_DATA_INDEX_COLUMN`, `GF_DATA_AMBIGUOUS_COLUMN`, `GF_DATA_SHORT_SERIES`). EUR prices take an explicit rate, FX basis and price year (`GF_MAPPING_FX`). | P0-5a, P0-9 | changed |
| Market replay and exports (R4-3, S-中1) | Model times are UTC on the fixed 365-day model year and end in `Z` (`2025-07-01T16:00:00Z`; was a naive local-looking `2025-07-01T16:00:00`); a leap model year skips 29 February. `timezone` is `UTC` and `calendar` `fixed_365_day_utc_periods`; new `clock_rule`, `clock_label_corrected` and, for a ledger written before the fix, `clock_note`. CSV/JSONL replay exports end with a `period_start_utc` column; the ZIP manifest has `model_clock`. | R4-3 (A27) | changed |
| Data mapping (R4-3) | Preview: optional `timestamp.date_order` (`auto`/`day_first`/`month_first`) and `model_start_year`; the review adds `clock`, `acknowledgements_required`, and in `timestamp` `data_row`/`csv_line` per problem, `date_order`, `date_order_basis`, `hints` and `coverage`; `validation.timestamp_check`. Commit: optional `acknowledged` (409 `GF_MAPPING_ACKNOWLEDGEMENT` without it when the series is shorter than a model year). `fx_basis` must be `annual average`, `monthly average` or `fixed rate`. Semicolon- or tab-separated uploads are refused with an explanation (`GF_MAPPING_CSV`). | R4-3 (A27) | changed |
| Comparisons | New `metric_delta_gates` ({metric: allowed, reason_code, definitions, reason}) and `withheld_metric_deltas`: annual deltas are gated per metric (AF3-1). `metric_deltas_allowed` still means "every metric". `changed_dimension_details` rows gain `name`. | R2-1 (A23) | additive |
| Methodology record | `universal_accounting_correction_ids` and `correction_ids_in_force` next to `applied_correction_ids` (R3-N6 / O-3); the method identity is unchanged. Catalogue `applies_when` gains `assets_any` (R3-N7). | R2-1 (A23) | additive |
| Parameters | New `methodology.profile`, `market.voll_gbp_per_mwh` (corrected VoLL), `market.dec_multiplier`, `market.policy_support_gbp_per_mwh_by_technology` and `network.inflexible_dec_premium_gbp_per_mwh_by_technology`. | X0, P0-6, P0-8 | additive |

### Methodology profiles, read-time advisories and Study migration (X0)

- `gridform_core/data/methodology/` is the single catalogue. It holds the
  profiles, the corrections per package, the declared deviations and the
  generic advisories. Every Run records its profile in `resolved-run.json`,
  provenance and status. A Run that changes only the profile differs only in
  the `method` comparison dimension.
- Read-time advisories and the shared status presentation are computed when
  a Run is read and never written to disk.
- Study revisions record `fingerprint_basis` and `revision_reason`. Start-run
  no longer silently overwrites a revision.
- The golden families are frozen as doctoral and corrected snapshots. Gates
  `p0_gate quick|full|nightly` run against them, and
  `scripts/golden/delta_report.py` writes the delta report.

### Declared data reading and validation (P0-5a)

- One series reader (`gridform_core/series_reader.py`) reads the declared CSV
  column in every reading mode (P6-01). An implicitly selected integer index
  column is refused.
- Registry-verified GBP1 objects are read with their recorded semantics in
  both profiles: Belgium EUR prices are converted at the documented rate
  (P6-02), flow files are assigned by line identity (P6-03), demand is put on
  the UTC clock (P6-04), and interconnector series follow the run clock
  (P6-24).
- Data-pack validation has three layers (structural, chronology,
  plausibility) and checks per-profile eligibility. The corrected profile
  reads declared resolutions and leap years, and refuses ambiguous columns in
  strict mode.

### Network software correctness and economics (P0-8)

- Assets mapped to several buses are split by share and the shares must sum
  to 1. The DC network expands, solves and aggregates per share (module
  1.1.0).
- Zonal solver contract v4 locks load shedding after the primary stage and
  then locks bid cost numerically; GBP 1 is only an acceptance ceiling (Q5).
  Contracts v2 and v3 can still be read, but upgrading needs explicit action.
- Staged balancing prices decremental bids economically. Equal-price bids are
  accepted pro rata, so renaming an asset no longer moves dispatch.
- Network cost is measured against a network-free LP counterfactual that uses
  one unit-cost table. Boundary marginal values are primary-stage duals: a
  diagnostic, not a zonal price.

### Corrected solar on the module plane, nuclear end month, DUKES hydro, CF disclosure (F2)

- Corrected profile only. Solar: ERA5 horizontal irradiance is split into
  diffuse and beam (Erbs 1982) and transposed (Hay-Davies 1980, albedo 0.2)
  onto a south-facing plane at the latitude-optimal tilt (Jacobson & Jadhav
  2018), with the sun position of each half-hour period, before the PV
  performance ratio 0.83 (decision A13, `p05.solar-plane-of-array`). GBP1
  corrected solar CF 0.0997 -> 0.1065. Synthetic teaching weather (VALUE 101)
  is not transposed.
- Heysham 2 and Torness retire in March 2030 like Heysham 1 and Hartlepool
  (A10). Natural-flow hydro uses the DUKES 2019-2024 load factor 0.3487 with a
  quarterly-derived seasonal shape (A14): GBP1 6.10 TWh against 5.77 TWh.
  The nuclear and hydro reference values are author-reviewed (A14); the wind
  and solar loss factors author-accepted (A9).
- The run results summary carries `vre_capacity_factor_disclosure`: the
  model's pre-curtailment wind and solar capacity factors next to DUKES 6.3
  load factors with the reasons they differ (A9; disclosure only, no
  calibration). GBP1 corrected / DUKES 2020-2024: onshore 1.56, offshore 1.23,
  solar 1.04.

### GBP1 public2 local registration and station nuclear (FX7, A16-6, A16-7)

- The A13 solar transposition model choices are author-approved (A16-6);
  values unchanged.
- GBP1 public2 (`value-uk-open-data-pack-public2`, built locally by
  `scripts/build_value_uk_pack_revision.py`, not published) is registered in
  the local pack-class registry as `scientific_reference`, so the corrected
  profile reads it strictly. The builder (`@v2`; `@v3` since A24-1) also declares the
  three hourly VRE profiles `interval_minutes` 60.
- Corrected profile only (`p05.nuclear-stations-public2`): GBP1 public2 takes
  the VALUE-UK nuclear station policy of GBP1 public1 (five EDF stations with
  their own load factors and month-exact generation ends, Hinkley Point C and
  Sizewell C as exogenous pipeline projects) instead of one aggregate
  `Nuclear` asset at the national fallback 0.723.
- Local one-year acceptance on GBP1 public2: hydro 6.06 TWh (DUKES 6.2
  2019-2024 mean 5.77 TWh, +5 %); nuclear far below Energy Trends 5.1 (see
  Known issues); wind and solar CF above DUKES as disclosed under A9.
  `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md`.

### The extra hour of the hourly solar profile (A24-1, R3-1)

- **Which hour.** R029 public1 and GBP1 public1 share `sa.csv` (sha256
  `15ef49b3...578e`, 8761 values, no timestamps). Against ERA5 2022 ssrd
  (GB mean), rows 0-8759 match the stamps 2022-01-01T00:00Z to
  2022-12-31T23:00Z one to one: correlation 0.956 at lag 0, 0.920 and
  0.921 one hour either way, lag 0 best in all 52 weeks, and no daylight
  row at a dark stamp. The last row (`0`) is the stamp 2023-01-01T00:00Z,
  which an inclusive `2022-01-01 .. 2023-01-01` slice of an hourly
  2022-2023 ERA5 file yields as its 8761st hour.
  `scripts/audit_hourly_solar_profile.py`;
  evidence `docs/dev/p0-reports/r31-solar/sa_8761_evidence.json`.
- **Local revisions (not published).** `scripts/build_value_uk_pack_revision.py@v3`
  writes the first 8760 lines byte for byte (sha256 `ae4b9577...b306`) and
  records the dropped row in the binding (`row_revision`: source sha256,
  row 8761, value, ERA5 stamp, reason, evidence). `--pack r029-public2`
  builds R029 public2 (`value-uk-calendar-vx-trade001-public2`): R029
  public1 with that object revised and the three VRE profiles declared
  `interval_minutes` 60; every other file is the public1 file. It is
  registered locally as `scientific_reference` and named next to R029 in
  the data corrections' `applies_when`. GBP1 public2 binds the same revised
  object.
- **No number changes.** Every existing reading used only the first 8760
  rows (the doctoral hourly repeat, the declared clock, the kernel's VRE-cap
  bisection, where the last row is a zero), so the doctoral reading of the
  public1 packs and the GBP1 public2 results are unchanged. The corrected
  profile now runs R029 (public2) with the default modules (golden C10).
- **Not changed.** ERA5 stamps ssrd at the end of the accumulated hour, so
  by interval the profile still lags the half-hour clock by one hour
  (finding P6-06 for the CSV profiles, which feed the VRE expansion cap and
  the dispatch of packs without NetCDF weather). Re-labelling it would be a
  method change and is left to the author.

### Result views read what was recorded (P0-9 close)

- Stress events (decision A2) are visible end to end: the Run context bar's
  Stress events field and notice, the Market replay window card (`Shortfall`,
  stress periods) and a 4 px amber band on the dispatch chart, and a new
  full-year list in Market replay (`GET /api/runs/{run}/market/stress-events`,
  paged by numeric start period, with Replay). A shortfall of a Run that
  predates exact stress accounting is shown as a lower bound `≥ x MWh`.
- Validation gates: any failed gate (run invariants, energy balance, storage
  limits) raises `Validation gate failed: {gates}`; a corrected Run blocked by
  a gate shows `Annual results not published` instead of totals;
  `reproduction_conformant` is a teal `● Conformant`; Inspect shows the raw
  boundary residuals.
- State words: `Withheld` is reserved for the Q14 rule on doctoral
  reproduction runs; partial, running and stopped years read
  `Partial year · n%`, `Running` and `Stopped · n%`. A Run cancelled or failed
  before a declared year finished is `unavailable`, not a red `invalid`.
- Labels state their basis: the average system cost reads `/MWh served` (CEM
  ledger) or `/MWh generated` (legacy total); the native operating cost now
  reports that it includes VoLL (P0-6) with the recorded amount; corrected VRE
  columns read `Non-VRE spill` and `VRE curtailment` with the event basis
  `corrected_unused_vre`.
- Network & redispatch shows the run-time fallback audit ("Spatially
  indicative: …"). Isolated VRE points are drawn as dots; event groups without
  events say `No events recorded`.
- CSV mapping accepts EUR prices with an explicit EUR per GBP rate, FX basis
  and price year, and previews the original value beside the converted one.

### Corrected-profile weather, VRE losses and firm availability (P0-5b)

- Corrected profile only (the doctoral reproduction keeps 0.6.0-alpha.2
  inputs): ERA5 accumulated irradiance is used for the hour it accumulates
  (weather v2, P6-06; GBP1 London solar centroid 12.97 -> 11.97 UTC); wind
  and solar are multiplied by cited literature loss factors (onshore 0.903,
  offshore 0.815, PV performance ratio 0.83; P6-08) without any calibration
  to statistical load factors; nuclear stations carry load factors and a
  month-exact generation end, natural-flow hydro an annual load factor
  (P5-09, P5-10).  The reference values were PENDING AUTHOR REVIEW at this
  step; the author reviewed the nuclear and hydro values in decision A14 (see
  F2 above).
- The retained kernel receives the same per-site and firm availability arrays
  as the canonical adapter; corrected interconnector offers keep negative
  prices.  In both profiles the kernel's weather cache is keyed by its files
  (P7-02).
- `scripts/build_value_uk_pack_revision.py` builds GBP1 public2 locally
  (demand and interconnectors re-bound to the approved R029 objects);
  `scripts/audit_boundary_flow_sign.py` marks `flow_sign` verified only
  against an author-supplied reference.  Nothing is uploaded.
- Read-time advisories flag runs on the ERA5 research packs made without
  these corrections.

### External modules and extensions cannot stop VALUE (P0-2)

- Built-in modules stay fail-closed; locally installed (external) module and
  extension manifests are fail-isolated.  A manifest that cannot be read, an
  implementation that raises anything while importing (including
  `SystemExit`), an external ID or namespace that collides with another
  external entry (every party is quarantined, there is no implicit winner) or
  with a built-in (only the external entry is quarantined) is listed as
  quarantined in memory; nothing is written into `modules/`.  A failed import
  is not retried in the same process until `POST /api/modules/rescan`.
- Install and enable refuse namespace conflicts before writing anything
  (`GF_EXTENSION_NAMESPACE_COLLISION`, naming the real owner) and then check
  the registry twice — in process and in a fresh, worker-like Python process
  — rolling the change back byte for byte if either refuses
  (`GF_EXTENSION_REGISTRY_CONFLICT`, `GF_MODULE_REGISTRY_CONFLICT`,
  `GF_MODULE_PROBE_FAILED`, `GF_MODULE_PROBE_TIMEOUT`).  Each install or
  enable takes about 1–2 s longer.  Disabling is always possible, also for a
  schema-drifted extension and for a quarantined entry that saved Studies
  still name (active runs still block it).
- The module catalogue is built on first use, never at import;
  `DATASET_SLOTS` moved to `gridform_core/dataset_slots.py` (re-exported by
  `gridform_core.catalog`).  A worker no longer imports the catalogue, so a
  broken module fails the run with `GF_MODULE_QUARANTINED` instead of leaving
  it queued.  Draft resolution, preflight and Study derivation report
  `GF_STUDY_MODULE_QUARANTINED` / `GF_PREFLIGHT_MODULE_QUARANTINED` only when
  the Study selects quarantined code; otherwise they add one warning.
  `preflight.json` records `checks.module_quarantine` and
  `checks.external_code`.
- Offline self-rescue without importing any installed code:
  `python -m gridform_core.module_recovery list | disable module|extension <id> |
  park-manifest module|extension <file> | park-installation module|extension <id> [<version>] |
  verify`; the user guide ("Offline module recovery") gives the command for
  an installed VALUE (bundled interpreter, `-B -s`, `PYTHONPATH=<prefix>/app`,
  `--modules-root <prefix>/state/modules`).  A damaged installation record
  (which refuses every run start) is reported as
  `GF_MODULE_INSTALL_RECORD_INVALID` and parked with `park-installation`.
- **API contract changes (additive):** `/api/health` reports
  `status: degraded` with `degraded_reasons [{code, count}]`
  (`GF_MODULE_IMPORT_FAILED`, `GF_EXTENSION_NAMESPACE_COLLISION`,
  `GF_MODULE_CATALOG_STALE`, …); `/api/workspace`, `/api/modules` and
  `/api/extensions` carry `module_quarantine`; new `POST /api/modules/rescan`;
  lifecycle conflicts are 409 (were 400), probe timeout 504, a stale
  catalogue 503 on run start; a lifecycle change while runs are pending is
  409 `GF_MODULE_LIFECYCLE_RUNS_PENDING` until confirmed with
  `{"confirm_pending_runs": true}` (JSON) or
  `X-VALUE-Confirm-Pending-Runs: acknowledged` (ZIP upload); every error
  answer carries `error_code`.  Library: `workspace_registry(...,
  strict=False)` quarantines by default (`strict=True` for release gates);
  catalogue constants are lazy attributes.
- Scientific identity is unchanged: for VALUE 101 the module graph
  (`graph_sha256` e6ff10cd…0ee9) and the Study revision (`revision_sha256`
  8d348df4…626d) are identical before and after this change, and the
  registry content and order are unchanged for every data directory that
  loaded before.

### Local API security boundary (P0-1)

- The browser talks only to the UI origin. `scripts/value-ui-gateway.mjs`
  (mounted by `serve-value-ui.mjs` and, for development, by `vite.config.ts`)
  answers only `127.0.0.1:<port>`/`localhost:<port>` (421 otherwise), refuses
  cross-site `/api` requests and writes without the page Origin (403), needs
  a Content-Length on POST (411), sends a per-response CSP nonce,
  `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy: no-referrer`, COOP/CORP, and forwards `/api` with the
  API session.  A foreign Host on a page gets the "Open VALUE from its
  launcher" explanation.
- The API generates a session token per process and writes it only to
  `<VALUE_DATA_HOME>/runtime/api-session-<port>.json` (0700/0600, atomic;
  removed on exit only by its owner).  Every request passes
  `backend/api_security.evaluate`: Host 421, any Origin 403
  `GF_BROWSER_ORIGIN_REJECTED`, cross-site Sec-Fetch-Site 403, invalid
  Content-Length 400, chunked POST 411, missing/wrong session 403
  `GF_SESSION_REQUIRED`/`GF_SESSION_INVALID`, form-style or missing POST
  Content-Type 415 `GF_CONTENT_TYPE_REJECTED`.
- Launchers pass `--api-origin` after `--port` (process patterns unchanged),
  never the token, and wait until the gateway reaches the API.
- Frontend calls same-origin `/api`; `NEXT_PUBLIC_VALUE_API_ORIGIN` is gone;
  pages are rendered per request (`force-dynamic`).
- `scripts/verify_local_security_boundary.py` probes an installation.
- **API contract changes (breaking for direct clients):** no CORS at all;
  new request header `X-VALUE-Session` (scripts:
  `backend.api_session.authorized_headers`); new response header
  `X-VALUE-Error-Code`; new statuses 421, 403, 415, 411, 400 and, at the
  gateway, 502 `GF_GATEWAY_SESSION_UNAVAILABLE`/`GF_GATEWAY_SESSION_MISMATCH`/
  `GF_GATEWAY_UPSTREAM_UNAVAILABLE`; `GET /api/health` without a session
  returns only `ok, service, version, python,
  authoritative_runtime_compatible, session_required, status,
  degraded_reasons`; the comparison CSV is an attachment.  The backend source
  hash is part of the execution identity, so Runs left unfinished by an
  earlier version cannot be resumed after the upgrade.
- `SECURITY.md` names VALUE, points to the VALUE advisory form and states the
  single-user host assumption; `X-VALUE-Executable-Trust` is documented as
  informed consent, not a security control.

### Run lifecycle (P0-3)

- `status.json` has a single writer API (`backend/lifecycle/run_status.py`):
  per-run file lock, field-level merges, a consecutive `lifecycle_history`,
  late worker writes recorded in `late-worker-*.json` without touching
  sealed artifacts. Cancellation is the `cancel-request.json` file only.
- Workers start through `python -m backend.worker_entry`, take a lease
  (`worker.lock`) before heavy imports, run detached from the backend and
  are reaped, supervised and reconciled at start-up (`GF_WORKER_EXITED`,
  `GF_WORKER_LOST`, `GF_WORKER_IMPORT_FAILED`, `GF_WORKER_TERMINATED`,
  `GF_WORKER_SPAWN_FAILED`); `POST /api/runs/<id>/mark-lost`; one backend
  per data directory (`.backend.lock`, exit code 3).
- Delete moves the run to the trash before recording `deleting`; runs a
  previous version left in `deleting` are repaired at start-up.
- Disk quota counts physical bytes once per inode and reservations only
  for the unwritten output of active runs; one rule for reservation,
  preflight, snapshot readiness and resume; reservation lock is a flock
  (timeout 503); reservation report v2.
- Every API request has one exception boundary (`_dispatch`); listings
  isolate bad records instead of failing.
- Launchers start every interpreter with `-B -s -X pycache_prefix=<fresh
  directory>`; stray `__pycache__` bytecode is quarantined instead of
  blocking start/diagnose (`diagnose-value --repair-bytecode`).
- API additions: `worker_liveness`, `worker`, `cancel_requested_at`,
  `persisted_status`; `worker.json` v2.

### Investment decisions, storage headroom and cost ledger (P0-7)

- Thermal investment net revenue restored in both profiles (decision A4,
  `p07.thermal-net-revenue`): gas and biomass net generated MWh x (generation
  + fuel + carbon + unit-time cost) from their income; VRE and storage keep
  gross revenue as profit. A CCGT paid exactly its marginal cost no longer
  expands (HEAD built 10.95 MW per 100 MW). PSMs publish
  `value.agent-cashflow/v1`; agent-investment 3.0.0 fails closed for a
  thermal group without it. The doctoral two-year golden (D4) was
  re-baselined once with a numeric report.
- Corrected profile: storage headroom from the post-charge surplus (P5-01;
  it was always zero) with a full-year guard, and one shared power-battery
  pool (P5-02, read as "the cap was counted three times";
  withdrawn by decision A20 in R1-3, see below). value-storage-expansion-policy
  5.0.0. The doctoral profile keeps both 0.6.0-alpha.2 behaviours.
- Cost ledger v2: VRE and storage fixed OPEX is a memo, not part of the
  headline (decision A7, both profiles); the corrected headline excludes the
  run-of-river hydro compatibility capital (P4-03), shown as a memo row on the
  Runs page. Perfect foresight books thermal FOM from `annual_fixed_opex_gbp`
  (the key it read never existed).
- Investment decisions stay undiscounted in constant base-year money (decision
  A6, P4-02 out of scope); see `docs/methodology/drafts/0.4/p07_investment.md`.

### Default PSM clearing and storage dispatch (P0-6)

- `value-bid-at-cost-psm` 6.0.0 runs one of two market rule sets derived from
  the methodology catalogue (`corrections/p06.json`).  The doctoral
  reproduction profile keeps the 0.6.0-alpha.2 dispatch bit for bit and
  reports its known deviations in `market_rule_diagnostics`.  The default
  (corrected) profile clears with: D1-surplus (VRE surplus rebuilt per source
  and kept on the books; must-run surplus never generated twice), storage
  after generation in the same 0.01 GBP/MWh band, an avoided-cost
  down-regulation stack, one net storage position per period (shared rated
  power, buy-back before charging), per-period storage fees, no pre-clearing
  VRE electrolysis, cycle-only dynamic storage bids (pumped hydro and
  hydrogen bid 0) and uniform-price settlement.  Saved Studies on the
  corrected profile need method confirmation (Q13).
- Realisation is unchanged in both profiles (decision A2): a period whose
  ahead stage cannot meet the forecast keeps its shortfall, booked as a
  stress event.
- Operating cost of the default PSM (both profiles) is physical: generation
  at running cost, imports, start-up adder, unserved energy x VoLL (17,000
  in both profiles since FX5; 8000 doctoral and `market.voll_gbp_per_mwh`
  corrected before) and storage cycle wear,
  which was previously counted twice.  New extensions
  `physical_operating_cost_detail_gbp`, `market_settlement_components_gbp`,
  `market_rule_diagnostics`, `market_rule_set`.
- Corrected ledgers declare `native_corrected_full_node_v1`: `vre_accepted`
  is gross VRE output, `curtailed` is VRE availability minus that output,
  `excess` is the non-VRE spill (declared in the ledger semantic metadata).
- `dynamic-annual-storage-cost` 2.0.0 (bid basis owned by the PSM rule set);
  `user-formula-storage-cost` stays 1.0.0; storage recovery adequacy v2.
- Per-period source flows (RealisationLog) stay in memory only; persisting
  them is deferred to ledger v9 (P1).

### Storage offers in the market ledger (post-UAT M-D1)

- `value-bid-at-cost-psm` 6.1.0 (code identity, no opt-in): the full market
  trace writes the new accounting table `storage_orders`, one row per storage
  tranche offer of the ahead and balancing stages, accepted or not, at its
  real price (storage cost module bid x bid multiplier), with the energy it
  delivered and a link to the clearing declaration.  The battery's `orders`
  row (`final_dispatch`, price 0.0) is unchanged.  Dispatch is unchanged in
  both profiles; golden D3 and C3 gained an accounting revision
  (`fx4.storage-offer-ledger`).

### Value of lost load 17,000 GBP/MWh in both profiles (A16-5)

- VoLL is the author's 17,000 GBP/MWh (8,500 GBP per MW and half-hour
  period) everywhere (`gridform_core/voll.py`).  Doctoral reproduction: the
  thesis cost-ledger constant 8,000 (`case3.py` / `modular_case3.py`
  `DEFICIT_VALUE_PER_MWH`, the native doctoral rule set, now
  `reliability_voll = constant_17000`, and the original-thesis system-cost
  view) becomes 17,000.  VoLL enters only the cost accounts there, so this is
  a universal accounting correction (`fx5.voll-17000`, Q12): the doctoral
  trajectory is bit-identical.  Corrected profile and every module that reads
  `market.voll_gbp_per_mwh`: the registry default is 17,000 instead of 10,000
  (zonal redispatch on the VALUE UK study already pinned 17,000).
- Method upgrades with explicit confirmation (Q13): `value-bid-at-cost-psm`
  6.2.0, `value-perfect-foresight-lp` 1.1.0, `value-staged-bid-at-cost-psm`
  1.4.0, `value-reference-dc-network` 1.2.0, `value-doctoral-national-psm`
  0.3.0.  `value-zonal-redispatch-balancing` keeps 4.0.0 (code and solver
  contract unchanged; a zonal Study always runs the staged PSM).
- A saved Study whose derived market configuration still carries the old
  default 10,000 without an explicit parameter is re-projected to 17,000
  instead of being refused; an explicit `market.voll_gbp_per_mwh` stays
  authoritative.
- VALUE 101 golden cases and GBP1 D5 record no blackout, so their headline
  cost is unchanged; only the VoLL value and its basis label in
  `physical_operating_cost_detail_gbp` change (accounting revisions of
  D1–D5 and C1–C6).

### Interconnector imports in the day-ahead clearing (A16-2, corrected profile)

- Four-role finding S-D3: a positive "import availability" produced no
  import in a one-day Run.  The retained default PSM offers interconnector
  imports only in the balancing stage, for the upward requirement left when
  realised demand exceeds the day-ahead schedule; the day-ahead clearing never
  receives a connection.  The doctoral reproduction profile keeps this thesis
  rule bit for bit (it is where the GBP1 doctoral imports, 0.336 TWh in the
  first model year, come from).
- Corrected profile (`fx6.day-ahead-interconnector-imports`, rule-set field
  `interconnector_import_stage`): every connection with a positive transfer
  constraint offers its available import capacity to the day-ahead clearing
  at the period's counterparty price (times the bid multiplier), in the same
  merit order as domestic generation (generation, then an import, then
  storage at an equal 0.01 GBP/MWh band).  The balancing stage offers only the
  import capacity the day-ahead schedule left, so no MW is bought twice.  An
  accepted day-ahead import can be reduced in the curtailment branch at its
  avoided import price (no curtailment payment).  Exports are unchanged.
- Ledger: the ahead clearing declarations carry `ahead:i:` import offers
  (`resource_kind` import, with the counterparty price), and the `orders`
  table books each import offer as an `ahead_offer` row (offered capacity,
  accepted import, status) instead of a 0.0-priced `final_dispatch` row; the
  market replay shows the import in the ahead supply curve.  The import
  payment diagnostic covers day-ahead and balancing imports.
- `value-bid-at-cost-psm` 6.2.0 → 6.3.0 with `requires_user_opt_in` (Q13):
  saved corrected Studies need explicit confirmation.  The data roles
  `market.<country>.profile` are labelled "interconnector availability
  (+ import / - export)".
- VALUE 101: the France offer (12 MW at 82 GBP/MWh) is dearer than the CCGT
  (66.5 GBP/MWh with its start-up adder), so it is offered and rejected in
  every period; dispatch, prices and costs of C1–C6 are unchanged, and C1–C4
  gained a revision for the new offer rows.

### Nuclear in service at the start of the year (A18, corrected profile)

- FX7 found that the default PSM starts every model year with no unit
  running: a nuclear unit adds its start-up cost (500 GBP/MWh on GBP1) to its
  day-ahead offer until it is first accepted, and then stays on to the year
  end.  On the local GBP1 public2 corrected run (2025) nuclear entered only
  on 12 December and generated 2.02 TWh against about 37.3 TWh supplied
  (Energy Trends 5.1).
- Corrected profile (`fx8.nuclear-in-service-at-start`, rule-set field
  `nuclear_initial_state = in_service_at_start`): every nuclear unit counts as
  running before the first period of each model year, so its first offer
  carries no start-up cost and it runs as baseload at its station
  availability.  A unit that was not accepted in a period (refuelling,
  outage, zero availability or not cleared) pays the start-up cost once, in
  its offer and in the physical start-up term, when it restarts.  Gas and
  biomass keep the thesis rule.
- The doctoral reproduction profile keeps the thesis rule bit for bit
  (`off_until_accepted`; D1-D5 unchanged).  Doctoral Runs carry the read-time
  advisory of the correction (severity high), which discloses the nuclear
  path dependency (A15).
- `value-bid-at-cost-psm` 6.3.0 → 6.4.0 with `requires_user_opt_in` (Q13).
- GBP1 public2 (local, not published) 2025, corrected: nuclear 2.02 → 38.26
  TWh (+2.5 % against Energy Trends 5.1, every period from period 0), CCGT
  101.4 → 67.5 TWh, curtailment 0.43 → 1.74 TWh, exports 0.41 → 1.51 TWh,
  mean period price 24.30 → 16.23 GBP/MWh, headline system cost −1,830.7
  GBP m, emissions −13.0 MtCO2.  New golden case C9 (research pack, tier
  full) records the run before and after A18; numeric report
  `docs/dev/p0-reports/fx8-golden/C9-r1.json`.  VALUE 101 has no nuclear, so
  C1–C8 change only in identity.

### Economic down-regulation order: restart cost against avoided cost (A19/A22, corrected profile)

- P0-6 S7 had read finding P3-03 as "always reduce gas and biomass before
  curtailing VRE".  Decision A19 withdrew that: whether reducing thermal
  output is cheaper than curtailing wind depends on the restart cost as well
  as on the fuel, carbon and variable cost saved, and neither side may be
  assumed dearer.
- Corrected profile (`r12.economic-downward-order`, rule-set field
  `downward_restart_economics = restart_cost_vs_avoided_cost_v1`): in the
  curtailment branch a gas or biomass row is split at minimum stable
  generation (50 % CCGT/OCGT, 35 % biomass, of its accepted output).  The
  running range above it is reduced at its avoided cost before VRE (no
  restart).  Below it, shutting units down saves `a(H) = c - S(H)/(m H)` per MWh
  (m = minimum stable fraction, since removing 1 MW of output shuts 1/m MW
  of capacity; restart cost S per MW of capacity: CCGT 110/130/150 GBP/MW hot/warm/cold, OCGT 170, biomass
  125; H = expected downtime from the day-ahead forecast surplus run): before
  VRE when `a > 0`, after VRE otherwise, and only as a last resort when H is
  below the minimum down time (6 h / 0.5 h / 6 h).  Values: reference
  statistics section 4, author-reviewed in A22, stored in
  `gridform_core/data/thermal/value_thermal_restart_v1.json`.  The restart
  cost ranks the stack only; cost accounts are unchanged.
- Every corrected market year records
  `extensions.downward_restart_economics` (MWh by segment, periods, mean H).
- The doctoral reproduction profile keeps the thesis curtail-cost order bit
  for bit (D1-D5 unchanged); doctoral Runs carry the read-time advisory of
  the correction (severity medium).
- `value-bid-at-cost-psm` 6.4.0 → 6.5.0 with `requires_user_opt_in` (Q13).
- Effect on the reference runs is small, because down regulation is rarely
  needed while gas is scheduled day-ahead.  VALUE 101 two_year (C5/C6): one
  period of 2025 changes (CCGT +0.16 MWh, curtailment +0.16 MWh, emissions
  +0.06 tCO2, system cost +GBP 10.4); 2026 is unchanged.  GBP1 public2 2025
  (local, C9): dispatch, curtailment (1.735 TWh), CCGT (67.53 TWh),
  emissions and costs are unchanged; of the 357 down-regulation periods only
  2 reduce gas (190.7 MWh, inside the running range), and no shutdown
  segment is reached.  Golden: C1-C4 and C9 gain the new extension columns
  only; C5/C6 one period; numeric reports
  `docs/dev/p0-reports/r12-golden/`.

### Economic down-regulation order in the network models (A24-3, corrected profile)

- The staged / zonal balancing (P0-8b rule set `network-economic-v1`)
  offered a gas or biomass unit's whole ahead schedule as one dec at its
  avoided cost `c > 0`, so every such unit was reduced to zero before any
  merchant VRE (dec price 0) was curtailed: the "fuel before VRE" order that
  A19 withdrew for the default PSM.  Decision A24 item (3) applies A19, A22
  and A22a to the network models.
- Rule set `network-economic-v2` (`r32.network-economic-downward-order`): a
  gas (CCGT, OCGT) or biomass dec is split at minimum stable generation (50 /
  50 / 35 % of its ahead schedule).  The running range keeps the price `c`
  and is reduced before VRE.  The shutdown segment (bid
  `...:down-shutdown:<asset>`) is priced at the net saving
  `a(H) = c - S(H)/(m H)` (same restart table as R1-2) and competes with VRE
  on price, after VRE at an equal band; when the expected downtime H is below
  the minimum down time (6 h / 0.5 h / 6 h) it is a last resort, priced 0.01
  below every other dec of the period.  H = (1 + consecutive later periods
  whose forecast demand is covered by declared VRE and nuclear availability) x
  period hours.  Two dec classes join the shared order (`fuel_shutdown` after
  VRE, `fuel_shutdown_last_resort` last; physical tie weights 3.5 and 5 in the
  zonal LP and in the PuLP/CBC oracle).
- Every staged market year records `extensions.downward_restart_economics`
  (`value.network-downward-restart-economics/v1`: down-regulation periods,
  mean H, dec MWh and periods by segment).
- `value-staged-bid-at-cost-psm` 1.4.0 → 1.5.0 with `requires_user_opt_in`
  (Q13); copperplate 1.1.0 and zonal 4.0.0 unchanged (they read the classes
  from the shared table).  The doctoral profile cannot select these modules
  (Q3).
- Effect on the reference cases: C7 (copperplate smoke) has no balancing dec;
  in C8 (zonal day) the 42 down-regulation periods all curtail VRE and the
  CCGT is never balanced down, as before, so dispatch and costs move only by
  solver tolerance.  Toy cases (staged copperplate, a two-zone LP checked
  against the CBC oracle, a live staged zonal Run) reproduce the R1-2
  examples: OCGT at H = 5 h shuts before wind, at H = 3 h wind is curtailed
  first.

### Restart costs in the model's price base; biomass disclosure (A24-4, A24-2)

- A24-4 (corrected profile, `r33.restart-cost-price-base-2025`): the restart
  costs of `gridform_core/data/thermal/value_thermal_restart_v1.json` were
  author-reviewed in 2024 GBP (A22). They are compared with fuel, carbon and
  variable costs, which are start-year money (A6); every shipped study starts
  in 2025, and the dated cost inputs are declared in 2025 GBP (storage
  catalogue `currency_base_year`, pumped-hydro CAPEX, policy budgets). The
  table now uses the A22 values restated by the UK CPI (ONS D7BT annual
  averages 138.4 / 133.9 = 1.0336, rounded to GBP 0.1): CCGT 113.7 / 134.4 /
  155.0 GBP/MW hot / warm / cold, OCGT 175.7, biomass 129.2. It keeps the
  2024 values, the index values, the factor and the source (`price_base`),
  and the loader refuses a table whose values do not match them. The 2025
  index value still has to be checked once against the ONS series (reference
  statistics 4.2a). Minimum stable generation, minimum down times and the
  rule are unchanged; break-even downtimes rise by 3.4 % (CCGT 4.13 h, OCGT
  4.69 h, biomass 4.34 h at the thesis costs).
- `value-bid-at-cost-psm` 6.5.0 → 6.6.0 and `value-staged-bid-at-cost-psm`
  1.5.0 → 1.6.0, both with `requires_user_opt_in` (Q13). The doctoral profile
  does not use the table.
- Effect: none on the reference runs except C8 (the CCGT last-resort dec
  price), because no priced shutdown segment is reached in them.
- A24-2 (both profiles, disclosure only): Runs whose frozen fleet contains
  biomass carry the read-time advisory `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED`
  (severity medium, generic predicate `fleet_assets`): biomass has no CfD/ROC
  support revenue, offers at its full fuel and carbon cost and is rarely
  dispatched. Behaviour and results are unchanged. Methodology draft
  `docs/methodology/drafts/0.4/r33_biomass_support_disclosure.md`; model card
  limitation list.

### Per-type power-battery expansion caps (A20, corrected profile)

- P0-7 S7 had read finding P5-02 ("each power battery receives the whole
  0.2 x power room, three times the documented cap") as a defect and made the
  1C, 0.5C and 0.25C batteries share one pool.  Decision A20 withdrew that:
  the three types serve different durations, and giving each its own
  `expansion.storage_cap_fraction x power_room` (0.2) is the thesis design;
  the fraction is already a reduced share.
- Corrected profile (`r13.per-type-battery-caps`): the storage headroom row
  gives each power battery type its own cap and declares no shared pool;
  agent-investment caps each type separately.  The P5-01 leftover headroom
  (`p07.storage-leftover-headroom`) is unchanged.  `p07.power-battery-pool`
  stays in the catalogue, without an advisory, so that Runs made between
  P0-7 and R1-3 keep a readable identity; no profile pools any more, and a
  per-type run that receives a pooled headroom row is refused.
- `value-storage-expansion-policy` 5.0.0 → 5.1.0 with `requires_user_opt_in`
  (Q13).  The doctoral reproduction profile is unchanged (D1-D5 gated 0);
  doctoral Runs lose the medium advisory "Power-battery cap counted three
  times".
- Effect on the reference runs: none on proposals or capacities.  The pool
  was never binding on VALUE 101 two_year (C5/C6) or on GBP1 public2 2025
  (C9), whose battery requests stayed below it; the golden revisions change
  only the headroom and investment evidence columns.

### Three thesis-kernel errors corrected in both profiles (A26, R4-1)

The website methodology describes the published VALUE model, not the
thesis, so three implementation errors of the retained thesis kernel are
corrected in both profiles (universal corrections). The thesis settings
(wind curtailed first at zero cost, bid rules, no loss factors, full
availability, the original data readings) are unchanged.

- **Down regulation taken once** (`r41.down-regulation-taken-once`, A15): a
  hydro, biomass or thermal unit that met the remaining down-regulation
  requirement of the curtailment branch did not clear it, so the same amount
  was reduced again from later offers (usually wind); it is now cleared.
- **One storage position per period** (`p06.storage-net-per-period`, now
  universal; formerly declared deviation DEV-STO-01): the clearing stages
  share a store's rated power; a store that discharged reduces that discharge
  before it can charge; a store that charged offers no discharge. The
  absorbed surplus is booked as curtailed (forecast surplus) or re-dispatched
  (must-run or VRE surplus, VRE then entering S as VRE output).
  `storage_position` is no longer a switch of the market rule sets.
- **Must-run surplus counted once** (`r41.must-run-surplus-counted-once`,
  formerly DEV-BAL-04): must-run nuclear surplus that serves the balancing
  requirement is neither generated nor paid a second time;
  `non_vre_double_counted_mwh` is zero.
- **Declared deviations.** DEV-BAL-04 and DEV-STO-01 and their gate matchers
  are withdrawn (`declared_deviations.json` keeps them under `withdrawn` so
  the evidence of earlier Runs stays readable); the drafted DEV-BAL-05 was
  never registered. No remaining declared deviation explains a gate failure.
- **Advisories.** Runs of the doctoral profile made before R4-1 (and Runs
  without a recorded profile) carry the new advisories; `applies_when` has a
  new key `profiles_any`. Corrected Runs never ran the old behaviour and get
  none.
- **Numbers (golden D3-D5).** GBP1 public1 2025, doctoral: surplus
  conservation passes (563 failing rows before), the storage gate passes
  (15,653 store-periods charged and discharged before), unserved energy
  300,855 -> 78,810 MWh, stress periods 890 -> 487, storage charge/discharge
  5.05/3.66 -> 2.42/1.75 TWh, operating cost GBP 4,317.5 m -> 4,287.0 m,
  direct emissions 30.91 -> 30.68 MtCO2. VALUE 101 day and two years: the
  storage gate passes (10 and 9,343 store-periods before). All three now
  publish annual results (Q14). Corrected golden cases are unchanged in the
  gated zones.
- **Saved Studies.** `value-bid-at-cost-psm` 6.6.0 -> 6.7.0 with
  `requires_user_opt_in`; the applied-corrections identity of both profiles
  changes, so every saved Study asks for confirmation (Q13).
- **Golden tooling.** The 96-period synthetic reproduction golden may
  re-baseline its trajectory once for the A26 kernel corrections
  (`capture_native_reproduction_golden.py revise --trajectory`, revision 4;
  revision 0 keeps the 0.6.0-alpha.2 columns); the P0-4 per-table fixture
  was re-captured once.

### R1 retest fixes, backend (R2-1, DECISIONS A23)

- **Unchanged saves stay unchanged (R3-N1).** A Study is saved with its
  numbers in the registry type (the VoLL of `market_configuration` and
  float-typed parameters as floats), so an editor that sends `17000` for
  `17000.0` appends no revision; comparisons compare recorded values by
  number, so `17000.0` and `17000` are no configuration change.
- **Annual deltas per metric (AF3-1).** A comparison withholds only the
  deltas whose own evidence is missing: the three VRE-curtailment metrics
  need matching reconciled curtailment attribution, cost metrics matching
  cost definitions, carbon its carbon definition. VALUE 101 annual
  comparisons (copperplate modules, no counterfactual snapshot) now show
  cost and carbon differences.
- **Corrections in force in the Run record (R3-N6 / O-3).** The Run's
  methodology record lists the universal accounting corrections that are
  not in the catalogue (`fx5.voll-17000`, `fx4.*`, `p04.*`,
  `p06.physical-operating-cost`, `p07.cost-ledger-v2`) and the union with
  the catalogue ids.
- **Advisories by asset presence (R3-N7).** Advisories about nuclear or
  natural-flow hydro apply only to Runs whose frozen fleet has such an
  asset; a VALUE 101 Run no longer lists the nuclear advisories.
- **p06 advisory wording (R3-N2).** The advisory of
  `p06.avoided-cost-downward-order` names only the bookkeeping defects;
  curtailing VRE first is the thesis rule, not a defect (A19).
- **Restart table text (A22a).** `rule.shutdown_segment` states
  `a(H) = c - S(H)/(m H)`, as the code computes since R1-2.
- Low items: an in-place module edit is named by its source hash and is a
  controlled storage-cost change (R3M-6); no doubled parenthesis in the
  comparison sentence (AF3-2); the source-change warning of a quarantined
  module (R3M-5); the mapping editor lists empty, non-finite and negative
  cells in one round and the API takes the editor's price-year range
  (L-1, L-2, L-3, L-5).

### Swap-data fixes: model clock, date order, coverage (R4-3, DECISIONS A27)

- **One model clock (S-中1).** The model always ran on UTC half-hours of a
  fixed 365-day year; the market ledger labelled that clock
  `Europe/London`, so replay times in summer looked an hour early against
  local-time input. The ledger now records `UTC` /
  `fixed_365_day_utc_periods` (`gridform_core/model_clock.py`), read
  models and exports write UTC times with `Z` and skip 29 February in a
  leap model year, and the UI labels them `UTC model time`. A ledger
  written before the fix is read on the UTC clock with a note, and resumes
  with its old label.
- **Clock notes say what the reader does (S-中2).** The pack validation and
  the mapping review describe the reader's actual branch: hourly values are
  used for two half-hour periods, 29 February is removed, a series longer
  than a year is truncated, a shorter one is filled by repeating it from
  its start (with the number of periods and days). It no longer says
  "repeats it cyclically" for every length.
- **Day/month dates (S-中3).** `02/01/2025` is read as 2 January when any
  row shows a day above 12 (or when the user chooses DD/MM/YYYY); the
  report names the order and why, and a wrong order is hinted at instead of
  154 month-long "gaps".
- **Coverage and data year (S-低2, report 7.3).** The timestamp report
  gives the span in days and the calendar year of the data; a series
  shorter than a model year needs an explicit confirmation before commit,
  and a data year other than the Study's first model year is noted.
- Low items: semicolon/tab exports get a plain explanation (S-低1); the
  timestamp table and the cell errors both give the data row and the CSV
  line (S-低3); the whole-file report includes the timestamp check
  (S-低4); the role card shows the EUR rate, FX basis and price year, and
  a read-only pack's roles can still be browsed (S-低5); `fx_basis` is one
  of the editor's three values and a price year other than the model's
  2025 price base is noted (S-低6); the single-change comparison sentence
  no longer mentions a storage-cost experiment, and a missing curtailment
  metric reads `Unavailable` on Compare as on Runs (S-低7).

### Scientific validation recomputed and gated (P0-4)

- No more literal "passed": stage parity v3 and scientific validation v2 are
  recomputed from checks executed on the run (contract checks, run
  invariants, the read-only energy-balance oracle).  A report that ran no
  check is `not_evaluated`.  Pre-fix runs keep their files; a `passed` that
  rests on a non-v2 report is shown as `superseded_pre_fix` and the ledger is
  re-checked read-only when the run is read.
- The default PSM declares its energy-balance boundary
  (`default_psm_surplus_node_v1` doctoral, `native_corrected_full_node_v1`
  corrected), records surplus routing per source and a per-asset storage
  audit, and its compatibility adjustment absorbs numerical noise only (it
  used to close every residual, so the adjusted residual was zero by
  construction).
- Decision A2: dispatch is unchanged when the ahead stage cannot meet the
  forecast; both profiles record stress events (per-period shortfall, events,
  annual summary) and book the shortfall as unserved energy in the
  energy-balance account.  Run status, summaries and market-replay windows
  carry `stress_periods`, `shortfall_mwh` and `shortfall_basis`; on a declared
  full-node boundary the shortfall now equals the booked unserved energy
  (it was a lower bound).
- Validation gates (P0-4 S7): run invariants, the energy-balance account and
  the storage throughput invariants (rated power, no charge and discharge in
  one period, 0 <= SoC <= E, audit identity).  Under the default profile a
  failed gate fails scientific validation and blocks annual economics
  (`publication_blocked.reason_code = GF_VALIDATION_GATE_FAILED`).  The
  doctoral reproduction profile reads gate failures through declared
  deviations with falsifiable signatures
  (`gridform_core/data/methodology/declared_deviations.json`: DEV-BAL-04,
  DEV-STO-01; DEV-BAL-01/02/03 as evidence only) and reports
  `reproduction_conformant` or `reproduction_with_declared_deviations`;
  its annual results follow decision Q14 (withheld unless every raw
  invariant passes).  New report fields: `storage_invariant_status`,
  `storage_invariants`, `validation_gate`, `declared_deviations`,
  `energy_balance.raw_boundary_status`.
- The Q14 verdict is derived from the gate statuses; a stored
  `raw_invariants.status` that disagrees is treated as failed, and the bundle
  validator recomputes it.
- Documentation errata: `docs/visibility-refactor/MARKET_LEDGER.md`,
  `RELEASE_0.4.md` (the 2,353 MWh statement), `ORCHESTRATOR_V2.md`,
  `TWO_YEAR_SMOKE.md`; methodology draft
  `docs/methodology/drafts/0.4/p04_energy_balance_validation.md`.

## 0.6.0-alpha.2 — VALUE Network Extensions identity (2026-08-20)

- Adopted the scientific name **VALUE**: Variable renewable electricity
  Allocation, Load-enabled excess-generation Utilisation, and system Evolution.
- Named this repository **VALUE Network Extensions** and kept the accepted
  single-node baseline distinct from optional network capabilities.
- Preserved `value.*`, `value.*`, `gridform_core`, `VALUE_DATA_HOME` and
  legacy launcher names as 0.x compatibility identifiers so existing Studies,
  checkpoints and external modules remain readable.
- Added VALUE-named launchers without changing the scientific execution path.

## 0.6.0-alpha.1 — Expanded-platform private test candidate (2026-08-19)

- Added versioned, fail-closed extension capability graphs and transactional
  extension bundles without changing the single execution registry.
- Added explicit run-of-river and reservoir hydrology contracts, with pumped
  hydro kept in the existing storage model.
- Added an open chronological DC network PSM independently checked on
  analytical, random, 24-hour and 168-hour cases.
- Added a local-only experimental AC feasibility checker; AC optimal power flow
  and global AC optimality remain not evaluated.
- Added an experimental, causal transmission-expansion lifecycle with explicit
  candidates, budgets, lineage, cost and carbon accounting.
- Preserved the Prompt 64 single-node beta and retained VALUE source hashes.

## 0.5.0-beta.1 — Prompt 58 local module bundles

- Added deterministic `value.module-bundle/v1` packaging and an offline,
  transactional local installer.
- Added the Modules-page install, trust acknowledgement, provenance and
  enable/disable workflow without changing the single execution registry.
- Prevented built-in shadowing, unsafe ZIP paths, native binaries, inventory
  mutation and disabling modules referenced by saved Studies.
- Added an uploadable storage-cost example, bilingual guidance and bounded
  installer/API/security tests.

## Unreleased — post-Prompt 46 corrections (2026-08-10)

- Added versioned commissioned-asset records with CAPEX, FOM, economic life,
  CRF, annualised cost and project lineage; incomplete economics now fail closed.
- Coupled cumulative commissioned assets into the following year's live VALUE
  clearing fleet and reconciled asset economics with the annual capital ledger.
- Declared the public CEM as `force-cem-v1`, VALUE-derived with explicit
  divergences and no exact retained numerical-reproduction claim.
- Closed direct, import and embodied annual carbon ledgers across JSON and
  SQLite outputs.
- Added a separately verified 25-role UK public-data candidate with per-object
  source terms, attribution and integrity evidence.
- Regenerated the one-year, causal two-year, dynamic ten-year and legacy-tariff
  ten-year runs and passed the bounded scientific beta release gates.

## 0.5.0-beta.1 — 2026-08-08

- Added native public-contract execution for the optional perfect-foresight PSM.
- Added canonical CEM cost, carbon, planning, terminal and fleet ledgers.
- Added immutable input snapshots, safe run bundles and lifecycle controls.
- Added independent CBC validation of the HiGHS perfect-foresight formulation.
- Added bounded run comparison and storage-policy experiment contracts.
- Licensed owner-controlled software under Apache-2.0, repository documentation
  under CC BY 4.0 and the deterministic synthetic data pack under CC0 1.0.
- Recorded Hanzhe Xing as copyright owner and project lead, with Stuart Scott and
  John Miles acknowledged as contributing supervisors and advisors.
- Added a metadata-only source register for all 25 local UK data roles and
  verified every installed object's size and SHA-256 without changing VALUE.
- Kept UK data redistribution and VALUE direct-runtime cutover as independent
  release gates.
