# Run API and audit UI

Prompt 08 replaces the former status-only frontend with on-demand views over the
artifacts created by the selected model modules. The Run centre remains an annual
results surface; detailed evidence is loaded only after a user opens a collapsed
planning panel or the Audit view.

## User flow

1. **Research projects** selects a Data Pack and manifest-registered PSM/CEM
   implementations. `Advanced settings` is generated from
   `gridform_core.parameters.PARAMETERS`; no parameter is duplicated in the UI.
2. **Preview effective parameters** calls the same resolver used before execution.
   Each field reports whether its effective value comes from the module default,
   Data Pack, runtime default or project override.
3. **Run centre** starts the shared `gridform_core.application` service. A smoke
   run publishes wiring evidence but deliberately hides annual economics.
4. Each full-year result has a collapsed **Planning pipeline** summary. Opening it
   fetches counts and MW by outcome, stage, technology, region and near-term
   completion year.
5. **Audit** loads paginated planning projects/events and period summaries. Order
   rows are requested only for a selected period and only exist when the project
   selected `runtime.market_trace_level = full`.
6. **Artifacts & provenance** lists run-relative downloads and resolved execution
   identity without returning absolute workstation paths.

## HTTP contract

| Method and path | Purpose | Bounded behaviour |
| --- | --- | --- |
| `GET /api/modules` | Executable manifests and capabilities | Small registry payload |
| `GET /api/parameters` | Typed parameter schema | Small registry payload |
| `POST /api/parameters/preview` | Effective values, sources and warnings | No model run |
| `GET /api/runs/{id}/planning/summary` | Annual planning aggregates | Aggregate JSON only |
| `GET /api/runs/{id}/planning/projects` | Project search/filter | `limit` capped at 500 |
| `GET /api/runs/{id}/planning/events` | Lifecycle event filter | `limit` capped at 500 |
| `GET /api/runs/{id}/market/periods` | Clearing-period summary | `limit` capped at 1,000 |
| `GET /api/runs/{id}/market/orders` | Selected-period bids/orders | `limit` capped at 1,000 |
| `GET /api/runs/{id}/market/storage` | Selected-period storage state | `limit` capped at 1,000 |
| `GET /api/runs/{id}/artifacts` | Run-relative artifact metadata | File content is not inlined |
| `GET /api/runs/{id}/artifacts/{path}` | Safe artifact download | Traversal and absolute paths rejected |
| `GET /api/runs/{id}/provenance` | Sanitised run identity | No absolute local paths |

All detailed table endpoints read the durable SQLite ledgers created by the real
planning and PSM modules. They are not reconstructed from frontend fixtures.

## Manifest-to-execution proof

- `backend.server` returns `gridform_core.catalog.MODULES`, which is produced by
  `builtin_registry().catalog()` from the JSON module manifests.
- A project persists the selected manifest IDs.
- `gridform_core.application.run_project_application` validates those IDs and
  resolves their Python implementations through the same registry.
- The v2 orchestrator writes module ID/version stage events. The UI's module list
  and run evidence therefore share one source of truth.
- Parameter controls follow the same pattern: `parameter_schema()` serialises the
  registry used by `resolve_scheme_c_parameters()` during launch.

## Acceptance evidence (2026-08-04)

The real two-period full-trace fixture
`prompt08-audit-fixture-20260804-031129-3c915d` completed with:

- 12,983 durable planning projects, including visible filtered projects and reason
  codes;
- 2 period summaries and 96 order rows (48 in each selected period);
- a 14,561,280-byte planning ledger and 65,536-byte market ledger;
- 53,202-byte initial `/api/workspace` payload and 1,173-byte run-status payload;
- 23,200-byte 25-project page and 19,323-byte 48-order page.

Growing either SQLite ledger does not grow `/api/workspace` or `status.json`; a
regression test places a 2 MB ledger beside a run and verifies the run-list JSON
remains below 2 KB. Browser checks passed for the Advanced settings/source preview,
planning search/failure reasons, full-trace period/orders, summary-only explanation,
artifact links and sanitised provenance.

