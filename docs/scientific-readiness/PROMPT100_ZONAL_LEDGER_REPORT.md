# Prompt 100 — zonal ledger and accounting report

## Decision

**Accepted for bounded integration.** The authoritative market database now has
an additive `gridform.market-ledger/v5` migration. It keeps national settlement,
redispatch settlement, physical resource cost, constraint-cost attribution,
policy transfers and boundary shadow diagnostics separate. This does not make
the zonal solver a validated annual scientific baseline; Prompt 103 remains the
independent optimisation gate.

## Accounting boundary

- The national ahead schedule is settled at the GB clearing price.
- Redispatch is signed pay-as-bid: accepted delta multiplied by bid price.
- The CEM headline remains commissioned-fleet annualised CAPEX/FOM plus final
  physical operating resource cost. National and redispatch payments are not
  added to it again.
- Constraint cost is an attribution inside final physical cost: matched zonal
  realised cost minus matched realised copperplate cost.
- Boundary shadow value is labelled only as a diagnostic marginal value in the
  accepted-bid objective. It is not called a zonal price or cash cost.

The three counterfactuals share one realised-input SHA-256. Their identities are
checked as `forecast error = case 2 - case 1`, `network constraint = case 3 -
case 2`, and `total deviation = case 3 - case 1`.

## Storage and reliability

Summary mode stores final per-resource dispatch, signed adjustment, actual SOC,
charge and discharge. Prompt 101 will feed actual post-redispatch discharge to
the dynamic storage-recovery and CEM paths. Reliability rows report observed
loss-of-load half-hours, duration, unserved MWh, zones and peak deficit. A single
chronology is explicitly not labelled statistical LOLE.

## Store and query behaviour

The existing SQLite file remains authoritative. Summary mode stores compact
period, zone, boundary, resource, reliability and solver-link rows. Full mode
adds every redispatch bid, acceptance/payment and reason code. Public paginated
queries and filtered JSONL/CSV exports use allowlisted views and indexed fields.
The field dictionary is written beside the database. Preflight includes the
additional zonal/full-trace disk estimate.

## Verification

- Prompt 100 focused acceptance: 11 passed.
- Existing market-ledger regression: 7 passed.
- Existing market-replay regression: 6 passed.
- Existing cost/storage-ledger regression: 4 passed.
- Existing preflight regression: passed.
- 2,000-period / 100,000-order benchmark: passed within its 30-second gate.
- Retained Scheme C source hashes: passed.
- Complete Python 3.10 suite: 452 top-level tests run; 431 passed, 21 declared
  skips, 89 passed subtests and 0 failures.

The same result is recorded in
`publication/prompt100-zonal-ledger-report.json`.
