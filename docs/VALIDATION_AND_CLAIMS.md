# Validation evidence and bounded claims

This matrix states what the VALUE Network Extensions 0.7.0-alpha.1 source (P0
review fixes, October 2026; see "Scope of the 0.7.0-alpha.1 claims" below), the
0.6.0-alpha.2 candidate it supersedes and the separately preserved 0.5.0-beta.1
single-node baseline evidence support.
"Passed" applies only to the named scope; it is not a general endorsement of all
scientific output. Prompts 52-55 add complete post-architecture annual and
ten-year evidence to the earlier solver and bounded-integration tests.

| Claim | Evidence type | Evidence | Status | Boundary |
|---|---|---|---|---|
| Perfect-foresight LP conserves interval energy and storage SOC | Analytical residual and unit tests | `tests/test_perfect_foresight_psm.py` | passed | Synthetic convex cases |
| LP objective agrees with a separately encoded optimizer | Independent PuLP/CBC oracle against SciPy/HiGHS | `tests/test_independent_psm_validation.py` | passed | 24 h, 168 h and three random 24 h cases |
| Broken balance, efficiency, SOC, terminal and import constraints are detected | Mutation tests | `tests/test_independent_psm_validation.py` | passed | Synthetic cases |
| Project-selected external module executes | Integration and browser E2E marker | `tests/test_external_module_execution.py`, `e2e/happy-path.spec.ts` | passed | Synthetic two-year smoke |
| Dynamic storage first year uses full-utilization basis | Analytical/unit tests | `tests/test_dynamic_storage_cost.py` | passed | Catalogue technologies |
| Cycle depreciation applies to batteries, not pumped hydro/hydrogen | Unit tests and executable formula | `tests/test_dynamic_storage_cost.py` | passed | Shipped storage catalogue |
| Cost ledger excludes settlements/policy transfers from physical resource cost | Reconciliation tests | `tests/test_release_upgrade_ledgers.py`, `tests/test_results_summary.py` | passed | Typed market results |
| Missing carbon factors are not reported as zero | Database/ledger tests | `tests/test_carbon_ledger.py`, `tests/test_carbon_factor_database.py` | passed | Two shipped factor scenarios |
| Pipeline event counts and state transitions reconcile | Modular regression | `tests/test_planning_ledger.py`, `tests/test_planning_index.py`, `tests/test_terminal_state.py` | passed | Synthetic and compatibility fixtures |
| Checkpoint resume preserves frozen execution identity | Integration tests | `tests/test_native_checkpoint_resume.py`, `tests/test_run_lifecycle.py` | passed | Native test projects |
| Browser happy path uses real backend and produces a valid run bundle | Playwright E2E | `e2e/happy-path.spec.ts` | passed | Synthetic pack, two-period/two-year smoke |
| Full annual FORCE run produces non-zero model investment and reconciled owner/headroom evidence | 17,520-period production chronology | `publication/prompt52-one-year-full-audit.json` | passed | Corrected UK pack, 2025 |
| Commissioned REPD and model projects enter the actual following PSM with complete economics and lineage | 35,040-period causal run | `publication/prompt52-two-year-full-audit.json` | passed | Corrected UK pack, 2025-2026 |
| Dynamic and legacy modular scenarios complete ten annual transitions | Two 175,200-period runs and fail-closed audits | `publication/prompt52-dynamic-ten-year-audit.json`, `publication/prompt52-legacy-ten-year-audit.json` | passed | FORCE-CEM v1, 2025-2034 |
| Scheme C reproduction carbon is not relabelled as physical tCO2e | Scenario-aware null/reason-code audit | `publication/prompt52-legacy-ten-year-audit.json` | passed | Historical storage scalars have no declared physical unit |
| Checkpoint recovery preserves completed annual states | Interrupted and resumed paired ten-year runs | `publication/prompt52-checkpoint-resume-audit.json` | passed | Incomplete current year is recomputed |
| Built-in GB scenario has no internal transmission constraints | Fixed parameter and model source review | `model.topology=single_gb_node` | passed | Built-in scenario only |
| Compatibility thermal merit order equals continuous convex single-period dispatch under matching assumptions | Analytical qualification and small benchmark | `tests/test_market_ledger_benchmark.py` | bounded | No UC/ramp/network; storage excluded from the equivalence claim |
| Declared convex FORCE live bid-at-cost clearing stages agree with an independent optimizer | Pre-clearing declarations and independent PuLP/CBC oracle | `publication/prompt46-force-24h-independent-validation.json`, `publication/prompt46-force-168h-independent-validation.json` | passed | 24 h and 168 h declared convex stages; sequential rule stages are classified separately |
| Compatibility module exactly reproduces retained 2026-07-18 trajectory | Retained comparison did not satisfy gate | prior comparison artifacts | failed | Do not call exact reproduction |
| Dynamic storage policy is the uniquely recommended scientific baseline | Sensitivity reveals denominator feedback | storage audits | not_evaluated | Published research scenario, not unique optimum |
| CEM is a global perfect-foresight expansion optimum | No global CEM optimization formulation | none | not_evaluated | Agent/path-dependent model |
| Chronological convex DC-network clearing satisfies its declared formulation | Independent angle-eliminated oracle, analytical/random cases and mutations | Prompt 68 tests and `docs/scientific-readiness/PROMPT71_EXPANDED_PLATFORM_RELEASE_REPORT.md` | passed | Reference synthetic 24 h and 168 h scope; not full unit commitment |
| AC feasibility residuals agree across polar and rectangular checks | Cross-formulation feasibility fixtures | Prompt 69 tests and Prompt 71 report | experimental | Local feasibility only; not AC OPF or global optimality |
| Transmission candidates follow a causal planning and commissioning lifecycle | Two-year fixtures and typed ledgers | Prompt 70 tests and Prompt 71 report | experimental | No full annual or ten-year GB network pathway |
| Staged/zonal redispatch dispatch does not depend on asset names; a decremented fuel unit keeps no windfall | Economic dec pricing and pro-rata ties (P0-8 S7) | `tests/test_network_dec_pricing.py` | passed | Toy staged copperplate and zonal cases; dec prices use declared support and premium parameters |
| Zonal network constraint cost contains only the network effect | Network-free LP counterfactual with one unit-cost table and VOLL (P0-8 S9) | `tests/test_p08b_network_counterfactual.py` | passed | Single-zone shortfall, period import prices and export arbitrage give 0; network cost and redispatch-added/avoided curtailment recorded before P0-8b must not support research conclusions (derived known defects) |
| Boundary marginal values are LP duals | Primary-stage duals equal finite differences; VALUE 101 NC boundary 66.5 GBP/MWh (P0-8 S10) | `tests/test_p08b_boundary_duals.py` | passed | Diagnostic, not a zonal price or cash cost; values before P0-8b were never computed and read as not computed |
| Doctoral reproduction profile keeps the 0.6.0-alpha.2 trajectory bit for bit except for the approved universal corrections | Golden digests per table and column, exact mode | `tests/golden/doctoral/`, `docs/release/P0_GOLDEN_DELTA.md` | passed | D1-D3 (VALUE 101 smoke, two_year_smoke, value_101_day) bit-identical to 35aadb3; D4 and D5 re-baselined once each (A4; A3, A5, A4) with numeric reports; linux-x86_64, CPython 3.10.18, numpy 1.24.4; not the 2026-07-18 retained trajectory |
| Every golden change since 35aadb3 is attributed to a correction id | Generated delta report with an attribution check | `scripts/golden/delta_report.py`, `tests/test_golden_delta_report.py` | passed | 13 golden cases and 4 doctoral/corrected pairs; lists changed columns, not magnitudes |
| Corrected default PSM closes the per-period energy identity and storage limits | Read-only energy-balance oracle and validation gates (P0-4, P0-6) | `tests/test_energy_balance_oracle.py`, `tests/test_p04_validation_gate.py`, golden C1-C4 | passed | VALUE 101 value_101_day and two_year_smoke; ahead shortfalls are reported as stress events (A2), not removed |
| Local API refuses browser-driven, cross-origin and sessionless requests | Truth table, side-effect tests with positive controls, browser E2E (P0-1) | `tests/test_local_api_boundary.py`, `e2e/security-boundary.spec.ts` | passed | Source tree on Linux; single-user host assumed (Q11); an installed 0.7.0-alpha.1 is checked only after reinstalling, with `scripts/verify_local_security_boundary.py` |
| 0.7.0-alpha.1 installers install, start and pass the post-install acceptance | Not yet built | `docs/release/P0_ACCEPTANCE.md` section 6 | not_evaluated | Windows needs a real-machine smoke before release; macOS is not verified on hardware |
| Corrected wind and solar capacity factors match statistical load factors | Disclosure next to DUKES 6.3 (A9) | run summary `vre_capacity_factor_disclosure` | not_evaluated | Not calibrated by design; GBP1 wind about 1.2-1.6x DUKES |
| Reserves, full unit commitment and ramping are represented | No executable module | none | not_evaluated | Unsupported |
| Owner-controlled code, documentation and synthetic data may be publicly redistributed under the declared licences | Owner decision and per-object rights inventory | `LICENSE`, `docs/LICENSE.md`, `publication/rights-inventory.json` | passed | Does not grant redistribution rights for third-party UK data |
| The separately assembled UK public-data candidate may be distributed per object | Per-object source terms, attribution, semantic checks and file hashes | `publication/rights-inventory.json`, `publication/force-uk-open-data-pack/prompt46-final-public-artifact-scan.json` | passed | No blanket relicensing; the installed local pack is not automatically covered |

