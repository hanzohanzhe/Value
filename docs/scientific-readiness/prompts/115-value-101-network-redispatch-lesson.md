# Prompt 115 — VALUE 101 network constraints and redispatch lesson

## Status

Implemented on 24 August 2026.

## Purpose

Add one optional network lesson after the core VALUE 101 route. It lets a
learner compare the same national auction with and without fixed delivery
constraints, then inspect congestion, redispatch, curtailment and cost evidence.

## Implemented contract

- `value-101-network-v1` is a complete deterministic CC0 teaching pack. Its 25
  ordinary data-role files are byte-identical to the baseline pack; eight zonal
  roles are additive.
- The network contains North, Central and South zones, two fixed corridors,
  asymmetric transfer limits and declared maintenance multipliers. North is a
  low-demand, wind-rich zone behind an intentionally narrow teaching boundary.
- The API previews and then creates a matched copperplate/constrained Study
  pair. It never starts a Run implicitly. Both Studies use the same staged
  bid-at-cost PSM, national demand clock, data and non-network modules.
- The constrained Study uses the existing `force-zonal-redispatch-balancing`
  implementation and built-in `highs-ds` numerical contract. It does not create
  a tutorial solver.
- Representative-point weather is selected explicitly for both Studies. The
  experimental weather and redispatch modules retain their normal maturity
  acknowledgements.
- The synthetic REPD solar project has a declared South-zone location. Its
  commissioned child inherits that frozen mapping in 2026.
- Multi-year network clocks are selected by model year. A later year cannot
  silently reuse an earlier year's period identifiers.
- The existing Network results view remains the detailed evidence surface.

## Live verification

The final matched run executed 48 half-hour periods in each of 2025 and 2026
for both Studies. The machine-readable report is
`publication/prompt115-value-101-network-live-verification.json`.

- 96/96 normalized ahead-market schedules were identical.
- 96 unique cross-year period identifiers and 288 three-phase solver rows were
  stored; every numerical lock was `GO`.
- 96 boundary-period rows reached the declared transfer envelope.
- 645 pay-as-bid redispatch settlements moved 1,010.186 MWh in absolute terms.
- Network constraint cost was £33,258.83 over the teaching window.
- Redispatch added 563.661 MWh and avoided 53.568 MWh of VRE curtailment; the
  net redispatch impact was 510.093 MWh.
- Total load shedding was `7.10e-16 MWh`, numerical noise below the material
  threshold.

The run exposed and fixed two integration defects before passing: missing
explicit weather spatialisation, and reuse of 2025 network period identifiers
in 2026. It also demonstrated that a located planning project must be present
in the signed asset map before its commissioned child enters the next year.

## Verification performed

- Prompt 115 pack/API/UI and cross-year clock tests: 9 passed.
- Prompt 98 data-builder regressions: passed.
- Prompt 99 zonal solver regressions: passed.
- Prompt 100 market-ledger regressions: passed.
- Prompt 102 workspace regressions: passed.
- Prompt 103 independent 24/168-hour oracle, random and mutation gates: passed.
- Final matched live verifier: `PASS`.

The remaining Prompt 107 pytest-only production gate is part of the clean test
environment in Prompt 117; it is not treated as passed by this document.

## Scientific boundary

This is fixed, lossless zonal transport followed by pay-as-bid redispatch. It is
not DC load flow, AC power flow, N-1 security analysis, a transmission-expansion
model or annual GB economics. Its purpose is to make delivery constraints and
their market consequences visible with the same PSM/CEM interfaces used by the
rest of VALUE.

