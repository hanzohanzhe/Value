# Changelog

## Unreleased — P0 fixes on fix/review-2026-10-04

### Local API security boundary (P0-1)

- The browser talks only to the UI origin. `scripts/value-ui-gateway.mjs`
  (mounted by `serve-value-ui.mjs` and, for development, by `vite.config.ts`)
  answers only `127.0.0.1:<port>`/`localhost:<port>` (421 otherwise), refuses
  cross-site `/api` requests and writes without the page Origin (403), needs
  a Content-Length on POST (411), sends a per-response CSP nonce,
  `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy: no-referrer`, COOP/CORP, and forwards `/api` with the
  API session.  A foreign Host on a page gets the "Open VALUE from its
  launcher" explanation.
- The API generates a session token per process and writes it only to
  `<VALUE_DATA_HOME>/runtime/api-session-<port>.json` (0700/0600, atomic;
  removed on exit only by its owner).  Every request passes
  `backend/api_security.evaluate`: Host 421, any Origin 403
  `GF_BROWSER_ORIGIN_REJECTED`, cross-site Sec-Fetch-Site 403, invalid
  Content-Length 400, chunked POST 411, missing/wrong session 403
  `GF_SESSION_REQUIRED`/`GF_SESSION_INVALID`, form-style or missing POST
  Content-Type 415 `GF_CONTENT_TYPE_REJECTED`.
- Launchers pass `--api-origin` after `--port` (process patterns unchanged),
  never the token, and wait until the gateway reaches the API.
- Frontend calls same-origin `/api`; `NEXT_PUBLIC_VALUE_API_ORIGIN` is gone;
  pages are rendered per request (`force-dynamic`).
- `scripts/verify_local_security_boundary.py` probes an installation.
- **API contract changes (breaking for direct clients):** no CORS at all;
  new request header `X-VALUE-Session` (scripts:
  `backend.api_session.authorized_headers`); new response header
  `X-VALUE-Error-Code`; new statuses 421, 403, 415, 411, 400 and, at the
  gateway, 502 `GF_GATEWAY_SESSION_UNAVAILABLE`/`GF_GATEWAY_SESSION_MISMATCH`/
  `GF_GATEWAY_UPSTREAM_UNAVAILABLE`; `GET /api/health` without a session
  returns only `ok, service, version, python,
  authoritative_runtime_compatible, session_required, status,
  degraded_reasons`; the comparison CSV is an attachment.  The backend source
  hash is part of the execution identity, so Runs left unfinished by an
  earlier version cannot be resumed after the upgrade.
- `SECURITY.md` names VALUE, points to the VALUE advisory form and states the
  single-user host assumption; `X-VALUE-Executable-Trust` is documented as
  informed consent, not a security control.

### Run lifecycle (P0-3)

- `status.json` has a single writer API (`backend/lifecycle/run_status.py`):
  per-run file lock, field-level merges, a consecutive `lifecycle_history`,
  late worker writes recorded in `late-worker-*.json` without touching
  sealed artifacts. Cancellation is the `cancel-request.json` file only.
- Workers start through `python -m backend.worker_entry`, take a lease
  (`worker.lock`) before heavy imports, run detached from the backend and
  are reaped, supervised and reconciled at start-up (`GF_WORKER_EXITED`,
  `GF_WORKER_LOST`, `GF_WORKER_IMPORT_FAILED`, `GF_WORKER_TERMINATED`,
  `GF_WORKER_SPAWN_FAILED`); `POST /api/runs/<id>/mark-lost`; one backend
  per data directory (`.backend.lock`, exit code 3).
- Delete moves the run to the trash before recording `deleting`; runs a
  previous version left in `deleting` are repaired at start-up.
- Disk quota counts physical bytes once per inode and reservations only
  for the unwritten output of active runs; one rule for reservation,
  preflight, snapshot readiness and resume; reservation lock is a flock
  (timeout 503); reservation report v2.
- Every API request has one exception boundary (`_dispatch`); listings
  isolate bad records instead of failing.
