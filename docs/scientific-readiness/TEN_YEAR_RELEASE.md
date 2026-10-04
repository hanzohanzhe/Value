# Archived pre-Prompt-11 ten-year engineering comparison

> Historical evidence only. This report was produced on 5 August 2026 before
> Prompts 11-28 changed the canonical cost/carbon contracts, clean module path and
> public release gates. Its “functional GO” meant that those two old local runs
> completed; it is **not** the current public-code, UK-data or scientific-baseline
> decision. The current decisions are all NO-GO in
> `publication/release-report-0.5.0-beta.1-post-prompt34.md`. The old bundles remain immutable
> and were not relabelled or overwritten.

Date: 2026-08-05  
Runtime: Python 3.10.0 on Windows; Node.js/vinext production build

## Decision

**Functional release: GO.** Both project-composed 2025-2034 runs completed all
175,200 half-hour periods, all ten PSM -> CEM -> planning -> next-state cycles,
and produced valid immutable run bundles.

**Exact 2026-07-18 Scheme C reproduction: NO-GO.** The legacy storage-cost
module reproduces the retained `storage_fee + dwell * per_storage_fee` bid
equation, but its full modular trajectory fails the declared strict numerical
tolerances. It must be described as the *legacy-tariff modular scenario*, not an
exact reproduction.

**Dynamic storage scenario: scientifically distinct.** Its retained-result
difference is expected evidence, not a reproduction failure. Its equations and
contracts pass, but the endogenous cost-recovery oscillation described below
requires sensitivity analysis before a policy baseline is adopted.

## Runs and integrity

| Scenario | Run ID | Completion | Bundle validation | Scientific interpretation |
| --- | --- | ---: | --- | --- |
| Dynamic annual-average recovery | `scientific-dynamic-storage-2025-2034-20260804-205626-585b97` | 10/10 years | 81 artifacts, 10 state transitions, 0 errors | Scenario passed; retained difference expected |
| Scheme C legacy tariff | `scientific-legacy-storage-2025-2034-20260804-205626-dcd3c5` | 10/10 years | 81 artifacts, 10 state transitions, 0 errors | Execution/contracts passed; strict reproduction failed |

Both scenarios recorded 175,200 period summaries and 876,000 storage-state
rows. Maximum adjusted energy-balance residual was
`1.8189894035458565e-11 MWh` for dynamic recovery and
`2.1827872842550278e-11 MWh` for the legacy tariff. Total blackout was zero in
both runs.

The dynamic bundle was closed before the validation-role fix and therefore
preserves its original embedded `failed` label. That immutable record was not
rewritten. The current application presents its preserved execution, contract
and analytical checks as `scientific scenario: passed`, with
`retained comparison: expected difference`. Future bundles write that role at
creation time.

## Annual comparison

### System cost

| Year | Dynamic (GBP/MWh) | Legacy tariff (GBP/MWh) | Retained Scheme C (GBP/MWh) |
| ---: | ---: | ---: | ---: |
| 2025 | 183.442 | 183.567 | 182.923 |
| 2026 | 187.315 | 187.484 | 186.969 |
| 2027 | 196.137 | 196.805 | 196.481 |
| 2028 | 198.700 | 198.840 | 198.705 |
| 2029 | 200.130 | 199.918 | 199.861 |
| 2030 | 201.915 | 202.864 | 202.881 |
| 2031 | 204.247 | 204.674 | 204.758 |
| 2032 | 206.987 | 206.549 | 206.632 |
| 2033 | 216.245 | 215.773 | 216.115 |
| 2034 | 229.626 | 229.563 | 230.054 |

### Beginning-of-year storage capacity

| Year | Dynamic (MW) | Legacy tariff (MW) | Retained Scheme C (MW) |
| ---: | ---: | ---: | ---: |
| 2025 | 5,669.600 | 5,669.600 | 5,669.600 |
| 2026 | 26,907.330 | 26,907.330 | 26,907.330 |
| 2027 | 59,464.221 | 59,464.221 | 59,674.063 |
| 2028 | 64,813.156 | 64,660.109 | 65,236.337 |
| 2029 | 70,072.974 | 67,854.360 | 68,491.102 |
| 2030 | 74,508.547 | 72,251.956 | 72,914.941 |
| 2031 | 80,117.160 | 77,909.581 | 78,591.923 |
| 2032 | 85,559.561 | 83,488.220 | 84,201.977 |
| 2033 | 91,199.974 | 89,119.429 | 89,881.887 |
| 2034 | 96,807.414 | 94,750.689 | 95,585.162 |

