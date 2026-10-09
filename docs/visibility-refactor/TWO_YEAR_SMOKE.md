# Two-year smoke verification

Date: 2026-08-04  
Run: `postedit-two-year-smoke-v2-20260804`

## Scope

The `two_year_smoke` mode runs two half-hour periods in 2025 and two in 2026.
Both years execute the complete planning advance, PSM, expansion policies,
agent investment, planning admission and state-transition lifecycle. It tests
interfaces and cross-year state continuity; it is not a sampled annual study.

## Result

- process status: completed, 2/2 years;
- selected-module completion: 10/10;
- copied-session to public-contract parity: 75/75;
- market ledger: 4 period rows and 20 storage-state rows;
- maximum adjusted energy-balance residual: `3.637978807091713e-12 MWh`;
- planning reconciliation: passed in both years;
- provenance state chain: 2 transitions with exact 2025-output to 2026-input hash continuity;
- bundle: 40 artifacts valid, no errors;
- PSM and storage-cap versions: `3.0.0`.

## Issues found and corrected

The first smoke run correctly hid annual cost cards, but its parity report called
the overall release gate passed even though retained annual numerical parity is
not evaluated for a four-period run. `release_gate_passed` is now `null`; only
`contract_parity_passed` is true.

Correction (P0-4, 2026-10): up to 0.6.0-alpha.2 `contract_parity_passed` was a
literal `true` written by the application, not the result of executed
checks. From P0-4 S2 it is recomputed from the checks the parity report lists
(`null`, i.e. not evaluated, when none ran), and it says nothing about the
energy balance, which the scientific-validation report gates separately
(P0-4 S7).

Two periods also produce non-representative annual costs, investment quantities
and pipeline quantities. The status contract and Run centre now explicitly mark
all three as diagnostic, publish no scientific result rows, and retain the raw
artifacts only for engineering audit.

No PSM/CEM invocation, state-continuity, planning-reconciliation, market-balance,
module-version or bundle-integrity defect remained after these corrections.