The independent LP oracle proves the optional LP implementation against another
optimizer; it does **not** prove that the research-compatible Scheme C algorithm is
the same optimization problem. Smoke modes prove wiring and state continuity only.
They deliberately hide annual economics and cannot replace a 17,520-period annual
validation.

The Prompt 52-55 decision is GO for a local research beta with bounded scientific
claims. It is NO-GO for a fresh GitHub checkout because 460 intended source
members are not tracked. It does not establish exact retained Scheme C
reproduction, global optimality of the CEM, AC optimal power flow or full unit
commitment. The reference DC validation remains bounded to its declared convex
scope. Dynamic storage pricing remains a selectable research policy, and
each redistributed UK data object remains governed by its recorded upstream
terms. See `publication/prompt52-final-test-report.md` and the companion JSON.

Default PSM (P0-6): corrected runs close the per-period energy identity
`native_corrected_full_node_v1` (raw residual <= 1e-6, no compatibility
adjustment, storage discharge <= rated power and no same-period charge and
discharge, checked on the VALUE 101 value_101_day and two_year_smoke
variants) except where the ahead stage could not meet the forecast; those
shortfalls are reported as stress events (decision A2). Doctoral runs
reproduce 0.6.0-alpha.2 dispatch and carry declared deviations; they do not
establish closure of the energy identity.

