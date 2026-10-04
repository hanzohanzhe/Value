# FORCE independent zonal solver validation

Date: 2026-08-21T23:16:51.203488+00:00

Scope: Prompt 103

## Decision

**GO** — Independent zonal formulation matches and all adversarial gates pass.

This validation independently rebuilds the declared zonal redispatch problem in
PuLP and solves it with CBC. It does not import the production formulation or
its HiGHS matrices. The chronological cases remain separate half-hour auctions:
only the previous period's realised SOC is carried forward.

## Results

| Gate | Result |
| --- | ---: |
| Hand-solvable cases | 5 / 5 |
| Seeded random convex cases | 4 / 4 |
| Sequential half-hours (24 h + 168 h) | 384 / 384 |
| Deliberate mutations detected | 11 / 11 |
| Malformed, zero-flexibility and infeasible behaviours | 5 / 5 |

## Declared tolerances

- Energy and physical quantities: `1e-06` MWh
- Absolute objective tolerance: `1e-05` GBP
- Relative objective tolerance: `1e-08`

## Interpretation

Passing this gate validates the implemented lossless transport/cut-set
redispatch problem against an independently assembled LP. It does not convert
the model into AC or DC power flow, validate GB security constraints, or add
perfect foresight. Prompt 104 may proceed only when the machine-readable
`prompt_104_allowed` field is true.

Machine-readable evidence: `publication/prompt103-independent-zonal-validation-report.json`.
