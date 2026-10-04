# DATA-09 — CLI and local job API

Execute after DATA-08 passes. Act as a local-application backend engineer. The
CLI and HTTP API are thin adapters over the same DataWorkbenchService.

## Objective

Expose reproducible source, build, validation and promotion operations to
programmers and the local frontend, with safe background jobs and cancellation.

## Required work

1. Add CLI subcommands `discover`, `fetch`, `compile`, `validate`, `candidates`,
   `promote`, `sources`, `diff`, `report`, `export` and `freshness`.
2. Return concise terminal summaries and persist complete structured reports.
3. Add `/api/data-workbench/v1` source, revision, job, candidate, report and
   bundle endpoints through a focused backend module rather than further
   enlarging route-specific science logic in `backend/server.py`.
4. Persist job identity, declared input, progress, status, timestamps and error
   codes in local SQLite or the established local state mechanism.
5. Support cooperative cancellation for discover/fetch/compile/validate. A
   cancelled operation leaves no usable partial receipt or candidate.
6. Require Candidate hash, version, reviewer and exact accepted-waiver IDs for
   promotion and revalidate server-side.
7. Serialize DTOs without absolute paths and reject unknown schema versions.

## Acceptance gate

- CLI and API contract tests return equivalent DTOs for the same service call.
- Background-job tests cover queued, running, completed, failed, cancel-requested
  and cancelled transitions.
- Restart tests recover durable job state without promoting partial work.
- API tests reject path traversal, stale Candidate hashes, missing review fields
  and client attempts to override validator output.
- Existing model-run and data-pack endpoints retain their behaviour.

## Stop conditions

Stop if CLI and API duplicate compiler logic, if jobs rely on process-global
mutable state, or if cancellation deletes a verified raw object or formal bundle.

## Deliverables

- versioned CLI;
- local job store and service runner;
- focused Data Workbench API routes;
- cancellation/restart/error tests;
- DATA-09 gate record and commit.

