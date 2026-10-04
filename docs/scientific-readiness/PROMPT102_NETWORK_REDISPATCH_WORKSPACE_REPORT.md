# Prompt 102 — Network & redispatch workspace report

Date: 21 August 2026  
Scope: dedicated results and launch UX for the optional staged zonal method

## Decision

Prompt 102 is accepted at bounded frontend and result-query scope. A user can
now see the national ahead market and final physical redispatch as separate
stages, inspect annual and half-hour zonal evidence, and create an explicitly
new copperplate run after a failed zonal solve.

This decision does not validate the zonal optimiser scientifically. Prompt 103
remains the independent-oracle gate, and Prompts 104–105 remain the annual and
long-run gates.

## Delivered interfaces

- `/api/runs/{run_id}/network-redispatch/capabilities`
- `/api/runs/{run_id}/network-redispatch/annual`
- bounded period, zone, boundary, resource, settlement, reliability and solver
  queries
- streamed CSV or JSONL exports from the canonical SQLite ledger
- a dedicated **Network & redispatch** workspace, separate from Run summary
- a computational zone/corridor schematic that makes no line-route claim
- annual resource-cost, counterfactual, settlement, policy, curtailment and
  observed-reliability summaries
- half-hour ahead-versus-final dispatch, storage state, corridor use and
  pay-as-bid redispatch replay
- immutable failure evidence and a new-run **Rerun as copperplate** action
- concise English and Chinese method/scope explanations

## Scientific labels

The page keeps final physical resource cost separate from national settlement,
redispatch settlement and policy transfers. Boundary marginal values are
labelled diagnostic rather than prices. Reliability is labelled **Observed
chronology, not statistical LOLE**. The zonal transport representation is
described as lossless computational corridors and explicitly **not a security
analysis**.

Summary and full ledgers produce the same annual scientific totals. Full trace
adds bid-level replay; summary trace explains why those rows are absent without
hiding annual results.

## Verification

| Gate | Result |
| --- | --- |
| Prompt 102 Python API/read-model tests | 3 passed |
| Complete Python 3.10 suite | 533 passed; 21 skipped; 89 subtests passed; 0 failed |
| Frontend lint | passed |
| Frontend production build | passed |
| Rendered HTML and source-claim tests | 3 passed |
| Focused Playwright journeys | 4 passed |
| Browser accessibility check | no serious or critical violations |

The browser fixtures cover congested zonal results, summary trace, failed zonal
rerun and a copperplate empty state. Prompt 103 is the next ordered task.