- Launchers start every interpreter with `-B -s -X pycache_prefix=<fresh
  directory>`; stray `__pycache__` bytecode is quarantined instead of
  blocking start/diagnose (`diagnose-value --repair-bytecode`).
- API additions: `worker_liveness`, `worker`, `cancel_requested_at`,
  `persisted_status`; `worker.json` v2.

## 0.6.0-alpha.2 — VALUE Network Extensions identity (2026-08-20)

- Adopted the scientific name **VALUE**: Variable renewable electricity
  Allocation, Load-enabled excess-generation Utilisation, and system Evolution.
- Named this repository **VALUE Network Extensions** and kept the accepted
  single-node baseline distinct from optional network capabilities.
- Preserved `value.*`, `value.*`, `gridform_core`, `VALUE_DATA_HOME` and
  legacy launcher names as 0.x compatibility identifiers so existing Studies,
  checkpoints and external modules remain readable.
- Added VALUE-named launchers without changing the scientific execution path.

## 0.6.0-alpha.1 — Expanded-platform private test candidate (2026-08-19)

- Added versioned, fail-closed extension capability graphs and transactional
  extension bundles without changing the single execution registry.
- Added explicit run-of-river and reservoir hydrology contracts, with pumped
  hydro kept in the existing storage model.
- Added an open chronological DC network PSM independently checked on
  analytical, random, 24-hour and 168-hour cases.
- Added a local-only experimental AC feasibility checker; AC optimal power flow
  and global AC optimality remain not evaluated.
- Added an experimental, causal transmission-expansion lifecycle with explicit
  candidates, budgets, lineage, cost and carbon accounting.
- Preserved the Prompt 64 single-node beta and retained VALUE source hashes.

## 0.5.0-beta.1 — Prompt 58 local module bundles

- Added deterministic `value.module-bundle/v1` packaging and an offline,
  transactional local installer.
- Added the Modules-page install, trust acknowledgement, provenance and
  enable/disable workflow without changing the single execution registry.
- Prevented built-in shadowing, unsafe ZIP paths, native binaries, inventory
  mutation and disabling modules referenced by saved Studies.
- Added an uploadable storage-cost example, bilingual guidance and bounded
  installer/API/security tests.

## Unreleased — post-Prompt 46 corrections (2026-08-10)

- Added versioned commissioned-asset records with CAPEX, FOM, economic life,
  CRF, annualised cost and project lineage; incomplete economics now fail closed.
- Coupled cumulative commissioned assets into the following year's live VALUE
  clearing fleet and reconciled asset economics with the annual capital ledger.
- Declared the public CEM as `force-cem-v1`, VALUE-derived with explicit
  divergences and no exact retained numerical-reproduction claim.
- Closed direct, import and embodied annual carbon ledgers across JSON and
  SQLite outputs.
- Added a separately verified 25-role UK public-data candidate with per-object
  source terms, attribution and integrity evidence.
- Regenerated the one-year, causal two-year, dynamic ten-year and legacy-tariff
  ten-year runs and passed the bounded scientific beta release gates.

## 0.5.0-beta.1 — 2026-08-08

- Added native public-contract execution for the optional perfect-foresight PSM.
- Added canonical CEM cost, carbon, planning, terminal and fleet ledgers.
- Added immutable input snapshots, safe run bundles and lifecycle controls.
- Added independent CBC validation of the HiGHS perfect-foresight formulation.
- Added bounded run comparison and storage-policy experiment contracts.
- Licensed owner-controlled software under Apache-2.0, repository documentation
  under CC BY 4.0 and the deterministic synthetic data pack under CC0 1.0.
- Recorded Hanzhe Xing as copyright owner and project lead, with Stuart Scott and
  John Miles acknowledged as contributing supervisors and advisors.
- Added a metadata-only source register for all 25 local UK data roles and
  verified every installed object's size and SHA-256 without changing VALUE.
- Kept UK data redistribution and VALUE direct-runtime cutover as independent
  release gates.
