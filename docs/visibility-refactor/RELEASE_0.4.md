# GridForm 0.4 release gate

Date: 2026-08-04  
Runtime: Python 3.10.0, Node.js/vinext production build on Windows

## Historical decision: NO-GO for numerical-equivalence claim

This document records the earlier two-year gate. The later ten-year functional
release is `GO`; the exact Scheme C numerical-reproduction claim remains
`NO-GO`. See `../scientific-readiness/TEN_YEAR_RELEASE.md` for the completed
2025-2034 evidence and current interpretation.

The application, module-contract, planning, provenance and run-bundle gates pass.
The scientific-retention gate does not. The dynamic annual-average storage cost
method intentionally changes storage offers and therefore the PSM and CEM result
relative to the retained 2026-07-18 Scheme C fixture. The fixture was not edited,
and the difference is not hidden by a wider tolerance.

The dynamic formulation is now truthfully published as PSM and storage-expansion
module version `3.0.0`, scientific version
`dynamic-storage-recovery-2026.08.04`. Historical bundles retain their earlier
manifest snapshots. The remaining release action is to approve an independently
reviewed two-year fixture for this dynamic version. Until that is done, 0.4 must
not be labelled numerically equivalent to the retained Scheme C run.

## Executed gates

| Gate | Result |
| --- | --- |
| Python 3.10 unit/integration suite | 65 passed, 1 runtime-conditional skip |
| Frontend production build/render suite | 3 passed |
| Two-period application run | completed in 37 s; 35/35 stage checks; 35 bundle artifacts valid |
| Full 2025 application run | completed in 70 min using the pre-optimisation process; 34/34 architecture checks; bundle valid |
| Final full 2025-2026 transition | completed in 16 min 18 s after removing redundant per-period garbage collection |
| Two-year v2 stage comparison | 81/81 passed |
| Two-year bundle validation | 40 artifacts and 2 state transitions valid; no errors |
| Planning reconciliation | passed for both years |
| Retained numerical comparison | **failed: 7/19 passed** |
| Convex bid-at-cost fixture | exact expected dispatch; 0 MWh residual |
| Retained source/data hashes | unchanged |

Run IDs:

- `release-prompt10-two-period-v2-20260804`
- `release-prompt10-one-year-v4-20260804`
- `release-prompt10-two-year-v2-20260804`

## Stage and transition evidence

The two-year typed path matched the copied project-composed session at every
materialised stage: beginning fleet, annual PSM summary, VRE/storage expansion
headroom, agent additions/retirements, agent income/cost/recommendation aggregates,
planning admission and reconciliation, next-year fleet and next-year pipeline.

Planning evidence:

- 2025: 13,023 introduced and 13,023 accounted; 1,210 active projects;
- 2026: 13,069 introduced and 13,069 accounted; 922 active, 332 commissioned and
  2 depleted/retired projects;
- the 2025 ending pipeline equals the 2026 beginning pipeline.

The independent one-year run and the 2025 portion of the two-year run are exactly
equal for the complete `system_cost_history`, `capacity_history` and
`investment_decisions` structures. The garbage-collection optimisation therefore
changed runtime only, not scientific output.

The final v2 run is also exactly equal to the earlier v1 full two-year run for
those same three complete structures. The v2 difference is evidence quality:
truthful module versions and an opt-in verbose balance diagnostic, not a changed
scientific calculation.

## Retained numerical divergence

The first scientific divergence is the 2025 PSM annual summary. Selected exact
differences are:

| Metric | Dynamic storage result | Retained Scheme C | Absolute difference |
| --- | ---: | ---: | ---: |
| 2025 system cost (GBP) | 42,605,875,468.47 | 42,697,698,747.10 | 91,823,278.62 |
| 2025 cost (GBP/MWh) | 183.44168275 | 182.92314458 | 0.51853818 |
| 2025 generation (MWh) | 232,258,420.38 | 233,418,788.23 | 1,160,367.85 |
| 2025 0.25C suggested addition (MW) | 800.00 | 1,040.43 | 240.43 |
| 2026 system cost (GBP) | 43,605,049,974.71 | 43,640,757,818.79 | 35,707,844.08 |
| 2026 cost (GBP/MWh) | 187.31467603 | 186.96917591 | 0.34550013 |
| 2026 generation (MWh) | 232,790,355.24 | 233,411,510.79 | 621,155.55 |
| 2026 0.25C suggested addition (MW) | 975.3549 | 1,219.79 | 244.4351 |

All beginning capacities in 2025 match. The full machine-readable comparison is
`prompt10-two-year-retained-parity-v2.json`. No tolerance was changed.

## Market invariant and compatibility visibility

The two-year summary ledger contains 35,040 period rows and 175,200 storage-state
rows. Maximum adjusted energy-balance residual is
`1.8189894035458565e-11 MWh`, so every persisted period satisfies the invariant.

The copied Scheme C settlement does not expose every secondary allocation as an
asset dispatch row. Ledger v2 therefore also preserves the unadjusted value:

- maximum absolute raw residual: `2,352.979705116729 MWh`;
- periods with an explicit compatibility adjustment: `1,900`;
- the adjustment is never relabelled as generation or blackout.

This is an asset-level visibility limitation, not evidence that the model's
annual physical accounting has been changed. The Audit page exposes both values
for affected periods.

## Trace benchmark

For 2,000 periods and 50 orders per period:

| Trace | Wall time | Overhead vs off | Rows | Bytes |
| --- | ---: | ---: | ---: | ---: |
| off | 0.0119 s | 0 s | 0 | 0 |
| summary | 0.1283 s | 0.1164 s | 4,000 | 364,544 |
| full | 5.0857 s | 5.0737 s | 104,000 | 15,388,672 |

The final two-year ledger spent 1.454 s writing. The verbose
`balance-diagnostic.jsonl` is now an explicit runtime option and was not created
by the final run; raw and adjusted residuals remain in SQLite.
Large ledgers never enter `/api/workspace` or run-status payloads. API limits are
bounded and the frontend paginates period and order queries.

## Legacy containment and deferred work

- The website/API start only `gridform_core.application.run_project_application`.
- Normal run history exposes only `gridform-annual-orchestrator/v2` runs.
- Retained runners remain explicit comparison CLI commands; old runs are not
  deleted or mutated.
- PyPSA is not a mandatory dependency. The exported convex bid-at-cost fixture is
  ready for a later independent PyPSA economic-dispatch comparison.
- Internal GB transmission, unit commitment, ramping and minimum-output constraints
  remain outside this single-node scientific formulation.
- Legacy and dynamic-storage scientific versions are now separated in provenance.
  An owner-reviewed dynamic fixture is still required before this decision can
  become `GO`.
