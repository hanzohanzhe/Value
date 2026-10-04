# Prompt 123 — bounded VALUE replay queries and on-demand exports

## Scope

Prompt 123 changes only read and export access for staged bid-at-cost plus
balancing/zonal ledgers. It does not change offers, dispatch, settlement,
storage SOC, curtailment, solver settings, CEM, annual transitions, other PSMs,
Prompt 96 data, retained Scheme C or frontend structure. SQLite remains the
sole authoritative period store; JSONL and CSV exist only as explicitly
requested bounded exports.

## Bounded read contract

Public long-result readers accept `year`, `period_from`, `period_to`, `limit`
and `offset`. Limits outside 1–1,000 and negative or reversed ranges fail
closed. Filtering, exact totals, stable ordering, pagination and chart
aggregation are performed in SQLite before rows are returned.

For v8, dispatch charts use `dispatch_summary` by ledger schema and never infer
a fallback from whether the requested page happens to contain summary rows.
Legacy v4–v7 tables remain readable through the same read-only connection path
and are never migrated or rewritten. Sparse legacy totals/pages are computed
from actual SQL buckets rather than a continuous-period assumption. Summary
capabilities publish `bid_replay_available=false`, name the missing individual
bid/acceptance/settlement detail and direct users to create a new Full market
replay Study revision; absence is never reported as zero bids.

## Replay and tabular exports

`ReplayExportRequest` supports one period, 24 hours, 168 hours, one year and an
explicit complete run. JSONL and CSV require a declared bounded range; a
complete-run export is available only as a replay ZIP. It requires an
officially completed Run, every frozen Study year, and a complete contiguous
annual integrity record whose declared and observed period counts agree.
Requests also validate Full market replay detail and a destination confined to
the run's export root.

A replay ZIP contains the applicable run/year contexts, one declared-input and
outcome member per selected period, the immutable Study revision and input
snapshot manifest, exact module/solver identity, annual science/evidence roots,
the authoritative ledger checksum and a checksum/byte count for every member.
The writer streams period selection in stable SQL order, publishes through a
same-directory temporary file and an atomic non-overwriting link, and never
changes the ledger.

Pack and network-pack manifests are evaluated conservatively. Source dataset
bytes are never copied automatically. Any local-use-only, pointer-only,
undeclared or otherwise restricted binding makes the package
`reference_only_not_portable`; immutable identity and local reference remain in
the sanitized manifest. Missing/empty bindings, unknown rights declarations and
missing applicable network-pack manifests fail closed. Only explicitly known
redistributable declarations permit the `portable` label. Context artifacts are
copied only after registry, canonical contract, file content, year-integrity and
frozen Study identities agree.

Completed legacy runs that predate SQLite remain readable through a bounded,
streaming `staged-market.jsonl` adapter. It is selected only when no v8 ledger
applies and any legacy SQLite adapter contains no period rows; it never migrates,
rewrites or materialises the complete file in memory.

## Background jobs

The loopback server exposes replay export jobs separately from the model
worker. `POST /api/runs/<run>/replay-exports` writes a queued job record and
starts a daemon export worker; `GET /api/runs/<run>/replay-exports/<job>`
returns queued/running/completed/failed state and the completed artifact link.
Each job has a unique destination and durable JSON status under the run export
root, so generation does not block or mutate scientific execution.

## Focused evidence

The RED run failed because `gridform_core.replay_export` did not exist. The
focused GREEN checks cover stable exact range pages, the hard 1,000-row limit,
v8 summary preference and capability truthfulness, byte-identical v7 fallback,
48 input/outcome pairs in a 24-hour ZIP, context/Study/identity/root/checksum
inventory, restricted rights, destination confinement, explicit JSONL bounds,
atomic publication, background job progress and source-ledger non-mutation.

Only these tests belong to this Prompt:

```powershell
python -m unittest discover -s tests -p "test_prompt123_bounded_replay_export.py" -v
python -m unittest discover -s tests -p "test_market_replay.py" -v
python -m unittest discover -s tests -p "test_prompt102_zonal_results_api.py" -v
```

No full suite, frontend build, annual run or ten-year run is authorised here.