Corrected-profile data science (P0-5b): the solar timing correction is
checked on GBP1 (London centroid 11.97 UTC, 21 December first nonzero
08:00 UTC). Wind and solar loss factors are literature values, not a fit:
the resulting annual capacity factors (GBP1 onshore 0.403, offshore 0.491,
solar 0.100) are reported, not claimed to match DUKES load factors, and
ERA5's own wind bias is not removed. Nuclear and natural-flow hydro
availability values were PENDING AUTHOR REVIEW at this step (reviewed by the
author in A14, see the F2 update below); their acceptance against
Energy Trends 5.1 and DUKES is deferred to the author.

F2 update (A9, A13, A14): corrected solar now uses plane-of-array irradiance
(GBP1 CF 0.107, 1.04x the DUKES 2020-2024 load factor); onshore and offshore
wind remain about 1.56x and 1.23x DUKES and are disclosed, not claimed to
match (reasons: ERA5 wind bias, free-stream single-turbine curve,
pre-curtailment basis, representative sites, climatology). Natural-flow hydro
(0.3487 x seasonal shape) gives 6.10 TWh on GBP1 against the DUKES 6.2
2019-2024 mean of 5.77 TWh (+5.8 %, within the author's +-15 %). The nuclear
and hydro values were reviewed by the author (A14); the nuclear acceptance run
against Energy Trends 5.1 on GBP1 has not been made.

## Scope of the 0.7.0-alpha.1 claims

- Reproduction statements are bounded by case, platform and section. Bit
  identity is claimed only for the trajectory zone (dispatch, flows, prices,
  state of charge, capacity, investment proposals) of the named doctoral
  golden cases, compared in exact mode on linux-x86_64 with CPython 3.10.18 and
  numpy 1.24.4. On other platforms the golden comparison uses values rounded
  to nine significant digits and supports no bit-identity statement.
  Accounting and identity columns (residuals, audits, cost ledgers,
  validation reports, code identity) changed under the correction ids listed
  in `docs/release/P0_GOLDEN_DELTA.md`.
- The doctoral reproduction profile reproduces VALUE 0.6.0-alpha.2 as
  implemented, with the universal corrections P6-24, P6-02, P6-03, P6-04 and
  the thermal net revenue (A4). The comparison with the retained 2026-07-18
  trajectory remains failed (row above). Its annual results appear on result
  pages only when every raw invariant passed (Q14).
- The GBP1 before/after comparison of the doctoral profile covers one model
  year (golden D5). Multi-year GBP1 doctoral runs were not repeated after the
  fixes.
- Known issue (A15): that GBP1 doctoral run fails the surplus-conservation
  invariant in 471 periods, by up to 991 MWh, as the 35aadb3 code did. It is
  under investigation and is not a declared deviation. Its annual results stay
  withheld (Q14), and no energy-balance statement is made for it. In the
  frozen kernel an accepted nuclear unit runs at full power to the end of the
  year (path dependency).
- Investment decisions are undiscounted ROI and payback tests in constant
  base-year money (A6). This is a model assumption, not a validated optimum.
- The corrected profile is a method change. Runs of different profiles are
  compared as different methods, and a comparison does not attribute their
  difference to any one input.
- The network modules (staged copperplate, zonal, DC, AC) run only under the
  corrected profile (Q3). Their claims are the bounded rows above.

