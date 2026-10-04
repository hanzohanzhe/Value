# Prompt 114 — VALUE 101 comparison and completion evidence

## Status

Implemented on 24 August 2026.

## Purpose

Give a learner one controlled, auditable comparison of the baseline, one data
variant and one storage-pricing variant without turning short teaching runs into
annual scientific results.

## Implemented contract

- The server accepts only three local Run identifiers and reads their immutable
  artifacts. Values supplied by the browser are ignored.
- Rows are ordered as baseline, data variant and storage variant.
- Every numerical field is labelled `teaching_window_*` and
  `annual_economics_eligible` is always false for the 48-period exercise.
- The controlled interpretation is refused when the declared identity
  difference contains an additional scientific dimension.
- Costs, carbon, VRE use and curtailment, storage movement, load shedding and
  planning events come from the corresponding stored ledgers or SQLite result
  databases. React only formats values returned by the API.
- Each row links to existing market, storage, curtailment, audit, provenance and
  raw-artifact routes.
- Completion evidence is exported as local JSON. It includes Study revisions,
  data packs, Run identities and statuses, optional-network status and available
  diagnostic paths.
- Reset first displays the exact teaching Studies and Runs and then calls the
  metadata-scoped lifecycle endpoint. It cannot remove ordinary research work.

## Verification performed

- Prompt 114 result/API/UI tests: 4 passed.
- Renamed VALUE 101 real-bundle evidence regression: 1 passed.
- VALUE 101 timing-contract regression: 1 passed.
- Result-summary regressions: 20 passed.
- Market-ledger unittest regressions: 17 passed.
- Carbon-ledger regressions: 9 passed.
- Planning-index regression: 1 passed.
- Frontend lint, production build and rendered HTML: passed (3/3 render tests).

`test_market_ledger_v6.py` is a pytest-only suite. The active Python 3.10
developer interpreter does not currently contain pytest, so that one command is
recorded as an environment gap rather than misreported as a model failure. The
clean test environment is part of Prompt 117's release gate.

## Scientific boundary

These outputs explain data flow, module replacement and stored evidence over a
small synthetic window. They are not annual GB economics, reliability or carbon
results and the interface does not annualise them.
