# Prompt 124 — trace/readiness and bounded long-result UI

## Scope

Prompt 124 changes presentation and API consumption only. It exposes the trace
profile saved in an immutable Study revision, renders Prompt 122 readiness
evidence without recalculating it in the browser, and consumes Prompt 123
bounded query and background-export contracts. It does not change the Study
graph, model science, ledger v8, solver/network equations, backend contracts,
Prompt 96 data, retained Scheme C or installer.

## Study trace selection

The Study composer presents `Summary`, `Full market replay` and
`Advanced: Off`. The selected canonical value is saved as
`runtime.market_trace_level = summary|full|off`; Summary remains the default.
Editing an existing Study loads its saved value and saving creates a new
immutable revision. A completed Run is never changed or started automatically.

Run and result screens label the actual `Recorded trace`. A Summary result
states `Bid-level replay was not recorded`, keeps scientific summary evidence
visible and offers to prepare a new Study revision with Full market replay.
Missing bid rows are not displayed as zero.

## Readiness evidence

Check readiness displays the backend-produced Prompt 122 payload: resolved
trace, estimated persisted output, temporary space, free-space reserve,
observed free space, runtime/calibration basis, quota decision and corrective
actions. It also displays selected data/network pack, context, module and
solver identities that the backend supplied. The frontend formats bytes and
labels only; it does not estimate resources or derive scientific quantities.

After a Run starts, the UI reads the immutable
`input-snapshot/resource-readiness.json`, `project.json` and `snapshot.json`
artifacts. These controls are read-only and expose the frozen trace, exact pack
manifest hashes, context hashes and module source identities used by the Run.

## Bounded results

Market replay requests one model year, a visible 24-hour or 168-hour period
window, a maximum 96-row page and an explicit offset. Network period replay
uses the same year/window contract with 48-row pages. The user can move between
windows and pages; neither view requests an annual or ten-year period payload.
Exact-period auction, storage, zone, boundary, resource, settlement and solver
requests remain bounded to the selected period.

Compact annual summaries remain available because they are server-aggregated
read models rather than period payloads. The former direct network JSONL/CSV
links were removed from the main controls.

## Export jobs

`ReplayExportPanel` requires one explicit range: period, 24 hours, 168 hours,
year or complete. It submits exactly one
`POST /api/runs/<run>/replay-exports` request, retains the returned
`status_url`, polls only that job while it is queued/running and exposes only
the completed job's `download_url`. Complete-run output is ZIP-only. JSONL and
CSV are explicitly bounded and no whole-run JSONL download anchor exists.

## Focused evidence

The initial RED run contained four intended assertion failures: trace/readiness
labels, truthful Summary behavior, bounded market/network controls and export
job UI were absent. The final focused gates are:

```text
node --test tests/prompt124-ui-contract.test.mjs  4/4 passed
npm run lint                                      passed
npm run build                                     exit 0
node --test tests/rendered-html.test.mjs           3/3 passed
```

No Python full suite, annual or ten-year model, installer build, output folder
or publication evidence was run or changed.