The legacy-versus-retained comparison passed only 18 of 100 deliberately tight
metric checks. Its largest annual deviations were 0.352% for system cost per
MWh, 3.094% for operational cost and 0.930% for storage capacity. Dynamic versus
retained maxima were 0.476%, 8.224% and 2.310%, respectively. The complete
values, units, tolerances and signed deltas are in `ten-year-comparison.json`.

The legacy mismatch is not evidence that its bid equation is wrong. The modular
public path also contains reviewed physical corrections absent from the retained
snapshot, including explicit MW/MWh capacity, half-hour energy conversion,
storage power limits and cross-year storage state. Those changes compound through
investment and planning, so selecting only the historical tariff cannot recreate
the entire retained trajectory.

## Dynamic storage-cost audit

The first year uses each technology's full-utilisation design case. Later years
use preceding-year delivered MWh and sales-weighted dwell time. Batteries alone
receive cycle depreciation; pumped hydro and hydrogen have zero cycle
depreciation. MW, MWh, duration, charge efficiency and discharge efficiency are
exported explicitly.

Across 50 technology-year observations, the audit found:

- 21 returns to the full-utilisation fallback after no preceding-year sale;
- 16 zero-sales years following a positive observed-sales pricing basis;
- 5 holding-recovery coefficients above GBP 10,000/MWh/period;
- positive cycle depreciation in all battery records and none in pumped hydro
  or hydrogen records.

This is a genuine feedback effect of the exact previous-year denominator. For
example, a very small sale can create an extremely high next-year bid, suppress
sales, and trigger the fallback in the following year. GridForm reports rather
than hides it. Recommended scientific practice is to run declared sensitivity
scenarios for `storage.cost.utilisation_floor_fraction` (including the exact
zero-floor thesis interpretation) and compare investment, dispatch and recovery
adequacy. No floor was silently imposed on these results.

## Planning evolution

Both planning ledgers reconcile every introduced project in every year. At the
end of 2034:

| Scenario | Active projects | Active capacity (MW) | Commissioned projects | Commissioned capacity (MW) |
| --- | ---: | ---: | ---: | ---: |
| Dynamic | 81 | 8,845.402 | 1,313 | 149,858.507 |
| Legacy tariff | 65 | 13,165.523 | 1,309 | 147,381.179 |

The Audit page exposes stage, technology, region, completion year, cause and
commissioning links on demand. Future summaries merge case-only source labels so
Windows JSON readers do not see duplicate keys; original SQLite evidence remains
unchanged.

## Ten implemented improvement modules

| Prompt | Result |
| --- | --- |
| 01 Scientific acceptance | Independent execution, contract, mechanism, modular and retained-comparison statuses |
| 02 Storage-cost policy | Dynamic, legacy and safe user-formula policies; battery-only cycle depreciation; explicit MW/MWh/efficiency |
| 03 Run classification | Two-period and smoke economics hidden; only 17,520-period years publish annual results |
| 04 Module conformance | IDs, slots, contracts, capabilities and callability validated before run |
| 05 Project revisions | Append-only revisions and canonical SHA-256 fingerprints |
| 06 Data-pack validation | All 25 semantic interfaces validated with units, mappings and provenance |
| 07 Planning ledger | Causal, reconciled project lifecycle with outcomes and commissioning links |
| 08 Market artifacts | Fast SQLite summaries, optional orders/Parquet and explicit balance evidence |
| 09 Preflight | Python 3.10, data, modules, parameters, disk, output and checkpoint readiness |
| 10 Recovery/release | Atomic annual checkpoints, source-bound resume identity, artifact index, bundle validator and three-way comparison |

## Final verification

| Gate | Result |
| --- | --- |
| Python 3.10 unit/integration suite | 103 passed, 1 runtime-conditional skip |
| Frontend production build/render suite | 3 passed |
| Retained-source hash protection | passed within Python suite |
| Dynamic run bundle | valid; 81 artifacts; 10 state transitions |
| Legacy run bundle | valid; 81 artifacts; 10 state transitions |
| Local browser smoke | Python 3.10 online; 25/25 interfaces; 9/9 executable modules; both 10/10 runs visible |

## Artifacts

- `ten-year-comparison.json`: complete three-way numerical comparison;
- `dynamic-storage-cost-audit.json`: detailed dynamic cost-recovery evidence;
- `legacy-storage-cost-audit.json`: detailed historical-tariff evidence.

The audit files were exported outside the already sealed run bundles from local,
trusted annual checkpoints. Future completed runs create
`storage/cost-audit.json` inside the bundle automatically. Pickle checkpoints
must never be loaded from an untrusted source.
